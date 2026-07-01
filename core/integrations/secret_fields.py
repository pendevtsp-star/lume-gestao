import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings


ENCRYPTED_PREFIX = "fernet:"


def encryption_configured():
    return bool(str(settings.LUME_FIELD_ENCRYPTION_KEY or "").strip())


def _fernet():
    raw_key = str(settings.LUME_FIELD_ENCRYPTION_KEY or "").strip()
    if not raw_key:
        return None
    try:
        return Fernet(raw_key.encode("utf-8"))
    except ValueError:
        derived_key = base64.urlsafe_b64encode(hashlib.sha256(raw_key.encode("utf-8")).digest())
        return Fernet(derived_key)


def encrypt_secret(value):
    value = str(value or "").strip()
    if not value:
        return ""
    if value.startswith(ENCRYPTED_PREFIX):
        return value
    cipher = _fernet()
    if cipher is None:
        raise ValueError("Configure LUME_FIELD_ENCRYPTION_KEY antes de salvar tokens do WhatsApp.")
    return f"{ENCRYPTED_PREFIX}{cipher.encrypt(value.encode('utf-8')).decode('utf-8')}"


def decrypt_secret(value):
    value = str(value or "").strip()
    if not value:
        return ""
    if not value.startswith(ENCRYPTED_PREFIX):
        return value
    cipher = _fernet()
    if cipher is None:
        raise ValueError("LUME_FIELD_ENCRYPTION_KEY ausente; nao foi possivel ler o token do WhatsApp.")
    encrypted_value = value[len(ENCRYPTED_PREFIX) :].encode("utf-8")
    try:
        return cipher.decrypt(encrypted_value).decode("utf-8")
    except InvalidToken as exc:
        raise ValueError("LUME_FIELD_ENCRYPTION_KEY nao corresponde ao token salvo do WhatsApp.") from exc


def is_encrypted_secret(value):
    return str(value or "").strip().startswith(ENCRYPTED_PREFIX)
