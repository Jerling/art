"""WeChat webhook handler.

GET  /wechat/webhook  — URL verification (echostr)
POST /wechat/webhook  — receive encrypted XML message, verify, decrypt, parse
"""
from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from typing import Any

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.integrations.wechat.crypto import WeChatCrypto, get_wechat_config
from src.services.intent import IntentService
from src.services.task import TaskService
from src.services.wechat_push import WeChatPushService
from src.storage.database import get_session
from src.storage.wechat_message import WeChatMessageStore

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/wechat", tags=["wechat"])


# ─────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────


def _build_crypto() -> WeChatCrypto:
    """Build a WeChatCrypto instance from config token."""
    cfg = get_wechat_config()
    return WeChatCrypto(token=cfg.token if cfg else "")


def _parse_xml_message(xml_body: bytes) -> dict[str, Any]:
    """Parse a WeChat XML message into a dict.

    Expected fields: ToUserName, FromUserName, MsgType, Content, MsgId
    """
    try:
        root = ET.fromstring(xml_body)
        return {child.tag: child.text for child in root}
    except ET.ParseError as exc:
        logger.warning("Failed to parse WeChat XML message: %s", exc)
        return {}


# ─────────────────────────────────────────────────────────────────
# GET /wechat/webhook — URL verification
# ─────────────────────────────────────────────────────────────────


@router.get(
    "/webhook",
    response_class=PlainTextResponse,
    summary="WeChat URL verification",
    description=(
        "WeChat calls this endpoint to verify the webhook URL during backend "
        "configuration. It passes signature, timestamp, nonce, and echostr. "
        "We verify the signature and return the decrypted echostr."
    ),
)
async def verify_wechat_webhook(
    signature: str = Query(..., description="WeChat signature"),
    timestamp: str = Query(..., description="Unix timestamp"),
    nonce: str = Query(..., description="Random nonce"),
    echostr: str = Query(..., description="Encrypted challenge string"),
) -> str:
    """Handle GET /wechat/webhook — verify signature and return echostr."""
    crypto = _build_crypto()

    if not crypto.verify_signature(signature, timestamp, nonce):
        logger.warning(
            "WeChat URL verification failed: invalid signature "
            "(sig=%s..., ts=%s, nonce=%s)",
            signature[:8],
            timestamp,
            nonce,
        )
        # WeChat expects a specific plain-text response; return empty on failure
        return ""

    # Signature valid — decrypt and return the echostr
    echo = crypto.get_echo_str(echostr, timestamp, nonce)
    if not echo:
        logger.warning("WeChat echostr decryption returned empty")
        return ""

    logger.info("WeChat URL verification succeeded")
    return echo


# ─────────────────────────────────────────────────────────────────
# POST /wechat/webhook — receive encrypted message
# ─────────────────────────────────────────────────────────────────


