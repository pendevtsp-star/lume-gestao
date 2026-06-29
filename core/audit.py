import threading

from django.forms.models import model_to_dict


_state = threading.local()
SENSITIVE_FIELD_PARTS = ("password", "secret", "token", "access_token", "refresh_token")


def set_current_user(user):
    _state.user = user


def get_current_user():
    return getattr(_state, "user", None)


def serialize_value(value):
    if value is None:
        return None
    return str(value)


def is_sensitive_field(field_name):
    lowered = field_name.lower()
    return any(part in lowered for part in SENSITIVE_FIELD_PARTS)


def instance_snapshot(instance):
    data = model_to_dict(instance)
    return {
        key: "***" if is_sensitive_field(key) and value else serialize_value(value)
        for key, value in data.items()
    }
