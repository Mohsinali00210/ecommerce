"""
Encryption for courier secrets stored in the database.

Uses Fernet (AES-128-CBC + HMAC) from the `cryptography` package.
The key comes from settings.COURIER_ENCRYPTION_KEY (a Fernet key, see README).
If it is not set, a key is derived from SECRET_KEY so development still works,
but production should set its own key: rotating SECRET_KEY would otherwise make
stored credentials unreadable.
"""
import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.db import models

PREFIX = "enc$"


def _fernet():
    key = getattr(settings, "COURIER_ENCRYPTION_KEY", "") or ""
    if not key:
        digest = hashlib.sha256(("couriers:" + settings.SECRET_KEY).encode()).digest()
        key = base64.urlsafe_b64encode(digest).decode()
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt(value):
    if value in (None, ""):
        return value
    if isinstance(value, str) and value.startswith(PREFIX):
        return value  # already encrypted
    return PREFIX + _fernet().encrypt(str(value).encode()).decode()


def decrypt(value):
    if value in (None, ""):
        return value
    if not isinstance(value, str) or not value.startswith(PREFIX):
        return value  # plain value (e.g. legacy row) - return as is
    try:
        return _fernet().decrypt(value[len(PREFIX):].encode()).decode()
    except InvalidToken:
        raise ValueError(
            "Cannot decrypt courier credential. COURIER_ENCRYPTION_KEY (or SECRET_KEY) changed "
            "since it was saved - re-enter the credential in Couriers > Settings."
        )


class EncryptedTextField(models.TextField):
    """TextField that is encrypted at rest and decrypted when loaded."""

    def from_db_value(self, value, expression, connection):
        return decrypt(value)

    def to_python(self, value):
        return decrypt(value) if isinstance(value, str) else value

    def get_prep_value(self, value):
        value = super().get_prep_value(value)
        return encrypt(value)
