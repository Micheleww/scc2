#!/usr/bin/env python3
"""
用户认证与权限管理系统
"""

import hashlib
import logging
import os
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any

import jwt

logger = logging.getLogger(__name__)


class UserRole(Enum):
    """用户角色"""

    ADMIN = "admin"
    OPERATOR = "operator"
    VIEWER = "viewer"


@dataclass
class User:
    """用户信息"""

    id: str
    username: str
    password_hash: str
    role: UserRole
    created_at: datetime
    last_login: datetime | None = None
    active: bool = True


class AuthService:
    """认证服务"""

    def __init__(self, db_path: Path | None = None):
        if db_path is None:
            db_path = Path(__file__).parent.parent.parent / "data" / "auth.db"

        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.secret_key = os.getenv("AUTH_SECRET_KEY", secrets.token_urlsafe(32))
        self.token_expire_hours = int(os.getenv("AUTH_TOKEN_EXPIRE_HOURS", "24"))

        self._init_database()
        self._create_default_admin()

    def _init_database(self):
        """初始化数据库"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL,
                created_at TEXT NOT NULL,
                last_login TEXT,
                active INTEGER DEFAULT 1
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                token TEXT UNIQUE NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS audit_logs (
                id TEXT PRIMARY KEY,
                user_id TEXT,
                action TEXT NOT NULL,
                resource TEXT,
                timestamp TEXT NOT NULL,
                ip_address TEXT,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)

        conn.commit()
        conn.close()

    def _create_default_admin(self):
        """创建默认管理员账户"""
        default_username = os.getenv("DEFAULT_ADMIN_USERNAME", "admin")
        default_password = os.getenv("DEFAULT_ADMIN_PASSWORD", "admin123")

        if not self.get_user_by_username(default_username):
            self.create_user(
                username=default_username, password=default_password, role=UserRole.ADMIN
            )
            logger.info(f"Created default admin user: {default_username}")

    def _hash_password(self, password: str) -> str:
        """密码哈希"""
        return hashlib.sha256(password.encode()).hexdigest()

    def create_user(self, username: str, password: str, role: UserRole = UserRole.VIEWER) -> str:
        """创建用户"""
        user_id = secrets.token_urlsafe(16)
        password_hash = self._hash_password(password)

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute(
                """
                INSERT INTO users (id, username, password_hash, role, created_at, active)
                VALUES (?, ?, ?, ?, ?, ?)
            """,
                (user_id, username, password_hash, role.value, datetime.now().isoformat(), 1),
            )
            conn.commit()
            return user_id
        except sqlite3.IntegrityError:
            raise ValueError(f"Username {username} already exists")
        finally:
            conn.close()

    def authenticate(self, username: str, password: str) -> str | None:
        """用户认证，返回token"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT id, password_hash, role, active FROM users WHERE username = ?
        """,
            (username,),
        )

        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        user_id, password_hash, role, active = row

        if not active:
            return None

        if self._hash_password(password) != password_hash:
            return None

        # 更新最后登录时间
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE users SET last_login = ? WHERE id = ?
        """,
            (datetime.now().isoformat(), user_id),
        )
        conn.commit()
        conn.close()

        # 生成JWT token
        token = self._generate_token(user_id, username, role)

        # 保存session
        self._save_session(user_id, token)

        return token

    def _generate_token(self, user_id: str, username: str, role: str) -> str:
        """生成JWT token"""
        payload = {
            "user_id": user_id,
            "username": username,
            "role": role,
            "exp": datetime.utcnow() + timedelta(hours=self.token_expire_hours),
            "iat": datetime.utcnow(),
        }
        return jwt.encode(payload, self.secret_key, algorithm="HS256")

    def verify_token(self, token: str) -> dict[str, Any] | None:
        """验证token"""
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=["HS256"])
            return payload
        except jwt.ExpiredSignatureError:
            return None
        except jwt.InvalidTokenError:
            return None

    def _save_session(self, user_id: str, token: str):
        """保存session"""
        session_id = secrets.token_urlsafe(16)
        expires_at = datetime.now() + timedelta(hours=self.token_expire_hours)

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT INTO sessions (id, user_id, token, created_at, expires_at)
            VALUES (?, ?, ?, ?, ?)
        """,
            (session_id, user_id, token, datetime.now().isoformat(), expires_at.isoformat()),
        )

        conn.commit()
        conn.close()

    def logout(self, token: str):
        """登出"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("DELETE FROM sessions WHERE token = ?", (token,))

        conn.commit()
        conn.close()

    def get_user_by_username(self, username: str) -> User | None:
        """根据用户名获取用户"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT id, username, password_hash, role, created_at, last_login, active
            FROM users WHERE username = ?
        """,
            (username,),
        )

        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        return User(
            id=row[0],
            username=row[1],
            password_hash=row[2],
            role=UserRole(row[3]),
            created_at=datetime.fromisoformat(row[4]),
            last_login=datetime.fromisoformat(row[5]) if row[5] else None,
            active=bool(row[6]),
        )

    def get_user_by_id(self, user_id: str) -> User | None:
        """根据ID获取用户"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT id, username, password_hash, role, created_at, last_login, active
            FROM users WHERE id = ?
        """,
            (user_id,),
        )

        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        return User(
            id=row[0],
            username=row[1],
            password_hash=row[2],
            role=UserRole(row[3]),
            created_at=datetime.fromisoformat(row[4]),
            last_login=datetime.fromisoformat(row[5]) if row[5] else None,
            active=bool(row[6]),
        )

    def log_audit(
        self,
        user_id: str | None,
        action: str,
        resource: str | None = None,
        ip_address: str | None = None,
    ):
        """记录审计日志"""
        audit_id = secrets.token_urlsafe(16)

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT INTO audit_logs (id, user_id, action, resource, timestamp, ip_address)
            VALUES (?, ?, ?, ?, ?, ?)
        """,
            (audit_id, user_id, action, resource, datetime.now().isoformat(), ip_address),
        )

        conn.commit()
        conn.close()


# 权限检查装饰器
def require_role(required_role: UserRole):
    """权限检查装饰器"""

    def decorator(func):
        def wrapper(*args, **kwargs):
            # 这里需要从请求中获取token并验证
            # 实际实现会在main.py中
            return func(*args, **kwargs)

        return wrapper

    return decorator


# 全局认证服务实例
auth_service = AuthService()
