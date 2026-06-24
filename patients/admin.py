from django.contrib import admin

from patients.models import Patient


@admin.register(Patient)
class PatientAdmin(admin.ModelAdmin):
    list_display = ("full_name", "phone", "email", "active", "updated_at")
    list_filter = ("active",)
    search_fields = ("full_name", "cpf", "phone", "email")
