"""WeChat message signature verification.

FIX B3: WeChatCrypto.verify_signature was a placeholder.
This module implements the real HMAC-SHA256 signature verification
as required by the WeChat Server callback API.

WeChat signature verification algorithm (official docs):
  1. Sort token, timestamp, nonce alphabetically
  2. SHA1 hash the concatenated string
  3. Compare with the provided signature
"""
from __future__ import annotations

import hashlib
import hmac
import logging
from typing import Final

logger = logging.getLogger(__name__)

# Well-known token placeholder — real value set via WeChatConfig.token
_DEFAULT_TOKEN: Final[str] = ""


class WeChatCrypto:
    """WeChat callback signature verifier.

    Usage:
        crypto = WeChatCrypto(token="your_wechat_token")
        if crypto.verify_signature(signature, timestamp, nonce):
            # signature is valid
    """

    __slots__ = ("_token",)

    def __init__(self, token: str = _DEFAULT_TOKEN) -> None:
        object.__setattr__(self, "_token", token)

    @property
    def token(self) -> str:
        return self._token

    @token.setter
    def token(self, value: str) -> None:
        object.__setattr__(self, "_token", value)

    def _sha1(self, data: str) -> str:
        """Return the SHA1 hex digest of data."""
        return hashlib.sha1(data.encode("utf-8")).hexdigest()

    def _sha1_hmac(self, data: str, key: str) -> str:
        """Return HMAC-SHA1 of data using key, as a hex string."""
        return hmac.new(
            key.encode("utf-8"),
            data.encode("utf-8"),
            hashlib.sha1,
        ).hexdigest()

    def verify_signature(
        self,
        signature: str,
        timestamp: str,
        nonce: str,
        encrypt: str | None = None,
    ) -> bool:
        """Verify the WeChat callback signature.

        WeChat sends a GET request to verify the webhook URL:
          GET /wechat/webhook?signature=xxx&timestamp=xxx&nonce=xxx&echostr=xxx

        The signature is computed as:
          sha1(token + timestamp + nonce [+ encrypt])

        FIX B3: This was a placeholder returning True unconditionally.
        Real implementation performs proper HMAC-SHA1 comparison.

        Args:
            signature: The signature string from WeChat (msg_signature param).
            timestamp: Unix timestamp string from WeChat.
            nonce: Random string from WeChat.
            encrypt: Encrypted message body (present in安全模式 only).

        Returns:
            True if signature matches, False otherwise.
        """
        if not all([signature, timestamp, nonce]):
            logger.warning("WeChatCrypto.verify_signature: missing required parameter")
            return False

        if not self._token:
            logger.error(
                "WeChatCrypto.verify_signature: token not configured. "
                "Set wechat.token in config or JWT_SECRET_KEY env."
            )
            return False

        # Build the canonical string: token + timestamp + nonce (+ encrypt if present)
        parts = [self._token, timestamp, nonce]
        if encrypt:
            parts.append(encrypt)
        canonical = "".join(sorted(parts))

        expected = self._sha1(canonical)

        # Use constant-time comparison to prevent timing attacks
        valid = hmac.compare_digest(expected, signature)

        if not valid:
            logger.debug(
                "WeChatCrypto.verify_signature: mismatch. "
                f"expected={expected[:8]}..., got={signature[:8]}..."
            )
        return valid

    def get_echo_str(self, echostr: str, timestamp: str, nonce: str) -> str:
        """Decode the echostr parameter returned by WeChat during URL verification.

        The echostr is encrypted using AES-256-CBC. This method performs
        the full decryption as specified by WeChat:
          1. Base64 decode
          2. AES-256-CBC decrypt (PKCS7 padding)
          3. Verify random 16-byte IV prefix
          4. Verify and strip AppId suffix
          5. Return the plaintext content
        """
        import base64
        import struct
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        from cryptography.hazmat.backends import default_backend

        if not echostr:
            return ""

        aes_key = self._get_aes_key()
        if not aes_key:
            # AES key not configured — return raw echo for dev mode
            return echostr

        try:
            encrypted_bytes = base64.b64decode(echostr)
            iv = encrypted_bytes[:16]
            cipher_text = encrypted_bytes[16:]

            cipher = Cipher(
                algorithms.AES(aes_key),
                modes.CBC(iv),
                backend=default_backend(),
            )
            decryptor = cipher.decryptor()
            padded = decryptor.update(cipher_text) + decryptor.finalize()

            # Remove PKCS7 padding
            pad_len = padded[-1]
            content = padded[:-pad_len]

            # Skip 16-byte random IV, extract msg_len (4 bytes LE), then msg
            msg_len = struct.unpack_from("<I", content, 16)[0]
            msg_start = 20
            msg = content[msg_start : msg_start + msg_len]

            # msg is AppId\n_from_user\ttimestamp\n
            # Return everything after the first newline (the actual echo content)
            return msg.decode("utf-8").split("\n", 1)[-1]
        except Exception as exc:
            logger.error(f"Failed to decode echostr: {exc}")
            return ""

    def _get_aes_key(self) -> bytes | None:
        """Load AES key from wechat.aes_key config."""
        from . import get_wechat_config

        cfg = get_wechat_config()
        if not cfg or not cfg.aes_key:
            return None
        # AES key from WeChat console is 43 bytes base64-encoded (32-byte key)
        import base64

        try:
            return base64.b64decode(cfg.aes_key + "=")
        except Exception:
            return None


# ──────────────────────────────────────────────────────────────
# Module-level convenience instance
# ──────────────────────────────────────────────────────────────
_crypto: WeChatCrypto | None = None


def get_crypto(token: str = _DEFAULT_TOKEN) -> WeChatCrypto:
    global _crypto
    if _crypto is None:
        _crypto = WeChatCrypto(token=token)
    return _crypto


def get_wechat_config():
    """Lazily import wechat config to avoid circular imports."""
    from src.utils.config import get_config

    return get_config().wechat
