from django.contrib import admin

from checkout.models import CheckoutOrder, CheckoutPaymentEvent


@admin.register(CheckoutOrder)
class CheckoutOrderAdmin(admin.ModelAdmin):
    list_display = ("kind", "customer_name", "amount", "status", "provider", "created_at")
    list_filter = ("kind", "status", "provider")
    search_fields = ("customer_name", "customer_email", "customer_phone", "external_reference", "provider_payment_id")


@admin.register(CheckoutPaymentEvent)
class CheckoutPaymentEventAdmin(admin.ModelAdmin):
    list_display = ("provider", "event_type", "order", "processed_at", "created_at")
    list_filter = ("provider", "event_type", "access_token_valid")
    search_fields = ("event_id", "provider_payment_id", "external_reference")
