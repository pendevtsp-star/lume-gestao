from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Sum
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.utils.decorators import method_decorator
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import DetailView, FormView, ListView, TemplateView, View

from accounts.permissions import FinanceAccessMixin, get_profile
from billing.models import Membership, Payment, ServicePlan
from checkout.features import checkout_enabled, checkout_patient_enabled, checkout_public_enabled, checkout_webhook_enabled
from checkout.forms import CheckoutMerchantAccountForm, PublicPlanCheckoutForm
from checkout.models import CheckoutMerchantAccount
from checkout.models import CheckoutOrder
from checkout.models import CheckoutPaymentEvent
from checkout.providers import checkout_gateway_status
from checkout.services import parse_asaas_payload, record_asaas_checkout_webhook, start_checkout_order
from core.integrations.http import IntegrationError
from core.views import SearchableListView
from scheduling.models import Appointment, ServicePackage, ServiceUsage


class CheckoutFeatureMixin:
    required_feature = "public"

    def dispatch(self, request, *args, **kwargs):
        if self.required_feature == "public" and not checkout_public_enabled():
            return self.feature_disabled_response()
        if self.required_feature == "patient" and not checkout_patient_enabled():
            return self.feature_disabled_response()
        if self.required_feature == "any" and not checkout_enabled():
            return self.feature_disabled_response()
        return super().dispatch(request, *args, **kwargs)

    def feature_disabled_response(self):
        messages.info(self.request, "Checkout em homologacao. A compra online ainda nao esta liberada.")
        return redirect("/")


class CheckoutDashboardView(FinanceAccessMixin, TemplateView):
    template_name = "checkout/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        orders = CheckoutOrder.objects.all()
        pending_payments = Payment.objects.filter(status__in=[Payment.Status.PENDING, Payment.Status.OVERDUE])
        pending_amount = orders.filter(status=CheckoutOrder.Status.PENDING).aggregate(total=Sum("amount"))["total"] or 0
        paid_amount = orders.filter(status=CheckoutOrder.Status.PAID).aggregate(total=Sum("amount"))["total"] or 0
        context.update(
            {
                "gateway": checkout_gateway_status(self.request),
                "order_count": orders.count(),
                "pending_order_count": orders.filter(status=CheckoutOrder.Status.PENDING).count(),
                "paid_order_count": orders.filter(status=CheckoutOrder.Status.PAID).count(),
                "failed_order_count": orders.filter(status__in=[CheckoutOrder.Status.FAILED, CheckoutOrder.Status.CANCELED]).count(),
                "pending_amount": pending_amount,
                "paid_amount": paid_amount,
                "pending_patient_payments": pending_payments.count(),
                "public_plan_count": ServicePlan.objects.filter(active=True, show_on_website=True).count(),
                "recent_orders": orders.select_related("patient", "plan", "payment", "merchant_account")[:6],
                "recent_events": CheckoutPaymentEvent.objects.select_related("order")[:6],
            }
        )
        return context


class CheckoutMerchantAccountOnboardingView(FinanceAccessMixin, FormView):
    template_name = "checkout/merchant_onboarding.html"
    form_class = CheckoutMerchantAccountForm

    def get_merchant_account(self):
        if not hasattr(self, "_merchant_account"):
            self._merchant_account = (
                CheckoutMerchantAccount.objects.filter(
                    provider=CheckoutMerchantAccount.Provider.ASAAS,
                    active=True,
                )
                .order_by("-created_at")
                .first()
            )
        return self._merchant_account

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["instance"] = self.get_merchant_account()
        return kwargs

    def form_valid(self, form):
        merchant_account = form.save(commit=False)
        if not merchant_account.pk:
            merchant_account.provider = CheckoutMerchantAccount.Provider.ASAAS
            merchant_account.account_type = CheckoutMerchantAccount.AccountType.SUBACCOUNT
            merchant_account.active = True
        if "submit_for_review" in self.request.POST and not merchant_account.is_ready:
            merchant_account.status = CheckoutMerchantAccount.Status.PENDING_PROVIDER
            merchant_account.onboarding_started_at = merchant_account.onboarding_started_at or timezone.now()
            message = (
                "Cadastro financeiro salvo e marcado para analise. "
                "Na proxima etapa, vamos sincronizar esses dados com o Asaas sandbox."
            )
        else:
            if merchant_account.status == CheckoutMerchantAccount.Status.NOT_STARTED:
                merchant_account.status = CheckoutMerchantAccount.Status.DRAFT
            message = "Cadastro financeiro salvo como rascunho."
        merchant_account.save()
        messages.success(self.request, message)
        return redirect("checkout:merchant_onboarding")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        merchant_account = self.get_merchant_account()
        context.update(
            {
                "merchant_account": merchant_account,
                "gateway": checkout_gateway_status(self.request),
            }
        )
        return context


