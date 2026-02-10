#!/usr/bin/env python3
"""
Self-test script for OAuth production readiness
"""

import os
import subprocess
import sys
import time
from datetime import datetime, timedelta

import requests
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jose import jwt


def generate_rsa_keys():
    """Generate RSA key pair for testing"""
    private_key = rsa.generate_private_key(
        public_exponent=65537, key_size=2048, backend=default_backend()
    )

    public_key = private_key.public_key()

    # Convert to PEM format
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )

    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM, format=serialization.PublicFormat.SubjectPublicKeyInfo
    )

    return private_pem.decode("utf-8"), public_pem.decode("utf-8")


def generate_test_token(private_key, is_expired=False):
    """Generate test JWT token"""
    # Set expiration time
    if is_expired:
        expiry = datetime.utcnow() - timedelta(minutes=5)
    else:
        expiry = datetime.utcnow() + timedelta(minutes=5)

    # Create payload
    payload = {
        "iss": "https://auth.example.com",
        "aud": "api://exchange-server",
        "sub": "test_user",
        "exp": expiry,
        "iat": datetime.utcnow(),
        "client_id": "test_client",
    }

    # Encode token
    token = jwt.encode(payload, private_key, algorithm="RS256")
    return token


def start_server(public_key):
    """Start exchange server with OAuth config"""
    # Set environment variables
    env = os.environ.copy()
    env.update(
        {
            "EXCHANGE_JSONRPC_AUTH_TYPE": "oauth",
            "EXCHANGE_SSE_AUTH_MODE": "oauth",
            "EXCHANGE_SSE_OAUTH_ENABLED": "true",
            "EXCHANGE_JSONRPC_OAUTH_ENABLED": "true",
            "EXCHANGE_OAUTH_ISSUER": "https://auth.example.com",
            "EXCHANGE_OAUTH_AUDIENCE": "api://exchange-server",
            "EXCHANGE_OAUTH_CLIENT_ID": "test_client",
            "EXCHANGE_OAUTH_PUBLIC_KEY": public_key,
            "EXCHANGE_OAUTH_ALGORITHMS": "RS256",
        }
    )

    # Start server in background with different port to avoid conflict
    print("Starting exchange server...")
    server_process = subprocess.Popen(
        ["python", "-m", "tools.exchange_server.main", "--port=8081"],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    # Wait for server to start
    time.sleep(5)

    # Check if server is still running
    if server_process.poll() is not None:
        # Server exited, get output
        stdout, stderr = server_process.communicate()
        if stdout:
            print(f"Server stdout: {stdout}")
        if stderr:
            print(f"Server stderr: {stderr}")
        print(f"Server exited with code: {server_process.returncode}")
        return None
    else:
        print("Server is running")

    return server_process


def test_no_token_sse():
    """Test accessing SSE without token"""
    try:
        response = requests.get("http://localhost:18788/sse", timeout=5)
        print(f"Test no_token_sse - Status: {response.status_code}, Text: {response.text}")
        return response.status_code == 401 and "MISSING_AUTH_HEADER" in response.text
    except requests.RequestException as e:
        print(f"Test no_token_sse - Exception: {e}")
        return False


def test_expired_token(private_key):
    """Test accessing SSE with expired token"""
    expired_token = generate_test_token(private_key, is_expired=True)
    headers = {"Authorization": f"Bearer {expired_token}"}

    try:
        response = requests.get("http://localhost:8081/sse", headers=headers, timeout=5)
        print(f"Test expired_token - Status: {response.status_code}, Text: {response.text}")
        return response.status_code == 401 and "TOKEN_EXPIRED" in response.text
    except requests.RequestException as e:
        print(f"Test expired_token - Exception: {e}")
        return False


def test_valid_token(private_key):
    """Test accessing SSE with valid token"""
    valid_token = generate_test_token(private_key)
    headers = {"Authorization": f"Bearer {valid_token}"}

    try:
        response = requests.get(
            "http://localhost:8081/sse", headers=headers, timeout=5, stream=True
        )
        print(f"Test valid_token - Status: {response.status_code}")
        return response.status_code == 200
    except requests.RequestException as e:
        print(f"Test valid_token - Exception: {e}")
        return False


def main():
    """Run self-tests"""
    # Generate test keys
    private_key, public_key = generate_rsa_keys()

    # Start server
    server_process = None
    exit_code = 1  # Default to failure

    try:
        server_process = start_server(public_key)

        # Run tests
        tests = [
            ("无 token 访问 SSE", test_no_token_sse),
            ("过期 token 访问 SSE", lambda: test_expired_token(private_key)),
            ("合法 token 访问 SSE", lambda: test_valid_token(private_key)),
        ]

        passed = 0
        total = len(tests)

        # Create selftest.log
        with open("selftest.log", "w", encoding="utf-8") as f:
            f.write("OAuth Production Readiness Self-Test\n")
            f.write(f"Test Date: {datetime.now().isoformat()}\n")
            f.write(f"\n{'=' * 50}\n")

            for test_name, test_func in tests:
                result = test_func()
                status = "PASS" if result else "FAIL"

                f.write(f"Test: {test_name}\n")
                f.write(f"Result: {status}\n")
                f.write(f"{'=' * 50}\n")

                if result:
                    passed += 1

        # Update exit code based on results
        if passed == total:
            exit_code = 0

        # Append exit code to log
        with open("selftest.log", "a", encoding="utf-8") as f:
            f.write(f"\nSummary: {passed}/{total} tests passed\n")
            f.write(f"EXIT_CODE={exit_code}\n")

    finally:
        # Stop server
        if server_process:
            server_process.terminate()
            try:
                server_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server_process.kill()

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
