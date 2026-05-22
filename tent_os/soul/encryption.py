"""加密存储工具 —— 灵魂模型仓库的AES加密"""

import os
import hashlib
import base64
from pathlib import Path
from typing import Union

try:
    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    _CRYPTO_AVAILABLE = True
except ImportError:
    _CRYPTO_AVAILABLE = False


class SoulEncryption:
    """基于用户密码的AES加密器，用于本地灵魂数据加密"""
    
    def __init__(self, password: str = None, salt: bytes = None):
        self._key = None
        if _CRYPTO_AVAILABLE and password:
            self._init_key(password, salt)
    
    def _init_key(self, password: str, salt: bytes = None):
        if salt is None:
            salt = os.urandom(16)
        self.salt = salt
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=480000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
        self._key = key
        self._fernet = Fernet(key)
    
    def encrypt(self, data: bytes) -> bytes:
        if not _CRYPTO_AVAILABLE:
            return data
        if self._fernet is None:
            return data
        return self._fernet.encrypt(data)
    
    def decrypt(self, data: bytes) -> bytes:
        if not _CRYPTO_AVAILABLE:
            return data
        if self._fernet is None:
            return data
        return self._fernet.decrypt(data)
    
    def encrypt_file(self, src_path: Union[str, Path], dst_path: Union[str, Path]):
        src_path = Path(src_path)
        dst_path = Path(dst_path)
        data = src_path.read_bytes()
        encrypted = self.encrypt(data)
        dst_path.write_bytes(encrypted)
    
    def decrypt_file(self, src_path: Union[str, Path], dst_path: Union[str, Path]):
        src_path = Path(src_path)
        dst_path = Path(dst_path)
        data = src_path.read_bytes()
        decrypted = self.decrypt(data)
        dst_path.write_bytes(decrypted)
