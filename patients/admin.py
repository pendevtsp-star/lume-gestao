from django.contrib import admin

from patients.models import Patient, ProfessionalNote, ProfessionalPatientAssignment


@admin.register(Patient)
class PatientAdmin(admin.ModelAdmin):
    list_display = ("full_name", "phone", "email", "active", "updated_at")
    list_filter = ("active",)
    search_fields = ("full_name", "cpf", "phone", "email")


@admin.register(ProfessionalPatientAssignment)
class ProfessionalPatientAssignmentAdmin(admin.ModelAdmin):
    list_display = ("patient", "professional", "active", "updated_at")
    list_filter = ("active", "professional")
    search_fields = ("patient__full_name", "professional__full_name")


@admin.register(ProfessionalNote)
class ProfessionalNoteAdmin(admin.ModelAdmin):
    list_display = ("title", "patient", "professional", "record_type", "session_focus", "created_at")
    list_filter = ("professional", "record_type", "session_focus")
    search_fields = ("title", "objective", "body", "patient__full_name", "professional__full_name")