@router.post(
    "/webhook",
    response_class=Response,
    summary="WeChat message webhook",
    description=(
        "WeChat POSTs an encrypted XML message to this endpoint. "
        "We verify the signature, decrypt the payload, and parse the "
        "XML fields: ToUserName, FromUserName, MsgType, Content, MsgId."
    ),
)
async def receive_wechat_message(
    request: Request,
    session: AsyncSession = Depends(get_session),
    msg_signature: str = Query(..., alias="msg_signature", description="Message signature"),
    timestamp: str = Query(..., description="Unix timestamp"),
    nonce: str = Query(..., description="Random nonce"),
    encrypt_type: str | None = Query(None, alias="encrypt_type"),
) -> Response:
    """Handle POST /wechat/webhook — verify, decrypt, and parse the message.

    WeChat expects an empty 200 response after processing.
    """
    crypto = _build_crypto()

    # Read raw body for signature verification (must be read before parsing)
    body_bytes = await request.body()
    body_str = body_bytes.decode("utf-8") if body_bytes else ""

    # ── Signature verification ──────────────────────────────────
    # The signature for POST messages uses msg_signature param and the
    # encrypt field from the XML body if present.
    # When encrypt_type == "aes", the entire <xml><Encrypt>...</Encrypt></xml>
    # is what gets included in the signature computation alongside
    # token + timestamp + nonce.
    encrypt_value = ""
    if encrypt_type == "aes":
        # Extract <Encrypt> tag from the XML body for signature verification
        msg_dict = _parse_xml_message(body_bytes)
        encrypt_value = msg_dict.get("Encrypt", "")

    if not crypto.verify_signature(
        msg_signature, timestamp, nonce, encrypt=encrypt_value
    ):
        logger.warning(
            "WeChat message signature verification failed: "
            "(sig=%s..., ts=%s, nonce=%s, encrypt_type=%s)",
            msg_signature[:8],
            timestamp,
            nonce,
            encrypt_type,
        )
        return Response(status_code=200, content="")

    # ── Decrypt and parse message ───────────────────────────────
    if encrypt_type == "aes" and encrypt_value:
        # Decrypt the encrypted message using AES-256-CBC
        # crypto.get_echo_str() returns the decrypted content for the echostr;
        # for a general encrypted message we use the same AES logic but
        # extract the msg portion differently.
        decrypted_xml = _decrypt_encrypted_msg(encrypt_value, timestamp, nonce)
        if not decrypted_xml:
            logger.warning("WeChat message decryption failed")
            return Response(status_code=200, content="")
        msg_dict = _parse_xml_message(decrypted_xml.encode("utf-8"))
    else:
        # Plaintext mode — parse body directly
        msg_dict = _parse_xml_message(body_bytes)

    to_user = msg_dict.get("ToUserName", "")
    from_user = msg_dict.get("FromUserName", "")
    msg_type = msg_dict.get("MsgType", "")
    content = msg_dict.get("Content", "")
    msg_id = msg_dict.get("MsgId", "")

    logger.info(
        "WeChat message received: from=%s type=%s content=%r msg_id=%s",
        from_user,
        msg_type,
        content[:80] if content else "",
        msg_id,
    )

    # ── Persist message to DB (signature already verified by this point) ──
    from datetime import datetime
    try:
        store = WeChatMessageStore(session)
        # WeChat CreateTime is a Unix timestamp string
        create_time_str = msg_dict.get("CreateTime", "")
        if create_time_str and create_time_str.isdigit():
            create_time_dt = datetime.fromtimestamp(int(create_time_str))
        else:
            create_time_dt = datetime.now()

        await store.save(
            from_user=from_user,
            to_user=to_user,
            msg_type=msg_type,
            content=content or None,
            msg_id=msg_id or None,
            create_time=create_time_dt,
            raw_xml=body_str[:4000] if body_str else None,
        )
        logger.info("WeChat message persisted: msg_id=%s", msg_id)
    except Exception as exc:
        # Log but don't fail the 200 — WeChat expects empty response
        logger.error("Failed to persist WeChat message: %s", exc)

    # ── Intent processing + WeChat push ──────────────────────────
    # WeChat expects an empty 200 response immediately, so the
    # intent processing and push happen after we've already committed
    # the message to the DB. We do it synchronously but with error
    # isolation so any failure doesn't affect the 200 response.
    push_service = WeChatPushService()
    try:
        task_service = TaskService(session)
        intent_service = IntentService(task_service)
        result = await intent_service.process_message(
            content or "", from_user
        )

        if result.reply_text:
            push_result = await push_service.send_text(
                openid=from_user, text=result.reply_text
            )
            if not push_result.success:
                logger.warning(
                    "WeChat push failed for openid=%s: %s",
                    from_user,
                    push_result.error,
                )
    except Exception as exc:
        # Log but don't fail the 200 — WeChat expects empty response
        logger.error("WeChat intent processing error: %s", exc)
    finally:
        await push_service.close()

    return Response(status_code=200, content="")


# ─────────────────────────────────────────────────────────────────
# AES decryption for encrypted WeChat messages
# ─────────────────────────────────────────────────────────────────


def _decrypt_encrypted_msg(encrypt: str, timestamp: str, nonce: str) -> str:
    """Decrypt a WeChat encrypted message body.

    WeChat encrypts messages using AES-256-CBC with the following format:
      Base64(iv || ciphertext)

    Decryption steps:
      1. Base64 decode
      2. Extract 16-byte IV prefix
      3. AES-256-CBC decrypt
      4. Strip PKCS7 padding
      5. Skip 16-byte random IV, extract msg_len (4 bytes LE), return msg
    """
    import base64
    import struct

    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    cfg = get_wechat_config()
    if not cfg or not cfg.aes_key:
        logger.error("WeChat AES key not configured")
        return ""

    try:
        aes_key_bytes = base64.b64decode(cfg.aes_key + "=")
    except Exception as exc:
        logger.error("Failed to decode WeChat AES key: %s", exc)
        return ""

    try:
        encrypted_bytes = base64.b64decode(encrypt)
        iv = encrypted_bytes[:16]
        cipher_text = encrypted_bytes[16:]

        cipher = Cipher(
            algorithms.AES(aes_key_bytes),
            modes.CBC(iv),
            backend=default_backend(),
        )
        decryptor = cipher.decryptor()
        padded = decryptor.update(cipher_text) + decryptor.finalize()

        # Remove PKCS7 padding
        pad_len = padded[-1]
        content = padded[:-pad_len]

        # Skip 16-byte random IV, read msg_len (4 bytes LE at offset 16),
        # then msg starts at offset 20.
        msg_len = struct.unpack_from("<I", content, 16)[0]
        msg_start = 20
        msg_bytes = content[msg_start : msg_start + msg_len]

        return msg_bytes.decode("utf-8", errors="replace")
    except Exception as exc:
        logger.error("Failed to decrypt WeChat message: %s", exc)
        return ""
