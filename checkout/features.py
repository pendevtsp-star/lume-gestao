from django.conf import settings


def checkout_enabled():
    return bool(settings.CHECKOUT_ENABLED)


def checkout_public_enabled():
    return bool(settings.CHECKOUT_ENABLED and settings.CHECKOUT_PUBLIC_ENABLED)


def checkout_patient_enabled():
    return bool(settings.CHECKOUT_ENABLED and settings.CHECKOUT_PATIENT_ENABLED)


def checkout_webhook_enabled():
    return bool(settings.CHECKOUT_ENABLED and settings.CHECKOUT_WEBHOOK_ENABLED)
