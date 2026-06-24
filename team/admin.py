from django.contrib import admin

from team.models import Employee, Professional


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ("full_name", "role", "phone", "email", "active")
    list_filter = ("role", "active")
    search_fields = ("full_name", "phone", "email")


@admin.register(Professional)
class ProfessionalAdmin(admin.ModelAdmin):
    list_display = ("full_name", "specialty", "registration_number", "phone", "active")
    list_filter = ("specialty", "active")
    search_fields = ("full_name", "registration_number", "phone", "email")
