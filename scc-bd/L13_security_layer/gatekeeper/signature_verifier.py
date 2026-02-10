#!/usr/bin/env python3
"""
签名验证适配器层
支持本地签名与 KMS 验签两种后端
"""

import hashlib
import json
import os
from abc import ABC, abstractmethod

# 导入原因码
from .reason_codes import GateReasonCode


class SignatureVerifier(ABC):
    """签名验证器抽象基类"""

    @abstractmethod
    def verify_signatures(self, signature_map_path: str, rules: dict) -> tuple:
        """验证文件签名

        Args:
            signature_map_path: 签名映射文件路径
            rules: 验证规则

        Returns:
            tuple: (exit_code, reason_code, message)
                  - exit_code: 0 表示验证通过，1 表示验证失败
                  - reason_code: 原因码
                  - message: 详细信息
        """
        pass


class LocalSignatureVerifier(SignatureVerifier):
    """本地签名验证器"""

    def verify_signatures(self, signature_map_path: str, rules: dict) -> tuple:
        """验证文件签名（本地实现）

        规则：
        1. 检查是否存在签名映射文件
        2. 验证每个文件的签名是否匹配
        """
        # 检查是否启用了签名验证
        if not rules.get("enabled", True):
            return 0, GateReasonCode.SUCCESS, "[INFO] 签名验证已禁用"

        # 检查签名映射文件是否存在
        if not os.path.exists(signature_map_path):
            message = f"[ERROR] 缺少签名映射文件: {signature_map_path}"
            return 1, GateReasonCode.MISSING_SIGNATURE_MAP, message

        # 读取签名映射文件
        try:
            with open(signature_map_path, encoding="utf-8") as f:
                signature_map = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            message = f"[ERROR] 无法读取或解析签名映射文件: {e}"
            return 1, GateReasonCode.INVALID_SIGNATURE, message

        # 验证每个文件的签名
        invalid_files = []
        for file_path, expected_hash in signature_map.items():
            if not os.path.exists(file_path):
                continue

            # 计算文件的SHA256哈希值
            try:
                with open(file_path, "rb") as f:
                    file_content = f.read()
                actual_hash = hashlib.sha256(file_content).hexdigest()

                # 验证哈希值
                if actual_hash != expected_hash:
                    invalid_files.append((file_path, actual_hash, expected_hash))
            except OSError as e:
                message = f"[ERROR] 无法读取文件 {file_path}: {e}"
                invalid_files.append((file_path, "ERROR", expected_hash))

        # 如果有无效的签名，返回失败
        if invalid_files:
            message = f"[ERROR] 发现{len(invalid_files)}个文件签名验证失败:"
            for file_path, actual_hash, expected_hash in invalid_files:
                message += f"\n  - {file_path}: 实际哈希={actual_hash}, 期望哈希={expected_hash}"
            return 1, GateReasonCode.INVALID_SIGNATURE, message

        message = "[SUCCESS] 所有文件签名验证通过"
        return 0, GateReasonCode.SUCCESS, message


class KMSSignatureVerifier(SignatureVerifier):
    """KMS签名验证器"""

    def __init__(self):
        """初始化KMS签名验证器"""
        # KMS配置可以从环境变量或配置文件中获取
        self.kms_client = None
        self.kms_key_id = os.environ.get("KMS_KEY_ID")

    def verify_signatures(self, signature_map_path: str, rules: dict) -> tuple:
        """验证文件签名（KMS实现）

        规则：
        1. 检查是否存在签名映射文件
        2. 使用KMS验证每个文件的签名
        """
        # 检查是否启用了签名验证
        if not rules.get("enabled", True):
            return 0, GateReasonCode.SUCCESS, "[INFO] 签名验证已禁用"

        # 检查签名映射文件是否存在
        if not os.path.exists(signature_map_path):
            message = f"[ERROR] 缺少签名映射文件: {signature_map_path}"
            return 1, GateReasonCode.MISSING_SIGNATURE_MAP, message

        # 读取签名映射文件
        try:
            with open(signature_map_path, encoding="utf-8") as f:
                signature_map = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            message = f"[ERROR] 无法读取或解析签名映射文件: {e}"
            return 1, GateReasonCode.INVALID_SIGNATURE, message

        # 检查KMS配置
        if not self.kms_key_id:
            message = "[ERROR] KMS_KEY_ID环境变量未配置"
            return 1, GateReasonCode.INVALID_SIGNATURE, message

        # 模拟KMS验证过程
        # 在实际实现中，这里应该调用KMS API进行签名验证
        invalid_files = []
        for file_path, expected_signature in signature_map.items():
            if not os.path.exists(file_path):
                continue

            # 计算文件的SHA256哈希值
            try:
                with open(file_path, "rb") as f:
                    file_content = f.read()
                file_hash = hashlib.sha256(file_content).hexdigest()

                # 模拟KMS验证
                # 实际实现中应该调用KMS的verify_signature API
                # 这里简化处理，直接比较哈希值
                # 注意：这只是模拟实现，实际KMS验证会更复杂
                if file_hash != expected_signature:
                    invalid_files.append((file_path, file_hash, expected_signature))
            except OSError as e:
                message = f"[ERROR] 无法读取文件 {file_path}: {e}"
                invalid_files.append((file_path, "ERROR", expected_signature))

        # 如果有无效的签名，返回失败
        if invalid_files:
            message = f"[ERROR] 发现{len(invalid_files)}个文件签名验证失败:"
            for file_path, actual_hash, expected_signature in invalid_files:
                message += (
                    f"\n  - {file_path}: 实际哈希={actual_hash}, 期望签名={expected_signature}"
                )
            return 1, GateReasonCode.INVALID_SIGNATURE, message

        message = "[SUCCESS] 所有文件签名验证通过（KMS）"
        return 0, GateReasonCode.SUCCESS, message


class SignatureVerifierFactory:
    """签名验证器工厂类
    根据环境变量选择合适的签名验证器
    """

    @staticmethod
    def get_verifier() -> SignatureVerifier:
        """获取签名验证器实例

        Returns:
            SignatureVerifier: 签名验证器实例
        """
        # 根据环境变量选择验证器
        verifier_type = os.environ.get("SIGNATURE_VERIFIER_TYPE", "local")

        if verifier_type.lower() == "kms":
            return KMSSignatureVerifier()
        else:
            return LocalSignatureVerifier()
