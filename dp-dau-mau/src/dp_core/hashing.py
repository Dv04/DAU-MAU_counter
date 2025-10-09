"""Hashing utilities for user identifiers with salt rotation support."""

from __future__ import annotations

import base64
import datetime as dt
import hmac
import os
from dataclasses import dataclass
from hashlib import sha256
from typing import Optional

from .config import AppConfig


def _ensure_secret_bytes(secret: str) -> bytes:
    if secret.startswith("b64:"):
        return base64.b64decode(secret[4:])
    return secret.encode("utf-8")


@dataclass(slots=True)
class SaltManager:
    """Derives per-day salts based on a rotation cadence."""

    secret: str
    rotation_days: int

    def salt_for_day(self, day: dt.date) -> bytes:
        rotation_epoch = day.toordinal() // max(self.rotation_days, 1)
        message = f"{day.isoformat()}::{rotation_epoch}".encode("utf-8")
        secret_bytes = _ensure_secret_bytes(self.secret)
        digest = hmac.new(secret_bytes, message, sha256).digest()
        return digest

    def rotate_secret(self, new_secret: str) -> "SaltManager":
        return SaltManager(secret=new_secret, rotation_days=self.rotation_days)


def hash_user_id(user_id: str, day: dt.date, config: AppConfig) -> bytes:
    """Hash a raw user identifier into a privacy-preserving key."""

    manager = SaltManager(
        secret=config.security.hash_salt_secret,
        rotation_days=config.security.hash_salt_rotation_days,
    )
    salt = manager.salt_for_day(day)
    digest = hmac.new(salt, user_id.encode("utf-8"), sha256).digest()
    return digest


def hash_user_root(user_id: str, config: AppConfig) -> bytes:
    """Derive a root hash used to index erasure records across days."""

    secret_bytes = _ensure_secret_bytes(config.security.hash_salt_secret)
    digest = hmac.new(secret_bytes, user_id.encode("utf-8"), sha256).digest()
    return digest


def generate_random_secret() -> str:
    """Convenience helper for local development to mint a new HMAC secret."""

    return "b64:" + base64.b64encode(os.urandom(32)).decode("utf-8")


def truncate_key(key: bytes, length: Optional[int] = None) -> bytes:
    """Truncate hashed keys to the desired length for sketches."""

    if length is None:
        return key
    return key[:length]
