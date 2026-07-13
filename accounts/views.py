import hashlib

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.tokens import default_token_generator
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.cache import cache
from django.core.mail import EmailMultiAlternatives
from django.shortcuts import redirect
from django.template.loader import render_to_string
from django.urls import reverse, reverse_lazy
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from django.views.generic import CreateView, DeleteView, FormView, ListView, UpdateView

from accounts.forms import ForcePasswordChangeForm, PasswordRecoveryRequestForm, UserAccountForm, UserSelfSettingsForm
from accounts.onboarding import generate_temporary_password, send_welcome_credentials
from accounts.permissions import ManagementAccessMixin
from core.deletion import DeletionDecisionMixin
from core.views import SearchableListView


PASSWORD_RECOVERY_LIMIT = 5
PASSWORD_RECOVERY_WINDOW_SECONDS = 15 * 60


def password_recovery_cache_key(request, identifier):
    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR", "")
    ip_address = forwarded_for.split(",", 1)[0].strip() or request.META.get("REMOTE_ADDR", "")
    raw_key = f"{ip_address}|{identifier.strip().lower()}"
    digest = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
    return f"password-recovery:{digest}"


class UserAccountListView(ManagementAccessMixin, SearchableListView, ListView):
    model = get_user_model()
    template_name = "accounts/user_list.html"
    context_object_name = "users"
    paginate_by = 12
    search_fields = ["username", "first_name", "last_name", "email", "profile__role"]

    def get_queryset(self):
        return super().get_queryset().select_related("profile", "profile__patient", "profile__professional").order_by("username")


class UserAccountCreateView(ManagementAccessMixin, CreateView):
    model = get_user_model()
    form_class = UserAccountForm
    template_name = "core/form.html"
    success_url = reverse_lazy("accounts:list")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({"page_title": "Usuario", "section_label": "Acessos", "back_url": reverse_lazy("accounts:list")})
        return context

    def form_valid(self, form):
        temporary_password = form.cleaned_data.get("password") or generate_temporary_password()
        form.cleaned_data["password"] = temporary_password
        response = super().form_valid(form)
        profile = self.object.profile
        profile.must_change_password = True
        profile.save(update_fields=["must_change_password", "updated_at"])
        delivery = send_welcome_credentials(self.object, temporary_password, request=self.request)
        if delivery["sent"]:
            messages.success(self.request, "Usuario cadastrado e senha temporaria enviada por e-mail.")
        else:
            messages.warning(
                self.request,
                "Usuario cadastrado. Nao foi possivel enviar a senha temporaria automaticamente; informe a senha ao usuario com seguranca.",
            )
        return response


class UserAccountUpdateView(ManagementAccessMixin, UpdateView):
    model = get_user_model()
    form_class = UserAccountForm
    template_name = "core/form.html"
    success_url = reverse_lazy("accounts:list")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({"page_title": "Usuario", "section_label": "Acessos", "back_url": reverse_lazy("accounts:list")})
        return context

    def form_valid(self, form):
        temporary_password = form.cleaned_data.get("password")
        response = super().form_valid(form)
        if temporary_password:
            profile = self.object.profile
            profile.must_change_password = True
            profile.save(update_fields=["must_change_password", "updated_at"])
            delivery = send_welcome_credentials(self.object, temporary_password, request=self.request)
            if delivery["sent"]:
                messages.success(self.request, "Usuario atualizado e nova senha temporaria enviada por e-mail.")
            else:
                messages.warning(
                    self.request,
                    "Usuario atualizado. Nao foi possivel enviar a nova senha temporaria automaticamente.",
                )
        else:
            messages.success(self.request, "Usuario atualizado com sucesso.")
        return response


class UserAccountDeleteView(DeletionDecisionMixin, ManagementAccessMixin, DeleteView):
    model = get_user_model()
    template_name = "core/confirm_deactivate.html"
    success_url = reverse_lazy("accounts:list")
    page_title = "Excluir usuario"
    section_label = "Acessos"
    back_url_name = "accounts:list"
    entity_label = "usuario"
    deactivate_explanation = "Bloqueia o acesso do usuario sem remover o historico vinculado."
    delete_now_explanation = "Remove definitivamente o acesso. Paciente ou profissional vinculado permanecem cadastrados."

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        if self.object.pk == request.user.pk:
            messages.error(request, "Voce nao pode excluir ou inativar o proprio usuario logado.")
            return redirect(self.success_url)
        return super().post(request, *args, **kwargs)

    def perform_deactivate(self):
        self.object.is_active = False
        self.object.save(update_fields=["is_active"])

    def get_deactivate_success_message(self):
        return "Usuario inativado. O acesso fica bloqueado ate ser reativado."

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "object_name": self.object.get_full_name() or self.object.username,
                "entity_label": self.entity_label,
                "delete_explanation": "Escolha se deseja bloquear este acesso ou remover o usuario definitivamente.",
            }
        )
        return context


