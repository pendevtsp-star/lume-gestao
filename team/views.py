from django.contrib import messages
from django.db.models import Count, Q
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from accounts.models import UserProfile
from accounts.permissions import RoleRequiredMixin
from core.views import FormContextMixin, SearchableListView
from patients.services import deactivate_professional_relationships
from scheduling.models import Appointment
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


class SoftDeleteTeamView(FormContextMixin, TeamAdminMixin, DeleteView):
    template_name = "core/confirm_deactivate.html"
    object_name_attribute = "full_name"
    entity_label = "cadastro"
    delete_button_label = "Excluir cadastro"

    def form_valid(self, form):
        item = self.object
        item.active = False
        item.full_clean()
        item.save(update_fields=["active", "updated_at"])
        messages.success(self.request, f"{self.entity_label.capitalize()} excluido da lista ativa com sucesso.")
        return redirect(self.success_url)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "object_name": getattr(self.object, self.object_name_attribute),
                "entity_label": self.entity_label,
                "delete_button_label": self.delete_button_label,
                "delete_explanation": (
                    "O cadastro sera marcado como inativo para preservar agenda, relatorios, auditoria e "
                    "historicos ja vinculados. Ele pode ser reativado editando o cadastro depois."
                ),
            }
        )
        return context


class EmployeeDeleteView(SoftDeleteTeamView):
    model = Employee
    success_url = reverse_lazy("team:employees")
    page_title = "Excluir funcionario"
    section_label = "Equipe"
    back_url_name = "team:employees"
    entity_label = "funcionario"
    delete_button_label = "Excluir funcionario"


class ProfessionalListView(TeamAdminMixin, SearchableListView, ListView):
    model = Professional
    template_name = "team/professional_list.html"
    context_object_name = "professionals"
    paginate_by = 12
    search_fields = ["full_name", "email", "phone", "specialty", "registration_number"]

    def get_queryset(self):
        return super().get_queryset().annotate(
            active_patient_count=Count(
                "appointments__patient",
                filter=Q(
                    appointments__patient__active=True,
                    appointments__status__in=[
                        Appointment.Status.REQUESTED,
                        Appointment.Status.SCHEDULED,
                        Appointment.Status.COMPLETED,
                        Appointment.Status.NO_SHOW,
                    ],
                ),
                distinct=True,
            ),
            upcoming_appointment_count=Count(
                "appointments",
                filter=Q(
                    appointments__starts_at__gte=timezone.now(),
                    appointments__status__in=[Appointment.Status.REQUESTED, Appointment.Status.SCHEDULED],
                ),
                distinct=True,
            ),
        ).order_by("full_name")


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
        response = super().form_valid(form)
        if not self.object.active:
            deactivate_professional_relationships(self.object)
        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        professional = self.object
        context["page_title"] = professional.full_name
        context["heading_avatar_url"] = professional.photo.url if professional.photo else ""
        context["heading_initials"] = professional.full_name[:1].upper()
        return context


class ProfessionalDeleteView(SoftDeleteTeamView):
    model = Professional
    success_url = reverse_lazy("team:professionals")
    page_title = "Excluir profissional"
    section_label = "Equipe"
    back_url_name = "team:professionals"
    entity_label = "profissional"
    delete_button_label = "Excluir profissional"

    def form_valid(self, form):
        response = super().form_valid(form)
        deactivate_professional_relationships(self.object)
        return response

# Create your views here.
