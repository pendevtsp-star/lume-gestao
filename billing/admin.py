from django.contrib import admin

from billing.models import CashClosing, Charge, Expense, ExpenseCategory, Membership, Payment, ServicePlan


@admin.register(ServicePlan)
class ServicePlanAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "delivery_mode", "grants_homecare_access", "monthly_price", "sessions_per_week", "active")
    list_filter = ("category", "delivery_mode", "grants_homecare_access", "active")
    search_fields = ("name", "description")


@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    list_display = ("patient", "plan", "status", "due_day", "monthly_amount")
    list_filter = ("status", "plan")
    search_fields = ("patient__full_name", "plan__name")


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("patient", "item_type", "description", "membership", "reference_month", "due_date", "amount", "status", "method")
    list_filter = ("item_type", "status", "method", "due_date")
    search_fields = ("patient__full_name", "description", "membership__patient__full_name", "membership__plan__name")


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = ("description", "category", "kind", "due_date", "amount", "status")
    list_filter = ("category", "kind", "status", "due_date")
    search_fields = ("description",)


@admin.register(ExpenseCategory)
class ExpenseCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "kind", "active")
    list_filter = ("kind", "active")
    search_fields = ("name",)


@admin.register(Charge)
class ChargeAdmin(admin.ModelAdmin):
    list_display = ("description", "patient", "due_date", "amount", "status")
    list_filter = ("status", "due_date")
    search_fields = ("description", "patient__full_name")


@admin.register(CashClosing)
class CashClosingAdmin(admin.ModelAdmin):
    list_display = ("date", "payments_total", "charges_total", "expenses_total", "cash_expected", "cash_counted", "closed_by", "closed_at")
    list_filter = ("date", "closed_at")
    search_fields = ("notes", "closed_by__username")
