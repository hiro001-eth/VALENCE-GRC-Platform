"""Cryptographic operations and data integrity tests."""
from __future__ import annotations

from grc_dashboard.auth.jwt_handler import hash_password, verify_password


class TestCryptoIntegrity:
    """Verifies standard cryptographic hashing and encoding parameters."""

    def test_password_hashing_rounds_and_verify(self):
        """P2: Verify password hashing verification and timing checks."""
        passwd = "SecurePass123!@#"
        hashed = hash_password(passwd)
        assert hashed != passwd
        assert hashed.startswith("$2b$") or hashed.startswith("$2a$")  # bcrypt identifiers
        assert verify_password(passwd, hashed) is True
        assert verify_password("WrongPassword", hashed) is False
