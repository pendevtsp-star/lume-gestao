from django.contrib import messages
from django.urls import reverse_lazy
from django.views.generic import CreateView, ListView, UpdateView

from accounts.models import UserProfile
from accounts.permissions import RoleRequiredMixin
from core.views import FormContextMixin, SearchableListView
from team.forms import EmployeeForm, ProfessionalForm
from team.models import Employee, Professional


class TeamAdminMixin(RoleRequiredMixin):
    allowed_roles = [UserProfile.Role.ADMINISTRATION, UserProfile.Role.MANAGEMENT]


class EmployeeListView(TeamAdminMixin, SearchableListView, ListView):
    model = Employee
    template_name = "team/employee_list.html"
    context_object_name = "employees"
    paginate_by = 12
    search_fields = ["full_name", "email", "phone", "role"]


class EmployeeCreateView(FormContextMixin, TeamAdminMixin, CreateView):
    model = Employee
    form_class = EmployeeForm
    template_name = "core/form.html"
    success_url = reverse_lazy("team:employees")
    page_title = "Funcionario"
    section_label = "Equipe"
    back_url_name = "team:employees"

    def form_valid(self, form):
        messages.success(self.request, "Funcionario cadastrado com sucesso.")
        return super().form_valid(form)


class EmployeeUpdateView(FormContextMixin, TeamAdminMixin, UpdateView):
    model = Employee
    form_class = EmployeeForm
    template_name = "core/form.html"
    success_url = reverse_lazy("team:employees")
    page_title = "Funcionario"
    section_label = "Equipe"
    back_url_name = "team:employees"

    def form_valid(self, form):
        messages.success(self.request, "Funcionario atualizado com sucesso.")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        employee = self.object
        context["page_title"] = employee.full_name
        context["heading_avatar_url"] = employee.photo.url if employee.photo else ""
        context["heading_initials"] = employee.full_name[:1].upper()
        return context


class ProfessionalListView(TeamAdminMixin, SearchableListView, ListView):
    model = Professional
    template_name = "team/professional_list.html"
    context_object_name = "professionals"
    paginate_by = 12
    search_fields = ["full_name", "email", "phone", "specialty", "registration_number"]


class ProfessionalCreateView(FormContextMixin, TeamAdminMixin, CreateView):
    model = Professional
    form_class = ProfessionalForm
    template_name = "core/form.html"
    success_url = reverse_lazy("team:professionals")
    page_title = "Profissional"
    section_label = "Equipe"
    back_url_name = "team:professionals"

    def form_valid(self, form):
        messages.success(self.request, "Profissional cadastrado com sucesso.")
        return super().form_valid(form)


class ProfessionalUpdateView(FormContextMixin, TeamAdminMixin, UpdateView):
    model = Professional
    form_class = ProfessionalForm
    template_name = "core/form.html"
    success_url = reverse_lazy("team:professionals")
    page_title = "Profissional"
    section_label = "Equipe"
    back_url_name = "team:professionals"

    def form_valid(self, form):
        messages.success(self.request, "Profissional atualizado com sucesso.")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        professional = self.object
        context["page_title"] = professional.full_name
        context["heading_avatar_url"] = professional.photo.url if professional.photo else ""
        context["heading_initials"] = professional.full_name[:1].upper()
        return context

# Create your views here.
