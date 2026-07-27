import hmac
import json

from django.conf import settings
from django.contrib import messages
from django.http import JsonResponse
from django.urls import reverse, reverse_lazy
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import ListView, TemplateView, UpdateView

from accounts.permissions import ManagementAccessMixin
from core.forms import ClinicSettingsForm
from core.models import AuditLog, ClinicSettings, EmailDeliveryEvent
from core.web.mixins import SearchableListView

class BrevoTransactionalWebhookView(View):
    """Receives Brevo delivery events without exposing SMTP credentials."""

    http_method_names = ["post"]

    def post(self, request, *args, **kwargs):
        expected_token = settings.EMAIL_BREVO_WEBHOOK_TOKEN
        supplied_token = request.headers.get("X-Lume-Email-Webhook-Token") or request.GET.get("token", "")
        if not expected_token or not hmac.compare_digest(supplied_token, expected_token):
            return JsonResponse({"ok": False, "error": "unauthorized"}, status=403)

        try:
            payload = json.loads(request.body.decode("utf-8") or "{}")
        except (UnicodeDecodeError, json.JSONDecodeError):
            return JsonResponse({"ok": False, "error": "invalid_json"}, status=400)

        events = payload if isinstance(payload, list) else payload.get("events", [payload])
        if not isinstance(events, list):
            return JsonResponse({"ok": False, "error": "invalid_events"}, status=400)

        stored = 0
        for event in events:
            if not isinstance(event, dict):
                continue
            EmailDeliveryEvent.objects.create(
                provider="brevo",
                event_type=str(event.get("event") or event.get("type") or "unknown")[:60],
                recipient=str(event.get("email") or event.get("recipient") or "")[:254],
                message_id=str(event.get("message-id") or event.get("message_id") or event.get("id") or "")[:255],
                payload=event,
            )
            stored += 1
        return JsonResponse({"ok": True, "stored": stored})

class HealthCheckView(View):
    def get(self, request):
        return JsonResponse({"status": "ok"})


class LegalDocumentView(TemplateView):
    template_name = "core/legal_document.html"
    document_key = ""

    DOCUMENTS = {
        "terms": {
            "title": "Termos de Uso",
            "subtitle": "Regras basicas para uso seguro do Lume Gestao.",
            "sections": [
                (
                    "Finalidade do sistema",
                    "O Lume Gestao organiza cadastros, agenda, prontuario, financeiro, comunicacoes e documentos da clinica. O uso deve estar ligado ao atendimento, gestao operacional e relacionamento com pacientes.",
                ),
                (
                    "Responsabilidade do usuario",
                    "Cada usuario deve usar sua propria conta, proteger a senha, sair do sistema em computadores compartilhados e comunicar qualquer acesso indevido.",
                ),
                (
                    "Uso adequado",
                    "E proibido compartilhar login, inserir informacoes falsas, consultar dados sem necessidade profissional ou tentar burlar permissoes do sistema.",
                ),
                (
                    "Disponibilidade",
                    "A clinica pode realizar manutencoes, atualizacoes, backups e ajustes de seguranca para manter o sistema funcionando de forma confiavel.",
                ),
            ],
        },
        "privacy": {
            "title": "Politica de Privacidade",
            "subtitle": "Como os dados pessoais sao tratados no Lume Gestao.",
            "sections": [
                (
                    "Dados tratados",
                    "O sistema pode armazenar nome, CPF, nascimento, telefone, e-mail, endereco, agenda, pagamentos, registros de atendimento, prontuario e historico de comunicacoes.",
                ),
                (
                    "Finalidades",
                    "Os dados sao usados para identificar pacientes, organizar atendimentos, registrar evolucao clinica, cumprir obrigacoes administrativas/fiscais, enviar comunicacoes e proteger a seguranca da operacao.",
                ),
                (
                    "Compartilhamento",
                    "Dados podem ser compartilhados apenas quando necessario para prestadores tecnicos, servicos de e-mail, WhatsApp, Google Agenda, emissao fiscal, cumprimento legal ou mediante solicitacao autorizada.",
                ),
                (
                    "Direitos do titular",
                    "O paciente pode solicitar informacao, correcao, revisao de dados e orientacoes sobre o tratamento dos seus dados diretamente com a clinica.",
                ),
                (
                    "Seguranca",
                    "O acesso e controlado por perfil de usuario, senha individual, registros de auditoria, backups e verificacoes realizadas no backend.",
                ),
            ],
        },
        "sensitive": {
            "title": "Consentimento para Dados Sensiveis",
            "subtitle": "Autorizacao para tratamento de dados de saude.",
            "sections": [
                (
                    "Dados de saude",
                    "Registros de avaliacao, diagnostico, exame fisico, evolucao, observacoes clinicas, exercicios, dor, conduta e informacoes relacionadas ao atendimento podem ser considerados dados pessoais sensiveis.",
                ),
                (
                    "Uso autorizado",
                    "Ao consentir, o paciente autoriza o uso desses dados para prestacao de servicos de fisioterapia/pilates, continuidade do cuidado, organizacao da agenda, comunicacoes e gestao da clinica.",
                ),
                (
                    "Acesso restrito",
                    "A visualizacao desses dados deve ser limitada a profissionais e pessoas autorizadas conforme funcao, necessidade operacional e regras internas da clinica.",
                ),
                (
                    "Revogacao e limites",
                    "O consentimento pode ser revogado mediante contato com a clinica, observadas obrigacoes legais, regulatórias, defesa de direitos e preservacao de historico clinico quando aplicavel.",
                ),
            ],
        },
    }

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["document"] = self.DOCUMENTS[self.document_key]
        return context

