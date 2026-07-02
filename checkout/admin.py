from django.contrib import admin

from checkout.models import CheckoutMerchantAccount, CheckoutOrder, CheckoutPaymentEvent


@admin.register(CheckoutMerchantAccount)
class CheckoutMerchantAccountAdmin(admin.ModelAdmin):
    list_display = ("public_receiver_label", "provider", "account_type", "status", "active", "updated_at")
    list_filter = ("provider", "account_type", "status", "active")
    search_fields = ("legal_name", "trade_name", "document", "email", "provider_account_id", "provider_wallet_id")
    readonly_fields = ("created_at", "updated_at")


@admin.register(CheckoutOrder)
class CheckoutOrderAdmin(admin.ModelAdmin):
    list_display = ("kind", "customer_name", "amount", "status", "provider", "merchant_account", "created_at")
    list_filter = ("kind", "status", "provider", "merchant_account")
    search_fields = ("customer_name", "customer_email", "customer_phone", "external_reference", "provider_payment_id")


@admin.register(CheckoutPaymentEvent)
class CheckoutPaymentEventAdmin(admin.ModelAdmin):
    list_display = ("provider", "event_type", "order", "processed_at", "created_at")
    list_filter = ("provider", "event_type", "access_token_valid")
    search_fields = ("event_id", "provider_payment_id", "external_reference")
