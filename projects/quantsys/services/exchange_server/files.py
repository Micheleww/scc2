#!/usr/bin/env python3
"""
Files module with S3 presigned URL functionality
"""

import json
import os
import time
import uuid
from collections import defaultdict
from datetime import datetime

# Mock S3 implementation for testing
# In a real implementation, this would use boto3
boto3 = None
try:
    import boto3
    from botocore.exceptions import ClientError
except ImportError:
    pass


class FilesModule:
    """Files module with S3 presigned URL functionality"""

    def __init__(self):
        # Mock S3 bucket name (would be configured via environment)
        self.s3_bucket = os.getenv("S3_BUCKET_NAME", "test-bucket")

        # URL expiration time in seconds (15 minutes as per requirement)
        self.url_expiration = int(os.getenv("S3_URL_EXPIRATION", "900"))

        # In-memory denylist for revoked files
        self.denylist = set()
        self.denylist_file = os.getenv("FILES_DENYLIST_FILE", "files_denylist.json")

        # Track used upload IDs
        self.used_upload_ids = defaultdict(set)  # {client_id: {upload_id}}

        # Load denylist from disk if it exists
        self._load_denylist()

        # Mock S3 client (for testing purposes)
        self.s3_client = None
        if boto3:
            try:
                self.s3_client = boto3.client("s3")
            except Exception:
                # Fall back to mock implementation
                self.s3_client = None

    def _load_denylist(self):
        """Load denylist from disk"""
        if os.path.exists(self.denylist_file):
            try:
                with open(self.denylist_file) as f:
                    denylist_data = json.load(f)
                    self.denylist = set(denylist_data.get("denylist", []))
            except Exception as e:
                print(f"Error loading denylist: {e}")

    def _save_denylist(self):
        """Save denylist to disk"""
        try:
            with open(self.denylist_file, "w") as f:
                json.dump({"denylist": list(self.denylist)}, f)
        except Exception as e:
            print(f"Error saving denylist: {e}")

    def generate_presigned_url(self, file_id, operation, client_id):
        """
        Generate presigned URL for S3 operations

        Args:
            file_id: Unique identifier for the file
            operation: Type of operation ("upload" or "download")
            client_id: Client identifier for isolation

        Returns:
            dict: Presigned URL information or error
        """
        # Check if file is revoked
        if file_id in self.denylist:
            return {
                "error_code": "FILE_REVOKED",
                "error_message": "File access has been revoked",
                "reason_code": "FILE_REVOKED",
            }

        # Validate operation
        if operation not in ["upload", "download"]:
            return {
                "error_code": "INVALID_OPERATION",
                "error_message": "Invalid operation type",
                "reason_code": "INVALID_OPERATION",
            }

        # Validate client_id
        if not client_id:
            return {
                "error_code": "INVALID_CLIENT_ID",
                "error_message": "Client ID is invalid",
                "reason_code": "INVALID_CLIENT_ID",
            }

        # Generate client-specific S3 key
        s3_key = f"{client_id}/{file_id}"

        # Generate one-time upload ID for upload operations
        upload_id = None
        if operation == "upload":
            upload_id = str(uuid.uuid4())
            self.used_upload_ids[client_id].add(upload_id)

        # Generate presigned URL
        presigned_url = self._generate_s3_presigned_url(s3_key, operation)

        # Return response
        response = {
            "presigned_url": presigned_url,
            "file_id": file_id,
            "expires_in": self.url_expiration,
        }

        if upload_id:
            response["upload_id"] = upload_id

        return response

    def _generate_s3_presigned_url(self, s3_key, operation):
        """
        Generate S3 presigned URL

        Args:
            s3_key: S3 object key
            operation: Type of operation

        Returns:
            str: Presigned URL
        """
        if self.s3_client:
            # Real S3 implementation
            try:
                if operation == "upload":
                    url = self.s3_client.generate_presigned_url(
                        "put_object",
                        Params={"Bucket": self.s3_bucket, "Key": s3_key},
                        ExpiresIn=self.url_expiration,
                    )
                else:  # download
                    url = self.s3_client.generate_presigned_url(
                        "get_object",
                        Params={"Bucket": self.s3_bucket, "Key": s3_key},
                        ExpiresIn=self.url_expiration,
                    )
                return url
            except Exception as e:
                print(f"S3 error, falling back to mock: {e}")
                # Fall back to mock URL for any exception (including missing credentials)

        # Mock URL for testing
        timestamp = int(time.time())
        expires = timestamp + self.url_expiration
        return f"https://{self.s3_bucket}.s3.amazonaws.com/{s3_key}?X-Amz-Expires={self.url_expiration}&X-Amz-Signature=mock_signature&X-Amz-Credential=mock_credential&X-Amz-Date={timestamp}&X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-SignedHeaders=host"

    def revoke(self, file_id):
        """
        Revoke access to a file by adding it to the server-side denylist

        Args:
            file_id: Unique identifier for the file to revoke

        Returns:
            dict: Revocation status
        """
        # Add to denylist
        self.denylist.add(file_id)

        # Save denylist to disk
        self._save_denylist()

        # Return response
        return {
            "status": "success",
            "file_id": file_id,
            "revoked_at": datetime.utcnow().isoformat() + "Z",
        }

    def is_valid_upload_id(self, client_id, upload_id):
        """
        Check if upload ID is valid and not used

        Args:
            client_id: Client identifier
            upload_id: Upload ID to check

        Returns:
            bool: True if valid, False otherwise
        """
        if client_id not in self.used_upload_ids:
            return False

        if upload_id not in self.used_upload_ids[client_id]:
            return False

        # Remove upload ID after use (one-time use only)
        self.used_upload_ids[client_id].remove(upload_id)
        return True

    def check_file_access(self, file_id):
        """
        Check if file access is allowed

        Args:
            file_id: Unique identifier for the file

        Returns:
            dict: Access status or error
        """
        # Check if file is revoked
        if file_id in self.denylist:
            return {
                "error_code": "FILE_REVOKED",
                "error_message": "File access has been revoked",
                "reason_code": "FILE_REVOKED",
            }

        return {"status": "allowed"}

    def get_denylist(self):
        """
        Get the current denylist

        Returns:
            list: List of revoked file IDs
        """
        return list(self.denylist)

    def clear_denylist(self):
        """
        Clear the denylist

        Returns:
            dict: Clear status
        """
        self.denylist.clear()
        self._save_denylist()
        return {"status": "success", "message": "Denylist cleared"}
