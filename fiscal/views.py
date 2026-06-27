import secrets

from django.contrib import messages
from django.db.models import Count, Q, Sum
from django.http import HttpResponse
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, TemplateView, UpdateView

from accounts.permissions import FinanceAccessMixin
from billing.models import Charge, Payment

from .forms import FiscalDocumentForm, FiscalSettingsForm
from .models import FiscalDocument, FiscalSettings
from .services import build_document_pdf, send_document_email, send_document_whatsapp


class FiscalDashboardView(FinanceAccessMixin, TemplateView):
    template_name = "fiscal/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        documents = FiscalDocument.objects.select_related("patient").all()
        q = self.request.GET.get("q", "").strip()
        status = self.request.GET.get("status", "")
        document_type = self.request.GET.get("type", "")
        if q:
            documents = documents.filter(
                Q(customer_name__icontains=q)
                | Q(customer_document__icontains=q)
                | Q(description__icontains=q)
                | Q(external_id__icontains=q)
            )
        if status:
            documents = documents.filter(status=status)
        if document_type:
            documents = documents.filter(document_type=document_type)
        settings_object = FiscalSettings.load()
        totals = documents.aggregate(total=Sum("total_amount"), count=Count("id"))
        context.update(
            {
                "settings_object": settings_object,
                "settings_form": FiscalSettingsForm(instance=settings_object),
                "documents": documents[:30],
                "total_documents": totals["count"] or 0,
                "total_amount": totals["total"] or 0,
                "issued_count": documents.filter(status=FiscalDocument.Status.ISSUED).count(),
                "draft_count": documents.filter(status=FiscalDocument.Status.DRAFT).count(),
                "provider_cards": _provider_cards(),
                "q": q,
                "selected_status": status,
                "selected_type": document_type,
                "status_choices": FiscalDocument.Status.choices,
                "type_choices": FiscalDocument.DocumentType.choices,
            }
        )
        return context


class FiscalSettingsView(FinanceAccessMixin, View):
    def post(self, request, *args, **kwargs):
        settings_object = FiscalSettings.load()
        form = FiscalSettingsForm(request.POST, instance=settings_object)
        if form.is_valid():
            form.save()
            messages.success(request, "Configuracao fiscal salva.")
        else:
            messages.error(request, "Revise os campos da configuracao fiscal.")
        return redirect("fiscal:dashboard")


class FiscalDocumentCreateView(FinanceAccessMixin, CreateView):
    model = FiscalDocument
    form_class = FiscalDocumentForm
    template_name = "fiscal/document_form.html"
    success_url = reverse_lazy("fiscal:dashboard")

    def get_initial(self):
        initial = super().get_initial()
        settings_object = FiscalSettings.load()
        initial["service_code"] = settings_object.default_service_code
        initial["iss_rate"] = settings_object.default_iss_rate
        payment_id = self.request.GET.get("payment")
        charge_id = self.request.GET.get("charge")
        if payment_id:
            payment = Payment.objects.select_related("membership__patient", "membership__plan").filter(pk=payment_id).first()
            if payment:
                patient = payment.membership.patient
                initial.update(
                    {
                        "payment": payment,
                        "patient": patient,
                        "amount": payment.amount,
                        "description": f"Mensalidade {payment.reference_month:%m/%Y} - {payment.membership.plan.name}",
                        "customer_name": patient.full_name,
                        "customer_document": patient.cpf or "",
                        "customer_email": patient.email,
                        "customer_phone": patient.phone,
                    }
                )
        if charge_id:
            charge = Charge.objects.select_related("patient").filter(pk=charge_id).first()
            if charge:
                initial.update(
                    {
                        "charge": charge,
                        "patient": charge.patient,
                        "amount": charge.amount,
                        "description": charge.description,
                    }
                )
                if charge.patient:
                    initial.update(
                        {
                            "customer_name": charge.patient.full_name,
                            "customer_document": charge.patient.cpf or "",
                            "customer_email": charge.patient.email,
                            "customer_phone": charge.patient.phone,
                        }
                    )
        return initial

    def form_valid(self, form):
        document = form.save(commit=False)
        _fill_customer_from_patient(document)
        messages.success(self.request, "Documento fiscal criado.")
        return super().form_valid(form)


