from django.contrib import messages
from django.urls import reverse_lazy
from django.views.generic import CreateView, ListView, UpdateView

from accounts.models import UserProfile
from accounts.permissions import RoleRequiredMixin, get_profile
from core.views import FormContextMixin, SearchableListView
from patients.forms import PatientForm, ProfessionalNoteForm, ProfessionalPatientAssignmentForm
from patients.models import Patient, ProfessionalNote, ProfessionalPatientAssignment


class PatientAccessMixin(RoleRequiredMixin):
    allowed_roles = [
        UserProfile.Role.PATIENT,
        UserProfile.Role.PROFESSIONAL,
        UserProfile.Role.ADMINISTRATION,
        UserProfile.Role.MANAGEMENT,
    ]


def patients_for_user(user):
    queryset = Patient.objects.all()
    if user.is_superuser:
        return queryset
    profile = get_profile(user)
    if not profile:
        return queryset.none()
    if profile.role in {UserProfile.Role.ADMINISTRATION, UserProfile.Role.MANAGEMENT}:
        return queryset
    if profile.is_patient and profile.patient_id:
        return queryset.filter(pk=profile.patient_id)
    if profile.is_professional and profile.professional_id:
        patient_ids = ProfessionalPatientAssignment.objects.filter(
            professional=profile.professional,
            active=True,
        ).values_list("patient_id", flat=True)
        return queryset.filter(pk__in=patient_ids)
    return queryset.none()


class PatientListView(PatientAccessMixin, SearchableListView, ListView):
    model = Patient
    template_name = "patients/patient_list.html"
    context_object_name = "patients"
    paginate_by = 12
    search_fields = ["full_name", "cpf", "phone", "email"]

    def get_queryset(self):
        return patients_for_user(self.request.user)


class PatientCreateView(FormContextMixin, RoleRequiredMixin, CreateView):
    allowed_roles = [UserProfile.Role.ADMINISTRATION, UserProfile.Role.MANAGEMENT]
    model = Patient
    form_class = PatientForm
    template_name = "core/form.html"
    success_url = reverse_lazy("patients:list")
    page_title = "Paciente"
    section_label = "Cadastro"
    back_url_name = "patients:list"

    def form_valid(self, form):
        messages.success(self.request, "Paciente cadastrado com sucesso.")
        return super().form_valid(form)


class PatientUpdateView(FormContextMixin, PatientAccessMixin, UpdateView):
    model = Patient
    form_class = PatientForm
    template_name = "core/form.html"
    success_url = reverse_lazy("patients:list")
    page_title = "Paciente"
    section_label = "Cadastro"
    back_url_name = "patients:list"

    def get_queryset(self):
        return patients_for_user(self.request.user)

    def form_valid(self, form):
        messages.success(self.request, "Paciente atualizado com sucesso.")
        return super().form_valid(form)


class AssignmentListView(RoleRequiredMixin, SearchableListView, ListView):
    allowed_roles = [UserProfile.Role.ADMINISTRATION, UserProfile.Role.MANAGEMENT]
    model = ProfessionalPatientAssignment
    template_name = "patients/assignment_list.html"
    context_object_name = "assignments"
    paginate_by = 12
    search_fields = ["patient__full_name", "professional__full_name", "notes"]

    def get_queryset(self):
        return super().get_queryset().select_related("patient", "professional")


class AssignmentCreateView(FormContextMixin, RoleRequiredMixin, CreateView):
    allowed_roles = [UserProfile.Role.ADMINISTRATION, UserProfile.Role.MANAGEMENT]
    model = ProfessionalPatientAssignment
    form_class = ProfessionalPatientAssignmentForm
    template_name = "core/form.html"
    success_url = reverse_lazy("patients:assignments")
    page_title = "Vinculo paciente-profissional"
    section_label = "Pacientes"
    back_url_name = "patients:assignments"

    def form_valid(self, form):
        messages.success(self.request, "Vinculo cadastrado com sucesso.")
        return super().form_valid(form)


class AssignmentUpdateView(FormContextMixin, RoleRequiredMixin, UpdateView):
    allowed_roles = [UserProfile.Role.ADMINISTRATION, UserProfile.Role.MANAGEMENT]
    model = ProfessionalPatientAssignment
    form_class = ProfessionalPatientAssignmentForm
    template_name = "core/form.html"
    success_url = reverse_lazy("patients:assignments")
    page_title = "Vinculo paciente-profissional"
    section_label = "Pacientes"
    back_url_name = "patients:assignments"

    def form_valid(self, form):
        messages.success(self.request, "Vinculo atualizado com sucesso.")
        return super().form_valid(form)


class ProfessionalNoteListView(PatientAccessMixin, SearchableListView, ListView):
    model = ProfessionalNote
    template_name = "patients/note_list.html"
    context_object_name = "notes"
    paginate_by = 12
    search_fields = ["patient__full_name", "professional__full_name", "title", "body"]

    def get_queryset(self):
        queryset = super().get_queryset().select_related("patient", "professional")
        if self.request.user.is_superuser:
            return queryset
        profile = get_profile(self.request.user)
        if profile.role in {UserProfile.Role.ADMINISTRATION, UserProfile.Role.MANAGEMENT}:
            return queryset
        if profile.is_professional and profile.professional_id:
            return queryset.filter(professional=profile.professional)
        if profile.is_patient and profile.patient_id:
            return queryset.filter(patient=profile.patient)
        return queryset.none()


class ProfessionalNoteCreateView(FormContextMixin, RoleRequiredMixin, CreateView):
    allowed_roles = [UserProfile.Role.PROFESSIONAL, UserProfile.Role.ADMINISTRATION, UserProfile.Role.MANAGEMENT]
    model = ProfessionalNote
    form_class = ProfessionalNoteForm
    template_name = "core/form.html"
    success_url = reverse_lazy("patients:notes")
    page_title = "Anotacao"
    section_label = "Pacientes"
    back_url_name = "patients:notes"

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        profile = get_profile(self.request.user)
        if profile and profile.is_professional and profile.professional_id:
            form.fields["professional"].queryset = form.fields["professional"].queryset.filter(pk=profile.professional_id)
            patient_ids = ProfessionalPatientAssignment.objects.filter(
                professional=profile.professional,
                active=True,
            ).values_list("patient_id", flat=True)
            form.fields["patient"].queryset = form.fields["patient"].queryset.filter(pk__in=patient_ids)
        return form

    def form_valid(self, form):
        messages.success(self.request, "Anotacao registrada com sucesso.")
        return super().form_valid(form)

# Create your views here.
