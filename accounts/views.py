from django.contrib import messages
from django.contrib.auth import get_user_model
from django.urls import reverse_lazy
from django.views.generic import CreateView, ListView, UpdateView

from accounts.forms import UserAccountForm
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

# Create your views here.
