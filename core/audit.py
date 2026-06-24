import threading

from django.forms.models import model_to_dict


_state = threading.local()


def set_current_user(user):
    _state.user = user


def get_current_user():
    return getattr(_state, "user", None)


def serialize_value(value):
    if value is None:
        return None
    return str(value)


def instance_snapshot(instance):
    data = model_to_dict(instance)
    return {key: serialize_value(value) for key, value in data.items()}