class FiscalDocumentUpdateView(FinanceAccessMixin, UpdateView):
    model = FiscalDocument
    form_class = FiscalDocumentForm
    template_name = "fiscal/document_form.html"
    success_url = reverse_lazy("fiscal:dashboard")

    def form_valid(self, form):
        document = form.save(commit=False)
        _fill_customer_from_patient(document)
        messages.success(self.request, "Documento fiscal atualizado.")
        return super().form_valid(form)


class FiscalDocumentIssueView(FinanceAccessMixin, View):
    def post(self, request, pk, *args, **kwargs):
        document = FiscalDocument.objects.get(pk=pk)
        fiscal_settings = FiscalSettings.load()
        if not document.can_issue:
            messages.warning(request, "Este documento nao esta disponivel para emissao.")
            return redirect("fiscal:dashboard")

        if document.is_nfse and not fiscal_settings.nfse_enabled:
            document.provider_payload = {
                "official_emission": False,
                "reason": "NFS-e oficial ainda nao habilitada.",
                "provider": fiscal_settings.provider,
            }
            messages.warning(
                request,
                "NFS-e registrada no sistema. Para autorizacao oficial, habilite e configure prefeitura/provedor.",
            )
        else:
            document.provider_payload = {
                "official_emission": document.is_nfse,
                "provider": fiscal_settings.provider,
                "environment": fiscal_settings.environment,
            }
            messages.success(request, "Documento emitido/registrado com sucesso.")

        prefix = "NFSE" if document.is_nfse else "REC"
        document.external_id = document.external_id or f"LUME-{prefix}-{timezone.now():%Y%m%d}-{document.pk:06d}"
        document.verification_code = document.verification_code or secrets.token_hex(4).upper()
        document.status = FiscalDocument.Status.ISSUED
        document.save(update_fields=["external_id", "verification_code", "status", "provider_payload", "updated_at"])
        return redirect("fiscal:dashboard")


class FiscalDocumentPdfView(FinanceAccessMixin, View):
    def get(self, request, pk, *args, **kwargs):
        document = FiscalDocument.objects.get(pk=pk)
        response = HttpResponse(build_document_pdf(document), content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="documento-fiscal-{document.pk}.pdf"'
        return response


class FiscalDocumentEmailView(FinanceAccessMixin, View):
    def post(self, request, pk, *args, **kwargs):
        document = FiscalDocument.objects.get(pk=pk)
        try:
            send_document_email(document)
        except Exception as exc:
            messages.error(request, f"Nao foi possivel enviar por e-mail: {exc}")
        else:
            document.status = FiscalDocument.Status.SENT
            document.save(update_fields=["status", "updated_at"])
            messages.success(request, "Documento enviado por e-mail.")
        return redirect("fiscal:dashboard")


class FiscalDocumentWhatsAppView(FinanceAccessMixin, View):
    def post(self, request, pk, *args, **kwargs):
        document = FiscalDocument.objects.get(pk=pk)
        try:
            send_document_whatsapp(document)
        except Exception as exc:
            messages.error(request, f"Nao foi possivel enviar por WhatsApp: {exc}")
        else:
            document.status = FiscalDocument.Status.SENT
            document.save(update_fields=["status", "updated_at"])
            messages.success(request, "Resumo enviado por WhatsApp.")
        return redirect("fiscal:dashboard")


def _fill_customer_from_patient(document):
    if not document.patient_id:
        return
    patient = document.patient
    document.customer_name = document.customer_name or patient.full_name
    document.customer_document = document.customer_document or patient.cpf or ""
    document.customer_email = document.customer_email or patient.email
    document.customer_phone = document.customer_phone or patient.phone


def _provider_cards():
    return [
        {
            "title": "NFS-e Nacional / prefeitura",
            "description": "Melhor caminho quando o municipio da clinica ja aceita o padrao nacional ou tem portal proprio estavel.",
        },
        {
            "title": "Focus NFe, PlugNotas, NFE.io ou TecnoSpeed",
            "description": "Boas opcoes quando a clinica quer API, sandbox, suporte a varios municipios e automacao.",
        },
        {
            "title": "Recibo interno",
            "description": "Util para comprovante operacional, mas nao substitui NFS-e quando a prefeitura exigir nota de servico.",
        },
    ]
