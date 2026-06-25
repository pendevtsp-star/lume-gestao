from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.views.generic import CreateView, FormView, ListView, UpdateView

from accounts.forms import UserAccountForm, UserSelfSettingsForm
from accounts.permissions import ManagementAccessMixin
from core.views import SearchableListView


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
        messages.success(self.request, "Usuario cadastrado com sucesso.")
        return super().form_valid(form)


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
        messages.success(self.request, "Usuario atualizado com sucesso.")
        return super().form_valid(form)


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
        context.update(
            {
                "page_title": "Minha conta",
                "section_label": "Configuracao",
                "back_url": reverse_lazy("dashboard"),
                "heading_avatar_url": profile.avatar_url,
                "heading_initials": profile.initials,
                "display_name": profile.display_name,
                "has_profile_photo": bool(profile.avatar_url),
            }
        )
        return context

    def form_valid(self, form):
        user = form.save()
        update_session_auth_hash(self.request, user)
        messages.success(self.request, "Conta atualizada com sucesso.")
        return super().form_valid(form)

# Create your views here.
