from django.contrib import admin

from .models import FiscalDocument, FiscalSettings


@admin.register(FiscalSettings)
class FiscalSettingsAdmin(admin.ModelAdmin):
    list_display = ("provider", "environment", "municipality", "nfse_enabled", "updated_at")


@admin.register(FiscalDocument)
class FiscalDocumentAdmin(admin.ModelAdmin):
    list_display = ("document_type", "status", "customer_name", "amount", "issue_date", "external_id")
    list_filter = ("document_type", "status", "issue_date")
    search_fields = ("customer_name", "customer_document", "external_id", "description")
