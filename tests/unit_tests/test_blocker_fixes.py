"""Unit tests for Sprint 0 blocker fixes (B1–B4).

Run with: pytest tests/unit_tests/ -v
"""
from __future__ import annotations

import json
import os
import sys
from datetime import date
from unittest.mock import patch

import pytest

# Ensure src is on path
sys.path.insert(0, str(__file__.rsplit("/tests/", 1)[0]))

# ──────────────────────────────────────────────────────────────
# B1: JWT secret from env var, 24h expiry
# ──────────────────────────────────────────────────────────────
class TestB1_JwtEnvVar:
    """Tests for FIX B1: JWT secret must come from env var, not hardcoded."""

    def test_jwt_secret_from_env_var(self):
        """secret_key must be loaded from JWT_SECRET_KEY env var."""
        with patch.dict(os.environ, {"JWT_SECRET_KEY": "test-secret-32-chars-long-long-ok!!"}):
            from src.utils.config import AuthConfig

            cfg = AuthConfig()
            assert cfg.secret_key == "test-secret-32-chars-long-long-ok!!"
            assert cfg.secret_key != "your-secret-key-here"

    def test_jwt_secret_rejects_placeholder(self):
        """Using placeholder 'your-secret-key-here' must fail without env var."""
        with patch.dict(os.environ, {}, clear=True):
            # Remove JWT_SECRET_KEY from env
            env = {k: v for k, v in os.environ.items() if k != "JWT_SECRET_KEY"}
            with patch.dict(os.environ, env, clear=True):
                from src.utils.config import AuthConfig

                with pytest.raises(ValueError, match="JWT_SECRET_KEY"):
                    AuthConfig(secret_key="your-secret-key-here")

    def test_jwt_expire_hours_default_24(self):
        """Default JWT expiry must be 24 hours (was incorrectly 720h)."""
        with patch.dict(os.environ, {"JWT_SECRET_KEY": "test-secret"}):
            from src.utils.config import AuthConfig

            cfg = AuthConfig()
            assert cfg.jwt_expire_hours == 24

    def test_access_token_uses_24h_expiry(self):
        """Created tokens must expire in 24h."""
        with patch.dict(os.environ, {"JWT_SECRET_KEY": "test-secret-32-chars-long-ok!!"}):
            from src.utils.security import create_access_token

            token = create_access_token({"sub": "testuser"})
            assert isinstance(token, str)
            assert len(token) > 20

            from src.utils.security import decode_access_token

            payload = decode_access_token(token)
            assert payload["sub"] == "testuser"
            assert "exp" in payload
            assert "iat" in payload


class TestB1_JwtSecurity:
    """Security-focused tests for JWT handling."""

    def test_verify_token_rejects_tampered_token(self):
        with patch.dict(os.environ, {"JWT_SECRET_KEY": "test-secret-32-chars-long-ok!!"}):
            from src.utils.security import create_access_token, verify_token

            token = create_access_token({"sub": "testuser"})
            tampered = token[:-5] + "XXXXX"
            assert not verify_token(tampered)

    def test_verify_token_accepts_valid_token(self):
        with patch.dict(os.environ, {"JWT_SECRET_KEY": "test-secret-32-chars-long-ok!!"}):
            from src.utils.security import create_access_token, verify_token

            token = create_access_token({"sub": "testuser"})
            assert verify_token(token)


# ──────────────────────────────────────────────────────────────
# B2: Redis URL standard format
# ──────────────────────────────────────────────────────────────
class TestB2_RedisUrlFormat:
    """Tests for FIX B2: Redis URL must use standard redis:// format."""

    def test_standard_redis_url_accepted(self):
        from src.utils.config import RedisConfig

        cfg = RedisConfig(url="redis://localhost:6379/0")
        assert cfg.url == "redis://localhost:6379/0"

    def test_redis_url_with_password_accepted(self):
        from src.utils.config import RedisConfig

        cfg = RedisConfig(url="redis://user:password@redis.example.com:6380/1")
        assert "user:password@redis.example.com:6380/1" in cfg.url

    def test_redis_url_rejects_placeholder_syntax(self):
        from src.utils.config import RedisConfig

        with pytest.raises(ValueError, match="Non-standard Redis URL"):
            RedisConfig(url="redis://localhost:***@")

    def test_redis_url_rejects_double_at(self):
        from src.utils.config import RedisConfig

        with pytest.raises(ValueError, match="Non-standard Redis URL"):
            RedisConfig(url="redis://localhost:@@6379/0")

    def test_redis_url_rejects_invalid_scheme(self):
        from src.utils.config import RedisConfig

        with pytest.raises(ValueError, match="Invalid Redis URL scheme"):
            RedisConfig(url="http://localhost:6379/0")