class PublicPlanCheckoutView(CheckoutFeatureMixin, FormView):
    template_name = "checkout/public_plan_checkout.html"
    form_class = PublicPlanCheckoutForm
    required_feature = "public"

    def dispatch(self, request, *args, **kwargs):
        self.plan = get_object_or_404(
            ServicePlan,
            pk=kwargs["pk"],
            active=True,
            show_on_website=True,
        )
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        order = CheckoutOrder.objects.create(
            kind=CheckoutOrder.Kind.SERVICE_PLAN,
            plan=self.plan,
            customer_name=form.cleaned_data["full_name"],
            customer_document=form.cleaned_data["cpf"],
            customer_birth_date=form.cleaned_data["birth_date"],
            customer_email=form.cleaned_data["email"],
            customer_phone=form.cleaned_data["phone"],
            amount=self.plan.monthly_price,
        )
        try:
            start_checkout_order(order)
        except IntegrationError as exc:
            order.status = CheckoutOrder.Status.FAILED
            order.notes = f"Falha ao iniciar checkout: {exc}"
            order.save(update_fields=["status", "notes", "updated_at"])
            messages.error(self.request, str(exc))
            return redirect("checkout:plan", pk=self.plan.pk)
        if order.checkout_url:
            return redirect(order.checkout_url)
        return redirect("checkout:status", reference=order.external_reference)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "plan": self.plan,
                "page_title": f"Comprar {self.plan.name}",
                "browser_title": f"Comprar {self.plan.name} | Lume",
            }
        )
        return context


class CheckoutStatusView(DetailView):
    model = CheckoutOrder
    template_name = "checkout/status.html"
    context_object_name = "order"
    slug_field = "external_reference"
    slug_url_kwarg = "reference"


