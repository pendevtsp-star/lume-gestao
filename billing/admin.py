from django.contrib import admin

from billing.models import Membership, Payment, ServicePlan


@admin.register(ServicePlan)
class ServicePlanAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "monthly_price", "sessions_per_week", "active")
    list_filter = ("category", "active")
    search_fields = ("name", "description")


@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    list_display = ("patient", "plan", "status", "due_day", "monthly_amount")
    list_filter = ("status", "plan")
    search_fields = ("patient__full_name", "plan__name")


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("membership", "reference_month", "due_date", "amount", "status", "method")
    list_filter = ("status", "method", "due_date")
    search_fields = ("membership__patient__full_name", "membership__plan__name")
