from dataclasses import dataclass

from django.conf import settings
from django.urls import reverse

from core.integrations.credentials import first_configured_value


@dataclass(frozen=True)
class CheckoutProviderOption:
    code: str
    name: str
    recommended_for: str
    status: str


SUPPORTED_CHECKOUT_PROVIDERS = {
    "asaas": CheckoutProviderOption(
        code="asaas",
        name="Asaas",
        recommended_for="Pix, cartao, boleto, mensalidades e vendas publicas na fase inicial.",
        status="ativo",
    ),
    "iugu": CheckoutProviderOption(
        code="iugu",
        name="iugu",
        recommended_for="Candidato futuro se o custo de Pix em planos menores pesar.",
        status="planejado",
    ),
    "efi": CheckoutProviderOption(
        code="efi",
        name="Efi",
        recommended_for="Candidato futuro para API Pix e negociacao comercial.",
        status="planejado",
    ),
}


def configured_secret(value):
    configured = first_configured_value(value)
    if not configured:
        return False
    lowered = configured.lower()
    placeholders = {"troque", "cole-a-chave", "example", "seudominio", "change-before-production"}
    return not any(marker in lowered for marker in placeholders)


def checkout_provider_code():
    return settings.CHECKOUT_PAYMENT_PROVIDER.lower().strip()


def checkout_provider_option():
    return SUPPORTED_CHECKOUT_PROVIDERS.get(checkout_provider_code())


def get_active_merchant_account():
    from checkout.models import CheckoutMerchantAccount

    return (
        CheckoutMerchantAccount.objects.filter(provider=checkout_provider_code(), active=True)
        .order_by("-created_at")
        .first()
    )


def merchant_account_status():
    merchant = get_active_merchant_account()
    if not merchant:
        return {
            "exists": False,
            "ready": False,
            "label": "Cadastro comercial ainda nao iniciado",
            "status_label": "Pendente",
            "account_type_label": "-",
            "receiver_configured": False,
            "merchant": None,
        }
    return {
        "exists": True,
        "ready": merchant.is_ready,
        "label": merchant.public_receiver_label,
        "status_label": merchant.get_status_display(),
        "account_type_label": merchant.get_account_type_display(),
        "receiver_configured": bool(merchant.provider_wallet_id or merchant.provider_account_id),
        "merchant": merchant,
    }


def checkout_mode_label():
    if settings.ASAAS_DRY_RUN:
        return "Dry-run local"
    if "sandbox" in settings.ASAAS_BASE_URL.lower():
        return "Sandbox Asaas"
    return "Producao Asaas"


def checkout_gateway_status(request=None):
    provider = checkout_provider_option()
    webhook_path = reverse("checkout:asaas_webhook")
    webhook_url = request.build_absolute_uri(webhook_path) if request else webhook_path
    api_key_configured = configured_secret(settings.ASAAS_API_KEY)
    webhook_token_configured = configured_secret(settings.ASAAS_WEBHOOK_TOKEN)
    provider_supported = provider is not None and provider.code == "asaas"
    checkout_enabled = bool(settings.CHECKOUT_ENABLED)
    webhook_enabled = bool(settings.CHECKOUT_WEBHOOK_ENABLED)
    merchant_status = merchant_account_status()
    merchant_required = bool(getattr(settings, "CHECKOUT_REQUIRE_MERCHANT_ACCOUNT", False))
    merchant_ready = merchant_status["ready"] or not merchant_required
    ready_for_remote = provider_supported and not settings.ASAAS_DRY_RUN and api_key_configured and merchant_ready
    ready_for_webhook = provider_supported and webhook_enabled and webhook_token_configured

    if not provider_supported:
        readiness = "unsupported"
    elif settings.ASAAS_DRY_RUN:
        readiness = "dry_run"
    elif ready_for_remote and ready_for_webhook:
        readiness = "ready"
    else:
        readiness = "pending_config"

    return {
        "provider": provider,
        "provider_code": checkout_provider_code(),
        "provider_supported": provider_supported,
        "mode_label": checkout_mode_label(),
        "asaas_base_url": settings.ASAAS_BASE_URL.rstrip("/"),
        "using_sandbox": "sandbox" in settings.ASAAS_BASE_URL.lower(),
        "dry_run": bool(settings.ASAAS_DRY_RUN),
        "checkout_enabled": checkout_enabled,
        "public_enabled": bool(settings.CHECKOUT_PUBLIC_ENABLED),
        "patient_enabled": bool(settings.CHECKOUT_PATIENT_ENABLED),
        "webhook_enabled": webhook_enabled,
        "merchant_required": merchant_required,
        "merchant_account": merchant_status["merchant"],
        "merchant_account_exists": merchant_status["exists"],
        "merchant_account_ready": merchant_status["ready"],
        "merchant_account_label": merchant_status["label"],
        "merchant_status_label": merchant_status["status_label"],
        "merchant_account_type_label": merchant_status["account_type_label"],
        "merchant_receiver_configured": merchant_status["receiver_configured"],
        "api_key_configured": api_key_configured,
        "webhook_token_configured": webhook_token_configured,
        "can_create_remote_payment": ready_for_remote,
        "can_receive_webhook": ready_for_webhook,
        "webhook_url": webhook_url,
        "readiness": readiness,
        "supported_providers": SUPPORTED_CHECKOUT_PROVIDERS.values(),
    }
