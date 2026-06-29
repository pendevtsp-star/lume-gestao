from django.conf import settings


def homecare_enabled():
    return bool(settings.HOMECARE_ENABLED)


def homecare_internal_enabled():
    return bool(settings.HOMECARE_ENABLED and settings.HOMECARE_INTERNAL_ENABLED)


def homecare_public_enabled():
    return bool(settings.HOMECARE_ENABLED and settings.HOMECARE_PUBLIC_ENABLED)


def homecare_checkout_enabled():
    return bool(settings.HOMECARE_ENABLED and settings.HOMECARE_PUBLIC_ENABLED and settings.HOMECARE_CHECKOUT_ENABLED)


def homecare_webhook_enabled():
    return bool(settings.HOMECARE_ENABLED and settings.HOMECARE_WEBHOOK_ENABLED)
