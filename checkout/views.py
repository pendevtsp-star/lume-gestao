from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import DetailView, FormView, ListView, View

from accounts.permissions import FinanceAccessMixin, get_profile
from billing.models import Payment, ServicePlan
from checkout.features import checkout_enabled, checkout_patient_enabled, checkout_public_enabled, checkout_webhook_enabled
from checkout.forms import PublicPlanCheckoutForm
from checkout.models import CheckoutOrder
from checkout.models import CheckoutPaymentEvent
from checkout.services import parse_asaas_payload, record_asaas_checkout_webhook, start_checkout_order
from core.integrations.http import IntegrationError
from core.views import SearchableListView


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
        queryset = super().get_queryset().select_related("patient", "plan", "payment")
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