class UserSelfSettingsView(LoginRequiredMixin, FormView):
    form_class = UserSelfSettingsForm
    template_name = "accounts/self_settings.html"
    success_url = reverse_lazy("accounts:self_settings")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def get_context_data(self, **kwargs):
        profile = self.request.user.profile
        context = super().get_context_data(**kwargs)
        form = context.get("form")
        context.update(
            {
                "page_title": "Minha conta",
                "section_label": "Configuracao",
                "back_url": reverse_lazy("dashboard"),
                "heading_avatar_url": profile.avatar_url,
                "heading_initials": profile.initials,
                "display_name": profile.display_name,
                "has_profile_photo": bool(profile.avatar_url),
                "show_whatsapp_settings": form.show_whatsapp_settings if form else False,
            }
        )
        return context

    def form_valid(self, form):
        user = form.save()
        update_session_auth_hash(self.request, user)
        messages.success(self.request, "Conta atualizada com sucesso.")
        return super().form_valid(form)


class PasswordRecoveryRequestView(FormView):
    form_class = PasswordRecoveryRequestForm
    template_name = "registration/password_reset_form.html"
    success_url = reverse_lazy("password_reset_done")

    def is_throttled(self, identifier):
        cache_key = password_recovery_cache_key(self.request, identifier)
        attempts = cache.get(cache_key, 0)
        if attempts >= PASSWORD_RECOVERY_LIMIT:
            return True
        cache.set(cache_key, attempts + 1, PASSWORD_RECOVERY_WINDOW_SECONDS)
        return False

    def send_password_reset_email(self, user):
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)
        reset_url = self.request.build_absolute_uri(
            reverse("password_reset_confirm", kwargs={
                "uidb64": uid,
                "token": token,
            })
        )
        context = {
            "user": user,
            "uid": uid,
            "token": token,
            "protocol": "https" if self.request.is_secure() else "http",
            "domain": self.request.get_host(),
            "reset_url": reset_url,
        }
        subject = render_to_string("registration/password_reset_subject.txt", context).strip()
        text_body = render_to_string("registration/password_reset_email.txt", context)
        html_body = render_to_string("registration/password_reset_email.html", context)
        reply_to = [settings.EMAIL_REPLY_TO] if settings.EMAIL_REPLY_TO else None
        message = EmailMultiAlternatives(
            subject,
            text_body,
            settings.EMAIL_TRANSACTIONAL_FROM_EMAIL,
            [user.email],
            reply_to=reply_to,
        )
        message.attach_alternative(html_body, "text/html")
        message.send(fail_silently=False)

    def send_temporary_password_by_whatsapp(self, user, phone_number):
        if not phone_number:
            return False
        temporary_password = generate_temporary_password()
        old_password = user.password
        profile = user.profile
        old_must_change = profile.must_change_password
        user.set_password(temporary_password)
        user.save(update_fields=["password"])
        profile.must_change_password = True
        profile.save(update_fields=["must_change_password", "updated_at"])
        delivery = send_welcome_credentials(
            user,
            temporary_password,
            request=self.request,
            phone_number=phone_number,
            prefer_email=False,
        )
        if delivery["sent"]:
            return True
        user.password = old_password
        user.save(update_fields=["password"])
        profile.must_change_password = old_must_change
        profile.save(update_fields=["must_change_password", "updated_at"])
        return False

    def form_valid(self, form):
        identifier = form.cleaned_data.get("identifier", "")
        if self.is_throttled(identifier):
            messages.success(
                self.request,
                "Se os dados estiverem corretos, enviaremos a recuperacao para o e-mail ou WhatsApp cadastrado.",
            )
            return super().form_valid(form)

        for user in form.email_users:
            try:
                self.send_password_reset_email(user)
            except Exception:
                self.send_temporary_password_by_whatsapp(user, form.recovery_phones.get(user.pk, ""))

        for user in form.whatsapp_users:
            if user.email:
                continue
            self.send_temporary_password_by_whatsapp(user, form.recovery_phones.get(user.pk, ""))

        messages.success(self.request, "Se os dados estiverem corretos, enviaremos a recuperacao para o e-mail ou WhatsApp cadastrado.")
        return super().form_valid(form)


class ForcePasswordChangeView(LoginRequiredMixin, FormView):
    form_class = ForcePasswordChangeForm
    template_name = "accounts/force_password_change.html"
    success_url = reverse_lazy("dashboard")

    def dispatch(self, request, *args, **kwargs):
        profile = getattr(request.user, "profile", None)
        if not profile or not profile.must_change_password:
            return redirect("dashboard")
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        user = form.save()
        update_session_auth_hash(self.request, user)
        messages.success(self.request, "Senha alterada com sucesso. Bem-vindo(a) ao Lume Gestao.")
        return redirect("dashboard")

# Create your views here.