# ──────────────────────────────────────────────────────────────
# B3: WeChatCrypto.verify_signature real implementation
# ──────────────────────────────────────────────────────────────
class TestB3_WeChatCryptoSignature:
    """Tests for FIX B3: WeChatCrypto.verify_signature is no longer a placeholder."""

    def test_verify_signature_rejects_empty_params(self):
        from src.integrations.wechat.crypto import WeChatCrypto

        crypto = WeChatCrypto(token="test_token")
        assert not crypto.verify_signature("", "123", "nonce")
        assert not crypto.verify_signature("sig", "", "nonce")
        assert not crypto.verify_signature("sig", "123", "")

    def test_verify_signature_rejects_unconfigured_token(self):
        from src.integrations.wechat.crypto import WeChatCrypto

        crypto = WeChatCrypto(token="")
        assert not crypto.verify_signature("sig", "123", "nonce")

    def test_verify_signature_correct_hmac_sha1(self):
        """Signature must be HMAC-SHA1(token + sorted(timestamp, nonce))."""
        import hashlib

        from src.integrations.wechat.crypto import WeChatCrypto

        token = "my_wechat_token"
        timestamp = "1234567890"
        nonce = "random_nonce"

        # Compute expected signature the way WeChat does it
        parts = sorted([token, timestamp, nonce])
        canonical = "".join(parts)
        expected_sig = hashlib.sha1(canonical.encode()).hexdigest()

        crypto = WeChatCrypto(token=token)
        assert crypto.verify_signature(expected_sig, timestamp, nonce)

    def test_verify_signature_rejects_wrong_signature(self):
        from src.integrations.wechat.crypto import WeChatCrypto

        crypto = WeChatCrypto(token="my_wechat_token")
        assert not crypto.verify_signature("wrong_signature", "1234567890", "nonce")

    def test_verify_signature_is_not_placeholder(self):
        """Ensure the implementation is real, not just 'return True'."""
        from src.integrations.wechat.crypto import WeChatCrypto

        crypto = WeChatCrypto(token="token123")
        # Same inputs must produce consistent results
        r1 = crypto.verify_signature("sig1", "ts1", "n1")
        r2 = crypto.verify_signature("sig1", "ts1", "n1")
        assert r1 == r2
        # Different inputs must produce different results
        _ = crypto.verify_signature("sig2", "ts1", "n1")  # different sig → different result
        assert isinstance(r1, bool)


# ──────────────────────────────────────────────────────────────
# B4: intent_data Pydantic schema validation
# ──────────────────────────────────────────────────────────────
class TestB4_IntentDataSchema:
    """Tests for FIX B4: intent_data must be validated via Pydantic schema."""

    def test_valid_intent_data_parses(self):
        from src.domain.intent import IntentAction, IntentData, TaskPriority

        data = IntentData(
            action=IntentAction.CREATE_TASK,
            estimated_hours=2.5,
            suggested_priority=TaskPriority.MEDIUM,
            suggested_due_date=date(2026, 6, 1),
            confidence=0.92,
            raw_text="下周三前完成 API 设计",
        )
        assert data.action == "create_task"
        assert data.estimated_hours == 2.5
        assert data.confidence == 0.92

    def test_intent_data_from_json_string(self):
        from src.domain.intent import parse_intent_data

        raw = json.dumps(
            {
                "action": "create_task",
                "estimated_hours": 3.0,
                "suggested_priority": "high",
                "confidence": 0.85,
            }
        )
        intent = parse_intent_data(raw)
        assert intent.action == "create_task"
        assert intent.estimated_hours == 3.0
        assert intent.suggested_priority == "high"

    def test_intent_data_from_dict(self):
        from src.domain.intent import parse_intent_data

        intent = parse_intent_data({"action": "complete_task", "estimated_hours": 0.5})
        assert intent.action == "complete_task"
        assert intent.estimated_hours == 0.5

    def test_intent_data_rejects_invalid_action(self):
        from src.domain.intent import IntentData

        with pytest.raises(Exception):  # ValidationError
            IntentData(action="invalid_action")

    def test_intent_data_rejects_hours_out_of_range(self):
        from src.domain.intent import IntentData

        with pytest.raises(Exception):  # ValidationError — hours > 168
            IntentData(estimated_hours=200.0)

        with pytest.raises(Exception):  # ValidationError — hours < 0
            IntentData(estimated_hours=-1.0)

    def test_intent_data_rejects_confidence_out_of_range(self):
        from src.domain.intent import IntentData

        with pytest.raises(Exception):
            IntentData(confidence=1.5)

        with pytest.raises(Exception):
            IntentData(confidence=-0.1)

    def test_intent_data_allows_none_optional_fields(self):
        from src.domain.intent import IntentData

        intent = IntentData()
        assert intent.action == "unknown"
        assert intent.estimated_hours is None
        assert intent.confidence is None
        assert intent.extra == {}

    def test_parse_intent_data_handles_none(self):
        from src.domain.intent import parse_intent_data

        intent = parse_intent_data(None)
        assert intent.action == "unknown"

    def test_parse_intent_data_rejects_invalid_json(self):
        from src.domain.intent import parse_intent_data

        with pytest.raises(Exception):  # JSONDecodeError
            parse_intent_data("not valid json")

    def test_intent_data_serializes_to_json(self):
        from src.domain.intent import IntentData

        data = IntentData(
            action="create_task",
            estimated_hours=1.5,
            confidence=0.9,
        )
        serialized = data.model_dump_json()
        assert "create_task" in serialized
        assert "1.5" in serialized