class AuditLogListView(ManagementAccessMixin, SearchableListView, ListView):
    model = AuditLog
    template_name = "core/audit_list.html"
    context_object_name = "logs"
    paginate_by = 20
    search_fields = ["actor__username", "model_name", "object_repr", "action"]

    def get_queryset(self):
        queryset = super().get_queryset().select_related("actor")
        action = self.request.GET.get("action", "").strip()
        model_name = self.request.GET.get("model", "").strip()
        date_from = self.request.GET.get("date_from", "").strip()
        date_to = self.request.GET.get("date_to", "").strip()
        if action:
            queryset = queryset.filter(action=action)
        if model_name:
            queryset = queryset.filter(model_name=model_name)
        if date_from:
            queryset = queryset.filter(created_at__date__gte=date_from)
        if date_to:
            queryset = queryset.filter(created_at__date__lte=date_to)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        base_queryset = AuditLog.objects.all()
        filtered = self.get_queryset()
        context.update(
            {
                "action_choices": AuditLog.Action.choices,
                "model_choices": base_queryset.order_by("model_name")
                .values_list("model_name", flat=True)
                .distinct(),
                "selected_action": self.request.GET.get("action", ""),
                "selected_model": self.request.GET.get("model", ""),
                "date_from": self.request.GET.get("date_from", ""),
                "date_to": self.request.GET.get("date_to", ""),
                "audit_total": filtered.count(),
                "audit_created_total": filtered.filter(action=AuditLog.Action.CREATED).count(),
                "audit_updated_total": filtered.filter(action=AuditLog.Action.UPDATED).count(),
                "audit_deleted_total": filtered.filter(action=AuditLog.Action.DELETED).count(),
            }
        )
        return context


class ClinicSettingsUpdateView(ManagementAccessMixin, UpdateView):
    model = ClinicSettings
    form_class = ClinicSettingsForm
    template_name = "core/clinic_settings.html"
    success_url = reverse_lazy("settings")

    def get_object(self, queryset=None):
        return ClinicSettings.load()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "page_title": "Configuracoes",
                "section_label": "Gerencia",
                "back_url": reverse("dashboard"),
            }
        )
        return context

    def form_valid(self, form):
        messages.success(self.request, "Configuracoes da clinica atualizadas com sucesso.")
        return super().form_valid(form)
