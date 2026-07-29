from django.contrib import messages
from django.shortcuts import redirect
from django.utils import timezone
from django.views.generic import TemplateView

from accounts.permissions import FinanceAccessMixin
from core.integrations.http import IntegrationError
from core.integrations.whatsapp import (
    whatsapp_web_gateway_logout,
    whatsapp_web_gateway_restart,
    whatsapp_web_gateway_status,
)
from core.models import WhatsAppIntegration, WhatsAppMessageLog


class WhatsAppSettingsView(FinanceAccessMixin, TemplateView):
    template_name = "core/whatsapp_settings.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        integration = WhatsAppIntegration.load()
        gateway = whatsapp_web_gateway_status()
        connected = bool(gateway.get("ready"))
        connected_number = gateway.get("connectedNumber") or ""

        if connected:
            changed_fields = []
            if not integration.connected_at:
                integration.connected_at = timezone.now()
                changed_fields.append("connected_at")
            if connected_number and integration.clinic_whatsapp_number != connected_number:
                integration.clinic_whatsapp_number = connected_number
                changed_fields.append("clinic_whatsapp_number")
            if changed_fields:
                integration.save(update_fields=[*changed_fields, "updated_at"])

        context.update(
            {
                "page_title": "WhatsApp",
                "integration": integration,
                "gateway": gateway,
                "connected": connected,
                "connected_number": connected_number,
                "qr_data": gateway.get("qrDataUrl") or gateway.get("qr") or "",
                "waiting_count": WhatsAppMessageLog.objects.filter(
                    status=WhatsAppMessageLog.Status.SCHEDULED
                ).count(),
                "last_communication": WhatsAppMessageLog.objects.filter(
                    status__in=[
                        WhatsAppMessageLog.Status.SENT,
                        WhatsAppMessageLog.Status.DRY_RUN,
                    ]
                )
                .order_by("-sent_at", "-updated_at")
                .first(),
            }
        )
        return context

    def post(self, request):
        integration = WhatsAppIntegration.load()
        action = request.POST.get("action", "")
        if action in {"disconnect", "replace_device"}:
            try:
                whatsapp_web_gateway_logout()
            except IntegrationError:
                messages.error(
                    request,
                    "Não foi possível confirmar a desconexão do aparelho. "
                    "Atualize o estado antes de tentar novamente.",
                )
                return redirect("whatsapp_settings")

            integration.connected_at = None
            integration.save(update_fields=["connected_at", "updated_at"])
            messages.success(
                request,
                (
                    "Aparelho desconectado. Um novo QR Code está sendo preparado."
                    if action == "disconnect"
                    else "Troca de aparelho iniciada. Leia o novo QR Code."
                ),
            )
            return redirect("whatsapp_settings")

        if action in {"connect", "restart"}:
            integration.enabled = True
            integration.provider = WhatsAppIntegration.Provider.WEB_GATEWAY
            integration.save(update_fields=["enabled", "provider", "updated_at"])
            try:
                whatsapp_web_gateway_restart()
            except IntegrationError:
                messages.info(
                    request,
                    "A conexão ainda não respondeu. Aguarde alguns instantes e atualize a página.",
                )
            else:
                messages.success(
                    request,
                    "Conexão preparada. Leia o QR Code quando ele aparecer.",
                )
            return redirect("whatsapp_settings")

        messages.error(request, "Ação não reconhecida.")
        return redirect("whatsapp_settings")


class WhatsAppSupportView(FinanceAccessMixin, TemplateView):
    template_name = "core/whatsapp_support.html"

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and not request.user.is_superuser:
            return redirect("whatsapp_settings")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        gateway = whatsapp_web_gateway_status()
        context.update(
            {
                "page_title": "Suporte técnico do WhatsApp",
                "gateway": gateway,
                "scheduled_count": WhatsAppMessageLog.objects.filter(
                    status=WhatsAppMessageLog.Status.SCHEDULED
                ).count(),
                "failed_count": WhatsAppMessageLog.objects.filter(
                    status__in=[
                        WhatsAppMessageLog.Status.FAILED,
                        WhatsAppMessageLog.Status.DELIVERY_UNCERTAIN,
                    ]
                ).count(),
                "expired_count": WhatsAppMessageLog.objects.filter(
                    status=WhatsAppMessageLog.Status.EXPIRED
                ).count(),
            }
        )
        return context