class PatientPaymentListView(CheckoutFeatureMixin, LoginRequiredMixin, ListView):
    login_url = "/login/"
    template_name = "checkout/patient_payments.html"
    context_object_name = "payments"
    required_feature = "patient"

    def get_queryset(self):
        profile = get_profile(self.request.user)
        if not profile or not profile.patient_id:
            return Payment.objects.none()
        return (
            Payment.objects.select_related("membership__plan", "membership__patient")
            .filter(
                membership__patient=profile.patient,
                status__in=[Payment.Status.PENDING, Payment.Status.OVERDUE],
            )
            .order_by("due_date")
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        profile = get_profile(self.request.user)
        if not profile or not profile.patient_id:
            return context
        patient = profile.patient
        active_memberships = Membership.objects.filter(patient=patient, status=Membership.Status.ACTIVE).select_related("plan")
        active_packages = ServicePackage.objects.filter(
            membership__patient=patient,
            status=ServicePackage.Status.ACTIVE,
        ).select_related("membership__plan")
        active_credit_total = sum(package.remaining_sessions for package in active_packages)
        context.update(
            {
                "patient": patient,
                "pending_payments": context["payments"],
                "paid_payments": Payment.objects.filter(
                    membership__patient=patient,
                    status=Payment.Status.PAID,
                )
                .select_related("membership__plan")
                .order_by("-paid_at", "-created_at")[:8],
                "active_memberships": active_memberships,
                "active_packages": active_packages,
                "active_credit_total": active_credit_total,
                "upcoming_appointments": Appointment.objects.filter(
                    patient=patient,
                    starts_at__gte=timezone.now(),
                    status__in=[Appointment.Status.REQUESTED, Appointment.Status.SCHEDULED],
                )
                .select_related("professional", "service_plan")
                .order_by("starts_at")[:6],
                "recent_usages": ServiceUsage.objects.filter(service_package__membership__patient=patient)
                .select_related("service_package__membership__plan", "appointment__professional")
                .order_by("-registered_at")[:6],
            }
        )
        return context


class PatientPaymentStartView(CheckoutFeatureMixin, LoginRequiredMixin, View):
    login_url = "/login/"
    required_feature = "patient"

    def post(self, request, pk):
        profile = get_profile(request.user)
        if not profile or not profile.patient_id:
            raise Http404
        payment = get_object_or_404(
            Payment.objects.select_related("membership__patient", "membership__plan"),
            pk=pk,
            membership__patient=profile.patient,
            status__in=[Payment.Status.PENDING, Payment.Status.OVERDUE],
        )
        patient = payment.membership.patient
        order = CheckoutOrder.objects.create(
            kind=CheckoutOrder.Kind.PAYMENT,
            patient=patient,
            plan=payment.membership.plan,
            payment=payment,
            customer_name=patient.full_name,
            customer_document=patient.cpf or "",
            customer_birth_date=patient.birth_date,
            customer_email=patient.email,
            customer_phone=patient.phone,
            amount=payment.amount,
        )
        try:
            start_checkout_order(order)
        except IntegrationError as exc:
            order.status = CheckoutOrder.Status.FAILED
            order.notes = f"Falha ao iniciar checkout: {exc}"
            order.save(update_fields=["status", "notes", "updated_at"])
            messages.error(request, str(exc))
            return redirect("checkout:patient_payments")
        if order.checkout_url:
            return redirect(order.checkout_url)
        return redirect("checkout:status", reference=order.external_reference)


class CheckoutOrderListView(FinanceAccessMixin, SearchableListView, ListView):
    model = CheckoutOrder
    template_name = "checkout/order_list.html"
    context_object_name = "orders"
    paginate_by = 20
    search_fields = ["customer_name", "customer_email", "customer_phone", "external_reference", "provider_payment_id"]

    def get_queryset(self):
        queryset = super().get_queryset().select_related("patient", "plan", "payment", "merchant_account")
        status = self.request.GET.get("status", "").strip()
        if status:
            queryset = queryset.filter(status=status)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["status_choices"] = CheckoutOrder.Status.choices
        context["selected_status"] = self.request.GET.get("status", "")
        return context


class CheckoutPaymentEventListView(FinanceAccessMixin, SearchableListView, ListView):
    model = CheckoutPaymentEvent
    template_name = "checkout/event_list.html"
    context_object_name = "events"
    paginate_by = 20
    search_fields = ["event_id", "event_type", "provider_payment_id", "external_reference"]

    def get_queryset(self):
        return super().get_queryset().select_related("order")


@method_decorator(csrf_exempt, name="dispatch")
class AsaasCheckoutWebhookView(View):
    def post(self, request):
        if not checkout_webhook_enabled():
            return JsonResponse({"ok": False, "detail": "Webhook de checkout desativado."}, status=403)
        try:
            payload, token_valid = parse_asaas_payload(request)
            event, created = record_asaas_checkout_webhook(payload, token_valid)
        except IntegrationError as exc:
            return JsonResponse({"ok": False, "detail": str(exc)}, status=400)
        return JsonResponse({"ok": True, "created": created, "event": event.event_id})
