import base64
import hashlib
import hmac
import logging
import secrets
from datetime import datetime
from typing import Dict, Tuple, Any

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

class CryptographicError(Exception):
    pass


class CryptoService:
    def __init__(self):
        self.master_key = settings.get_secret_value('signature_private_key')
        self.salt = settings.get_secret_value('password_salt')

    def generate_key_pair(self) -> Tuple[str, str]:
        try:
            private_key = ed25519.Ed25519PrivateKey.generate()
            public_key = private_key.public_key()
            
            private_pem = private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption()
            )
            
            public_pem = public_key.public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo
            )
            
            return (
                base64.b64encode(private_pem).decode('utf-8'),
                base64.b64encode(public_pem).decode('utf-8')
            )
        except Exception as e:
            logger.error(f"Key pair generation failed: {e}")
            raise CryptographicError(f"Failed to generate key pair: {e}")

    def generate_contract_hash(self, content: str) -> str:
        try:
            content_bytes = content.encode('utf-8')
            
            if settings.contract_hash_algorithm == "blake2b":
                hash_obj = hashlib.blake2b(content_bytes, digest_size=32)
            else:
                hash_obj = hashlib.sha256(content_bytes)
            
            return hash_obj.hexdigest()
        except Exception as e:
            logger.error(f"Hash generation failed: {e}")
            raise CryptographicError(f"Failed to generate hash: {e}")

    def sign_contract(self, contract_data: str, phone_number: str) -> str:
        try:
            signing_key = self._derive_signing_key(phone_number)
            private_key = ed25519.Ed25519PrivateKey.from_private_bytes(signing_key)
            
            message = f"{contract_data}:{phone_number}:{datetime.utcnow().isoformat()}"
            signature = private_key.sign(message.encode('utf-8'))
            
            return base64.b64encode(signature).decode('utf-8')
        except Exception as e:
            logger.error(f"Contract signing failed: {e}")
            raise CryptographicError(f"Failed to sign contract: {e}")

    def verify_signature(self, contract_data: str, phone_number: str, signature: str) -> bool:
        try:
            signing_key = self._derive_signing_key(phone_number)
            private_key = ed25519.Ed25519PrivateKey.from_private_bytes(signing_key)
            public_key = private_key.public_key()
            
            signature_bytes = base64.b64decode(signature.encode('utf-8'))
            
            for time_window in [0, 1, 2]:
                test_time = datetime.utcnow().replace(minute=(datetime.utcnow().minute // 10 - time_window) * 10, second=0, microsecond=0)
                test_message = f"{contract_data}:{phone_number}:{test_time.isoformat()}"
                
                try:
                    public_key.verify(signature_bytes, test_message.encode('utf-8'))
                    return True
                except:
                    continue
            
            return False
        except Exception as e:
            logger.error(f"Signature verification failed: {e}")
            return False

    def generate_sms_confirmation_code(self, contract_id: str, phone_number: str) -> str:
        try:
            content = f"{contract_id}:{phone_number}:{datetime.utcnow().date().isoformat()}"
            hash_obj = hashlib.sha256(content.encode('utf-8'))
            hex_hash = hash_obj.hexdigest()
            
            numeric_code = int(hex_hash[:8], 16) % 1000000
            return f"{numeric_code:06d}"
        except Exception as e:
            logger.error(f"SMS code generation failed: {e}")
            raise CryptographicError(f"Failed to generate SMS code: {e}")

    def verify_sms_confirmation(self, contract_id: str, phone_number: str, code: str) -> bool:
        try:
            expected_code = self.generate_sms_confirmation_code(contract_id, phone_number)
            return hmac.compare_digest(code, expected_code)
        except Exception as e:
            logger.error(f"SMS verification failed: {e}")
            return False

    def generate_payment_reference(self, contract_id: str, amount: float, phone_number: str) -> str:
        try:
            content = f"{contract_id}:{amount}:{phone_number}"
            hash_obj = hashlib.blake2b(content.encode('utf-8'), digest_size=8)
            return hash_obj.hexdigest().upper()
        except Exception as e:
            logger.error(f"Payment reference generation failed: {e}")
            raise CryptographicError(f"Failed to generate payment reference: {e}")

    def create_audit_signature(self, action: str, contract_id: str, actor: str, data: Dict[str, Any]) -> str:
        try:
            timestamp = datetime.utcnow().isoformat()
            content = f"{action}:{contract_id}:{actor}:{timestamp}:{str(sorted(data.items()))}"
            
            signature = hmac.new(
                self.master_key.encode('utf-8'),
                content.encode('utf-8'),
                hashlib.sha256
            ).hexdigest()
            
            return f"{timestamp}:{signature}"
        except Exception as e:
            logger.error(f"Audit signature creation failed: {e}")
            raise CryptographicError(f"Failed to create audit signature: {e}")

    def verify_audit_signature(self, signature: str, action: str, contract_id: str, actor: str, data: Dict[str, Any]) -> bool:
        try:
            timestamp, sig_hash = signature.split(':', 1)
            content = f"{action}:{contract_id}:{actor}:{timestamp}:{str(sorted(data.items()))}"
            
            expected_signature = hmac.new(
                self.master_key.encode('utf-8'),
                content.encode('utf-8'),
                hashlib.sha256
            ).hexdigest()
            
            return hmac.compare_digest(sig_hash, expected_signature)
        except Exception as e:
            logger.error(f"Audit signature verification failed: {e}")
            return False

    def generate_webhook_signature(self, payload: str) -> str:
        try:
            webhook_secret = settings.get_secret_value('webhook_secret')
            signature = hmac.new(
                webhook_secret.encode('utf-8'),
                payload.encode('utf-8'),
                hashlib.sha256
            ).hexdigest()
            
            return f"sha256={signature}"
        except Exception as e:
            logger.error(f"Webhook signature generation failed: {e}")
            raise CryptographicError(f"Failed to generate webhook signature: {e}")

    def verify_webhook_signature(self, payload: str, signature: str) -> bool:
        try:
            expected_signature = self.generate_webhook_signature(payload)
            return hmac.compare_digest(signature, expected_signature)
        except Exception as e:
            logger.error(f"Webhook signature verification failed: {e}")
            return False

    def encrypt_sensitive_data(self, data: str, context: str = "") -> str:
        try:
            salt = secrets.token_bytes(16)
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=salt,
                iterations=100000,
            )
            
            key_material = f"{self.master_key}:{context}".encode('utf-8')
            key = kdf.derive(key_material)
            
            encrypted = self._xor_encrypt(data.encode('utf-8'), key)
            combined = salt + encrypted
            
            return base64.b64encode(combined).decode('utf-8')
        except Exception as e:
            logger.error(f"Data encryption failed: {e}")
            raise CryptographicError(f"Failed to encrypt data: {e}")

    def decrypt_sensitive_data(self, encrypted_data: str, context: str = "") -> str:
        try:
            combined = base64.b64decode(encrypted_data.encode('utf-8'))
            salt = combined[:16]
            encrypted = combined[16:]
            
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=salt,
                iterations=100000,
            )
            
            key_material = f"{self.master_key}:{context}".encode('utf-8')
            key = kdf.derive(key_material)
            
            decrypted = self._xor_encrypt(encrypted, key)
            return decrypted.decode('utf-8')
        except Exception as e:
            logger.error(f"Data decryption failed: {e}")
            raise CryptographicError(f"Failed to decrypt data: {e}")

    def generate_session_token(self, phone_number: str, session_type: str = "ussd") -> str:
        try:
            timestamp = datetime.utcnow().timestamp()
            content = f"{phone_number}:{session_type}:{timestamp}:{secrets.token_hex(8)}"
            
            token_hash = hashlib.blake2b(content.encode('utf-8'), digest_size=16)
            return base64.urlsafe_b64encode(token_hash.digest()).decode('utf-8').rstrip('=')
        except Exception as e:
            logger.error(f"Session token generation failed: {e}")
            raise CryptographicError(f"Failed to generate session token: {e}")

    def validate_contract_integrity(self, original_hash: str, current_content: str) -> bool:
        try:
            current_hash = self.generate_contract_hash(current_content)
            return hmac.compare_digest(original_hash, current_hash)
        except Exception as e:
            logger.error(f"Contract integrity validation failed: {e}")
            return False

    def _derive_signing_key(self, phone_number: str) -> bytes:
        try:
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=self.salt.encode('utf-8'),
                iterations=100000,
            )
            
            key_material = f"{self.master_key}:{phone_number}".encode('utf-8')
            return kdf.derive(key_material)
        except Exception as e:
            logger.error(f"Key derivation failed: {e}")
            raise CryptographicError(f"Failed to derive signing key: {e}")

    def _xor_encrypt(self, data: bytes, key: bytes) -> bytes:
        key_repeated = (key * ((len(data) // len(key)) + 1))[:len(data)]
        return bytes(a ^ b for a, b in zip(data, key_repeated))

    def generate_contract_verification_code(self, contract_id: str) -> str:
        try:
            content = f"{contract_id}:{datetime.utcnow().date().isoformat()}"
            hash_obj = hashlib.sha256(content.encode('utf-8'))
            hex_hash = hash_obj.hexdigest()
            
            verification_code = hex_hash[:8].upper()
            return f"VC-{verification_code}"
        except Exception as e:
            logger.error(f"Verification code generation failed: {e}")
            raise CryptographicError(f"Failed to generate verification code: {e}")


_crypto_instance = None


def get_crypto_service() -> CryptoService:
    global _crypto_instance
    if _crypto_instance is None:
        _crypto_instance = CryptoService()
    return _crypto_instance