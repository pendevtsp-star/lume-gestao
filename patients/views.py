from django import forms
from django.contrib import messages
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from accounts.models import UserProfile
from accounts.permissions import RoleRequiredMixin, get_profile
from core.exports import pdf_response, xlsx_response
from core.views import FormContextMixin, SearchableListView
from patients.forms import PatientForm, ProfessionalNoteForm, ProfessionalPatientAssignmentForm, note_type_options
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

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        patient = self.object
        context["page_title"] = patient.full_name
        context["heading_avatar_url"] = patient.photo.url if patient.photo else ""
        context["heading_initials"] = patient.full_name[:1].upper()
        return context

    def form_valid(self, form):
        messages.success(self.request, "Paciente atualizado com sucesso.")
        return super().form_valid(form)


class PatientDeleteView(FormContextMixin, RoleRequiredMixin, DeleteView):
    allowed_roles = [UserProfile.Role.ADMINISTRATION, UserProfile.Role.MANAGEMENT]
    model = Patient
    template_name = "core/confirm_deactivate.html"
    success_url = reverse_lazy("patients:list")
    page_title = "Excluir paciente"
    section_label = "Cadastro"
    back_url_name = "patients:list"
    entity_label = "paciente"
    delete_button_label = "Excluir paciente"

    def form_valid(self, form):
        patient = self.object
        patient.active = False
        patient.full_clean()
        patient.save(update_fields=["active", "updated_at"])
        messages.success(self.request, "Paciente excluido da lista ativa com sucesso.")
        return redirect(self.success_url)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "object_name": self.object.full_name,
                "entity_label": self.entity_label,
                "delete_button_label": self.delete_button_label,
                "delete_explanation": (
                    "O cadastro sera marcado como inativo para preservar historico financeiro, agenda, prontuario "
                    "e auditoria. Ele pode ser reativado editando o cadastro depois."
                ),
            }
        )
        return context


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


class ProfessionalRecordAccessMixin(RoleRequiredMixin):
    allowed_roles = [UserProfile.Role.PROFESSIONAL]

    def get_professional(self):
        profile = get_profile(self.request.user)
        if self.request.user.is_superuser and profile and profile.professional_id:
            return profile.professional
        if profile and profile.is_professional and profile.professional_id:
            return profile.professional
        return None


class ProfessionalRecordPatientListView(ProfessionalRecordAccessMixin, SearchableListView, ListView):
    model = Patient
    template_name = "patients/note_patient_list.html"
    context_object_name = "patients"
    paginate_by = 12
    search_fields = ["full_name", "cpf", "phone", "email"]

    def get_queryset(self):
        professional = self.get_professional()
        if not professional:
            return Patient.objects.none()
        queryset = patients_for_user(self.request.user).annotate(
            record_count=Count("professional_notes", filter=Q(professional_notes__professional=professional))
        )
        query = self.request.GET.get("q", "").strip()
        if query:
            filters = Q()
            for field in self.search_fields:
                filters |= Q(**{f"{field}__icontains": query})
            queryset = queryset.filter(filters)
        return queryset.order_by("full_name")


class ProfessionalNoteListView(ProfessionalRecordAccessMixin, SearchableListView, ListView):
    model = ProfessionalNote
    template_name = "patients/note_list.html"
    context_object_name = "notes"
    paginate_by = 12
    search_fields = ["title", "body", "objective", "record_type", "session_focus", "clinical_status", "conduct"]

    def dispatch(self, request, *args, **kwargs):
        self.patient = get_object_or_404(patients_for_user(request.user), pk=kwargs["patient_pk"])
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        professional = self.get_professional()
        if not professional:
            return ProfessionalNote.objects.none()
        queryset = (
            super()
            .get_queryset()
            .select_related("patient", "professional")
            .filter(patient=self.patient, professional=professional)
        )
        query = self.request.GET.get("q", "").strip()
        if query:
            filters = Q()
            for field in self.search_fields:
                filters |= Q(**{f"{field}__icontains": query})
            queryset = queryset.filter(filters)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["patient"] = self.patient
        return context


class ProfessionalNoteFormMixin(ProfessionalRecordAccessMixin):
    model = ProfessionalNote
    form_class = ProfessionalNoteForm
    template_name = "patients/note_form.html"
    section_label = "Prontuario"

    def dispatch(self, request, *args, **kwargs):
        self.patient = get_object_or_404(patients_for_user(request.user), pk=kwargs["patient_pk"])
        return super().dispatch(request, *args, **kwargs)

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        professional = self.get_professional()
        form.fields["patient"].queryset = Patient.objects.filter(pk=self.patient.pk)
        form.fields["patient"].initial = self.patient
        form.fields["patient"].widget = forms.HiddenInput()
        form.fields["professional"].queryset = form.fields["professional"].queryset.none()
        if professional:
            form.fields["professional"].queryset = professional.__class__.objects.filter(pk=professional.pk)
            form.fields["professional"].initial = professional
            form.fields["professional"].widget = forms.HiddenInput()
        return form

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        if not getattr(self, "object", None):
            kwargs["record_type"] = self.request.GET.get("tipo")
        return kwargs

    def form_valid(self, form):
        professional = self.get_professional()
        form.instance.patient = self.patient
        form.instance.professional = professional
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("patients:patient_notes", args=[self.patient.pk])

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "page_title": self.page_title,
                "section_label": self.section_label,
                "back_url": reverse("patients:patient_notes", args=[self.patient.pk]),
                "patient": self.patient,
                "note_type_options": note_type_options(),
                "record_type_title": context["form"].record_config["title"],
            }
        )
        return context


class ProfessionalNoteCreateView(ProfessionalNoteFormMixin, CreateView):
    page_title = "Novo registro"

    def form_valid(self, form):
        messages.success(self.request, "Evolucao registrada com sucesso.")
        return super().form_valid(form)


class ProfessionalNoteUpdateView(ProfessionalNoteFormMixin, UpdateView):
    page_title = "Editar evolucao"

    def get_queryset(self):
        professional = self.get_professional()
        if not professional:
            return ProfessionalNote.objects.none()
        return ProfessionalNote.objects.filter(patient=self.patient, professional=professional)

    def form_valid(self, form):
        messages.success(self.request, "Evolucao atualizada com sucesso.")
        return super().form_valid(form)


class ProfessionalRecordExportView(ProfessionalRecordAccessMixin, View):
    def dispatch(self, request, *args, **kwargs):
        self.patient = get_object_or_404(patients_for_user(request.user), pk=kwargs["patient_pk"])
        return super().dispatch(request, *args, **kwargs)

    def get_notes(self):
        professional = self.get_professional()
        if not professional:
            return ProfessionalNote.objects.none()
        return ProfessionalNote.objects.filter(patient=self.patient, professional=professional).order_by("created_at")

    def patient_rows(self):
        patient = self.patient
        return [
            ("Nome", patient.full_name),
            ("CPF", patient.cpf or "-"),
            ("Nascimento", patient.birth_date.strftime("%d/%m/%Y") if patient.birth_date else "-"),
            ("Telefone", patient.phone or "-"),
            ("E-mail", patient.email or "-"),
            ("Contato de emergencia", patient.emergency_contact or "-"),
            ("Endereco", patient.address or "-"),
            ("Observacoes clinicas", patient.clinical_notes or "-"),
            ("Status", "Ativo" if patient.active else "Inativo"),
        ]

    def professional_rows(self):
        professional = self.get_professional()
        return [
            ("Nome", professional.full_name),
            ("Especialidade", professional.get_specialty_display()),
            ("Registro", professional.registration_number or "-"),
            ("Telefone", professional.phone or "-"),
            ("E-mail", professional.email or "-"),
            ("Observacoes", professional.bio or "-"),
        ]

    def note_rows(self):
        return [
            (
                note.created_at.strftime("%d/%m/%Y %H:%M"),
                note.updated_at.strftime("%d/%m/%Y %H:%M"),
                note.title,
                note.get_record_type_display(),
                note.get_session_focus_display() if note.session_focus else "-",
                note.objective or "-",
                note.structured_summary,
                note.exercise_groups_display,
                note.pain_level if note.pain_level is not None else "-",
                note.get_clinical_status_display() if note.clinical_status else "-",
                note.get_conduct_display() if note.conduct else "-",
                note.body,
            )
            for note in self.get_notes()
        ]

    def get(self, request, *args, **kwargs):
        export_format = kwargs["export_format"]
        if export_format == "xlsx":
            return self.export_xlsx()
        return self.export_pdf()

    def export_xlsx(self):
        safe_name = self.patient.full_name.lower().replace(" ", "_")
        return xlsx_response(
            f"prontuario_{safe_name}.xlsx",
            [
                ("Paciente", ["Campo", "Valor"], self.patient_rows()),
                ("Profissional", ["Campo", "Valor"], self.professional_rows()),
                (
                    "Evolucoes",
                    [
                        "Criado em",
                        "Atualizado em",
                        "Resumo",
                        "Tipo",
                        "Foco",
                        "Objetivo",
                        "Dados estruturados",
                        "Selecoes",
                        "Dor",
                        "Evolucao clinica",
                        "Conduta",
                        "Observacoes",
                    ],
                    self.note_rows(),
                ),
            ],
        )

    def export_pdf(self):
        sections = [
            ("Paciente", [f"{label}: {value}" for label, value in self.patient_rows()]),
            ("Profissional", [f"{label}: {value}" for label, value in self.professional_rows()]),
        ]
        tables = [
            (
                "Evolucoes registradas pelo profissional",
                [
                    "Criado em",
                    "Atualizado em",
                    "Resumo",
                    "Tipo",
                    "Foco",
                    "Objetivo",
                    "Dados estruturados",
                    "Selecoes",
                    "Dor",
                    "Evolucao clinica",
                    "Conduta",
                    "Observacoes",
                ],
                self.note_rows(),
            )
        ]
        safe_name = self.patient.full_name.lower().replace(" ", "_")
        return pdf_response(
            f"prontuario_{safe_name}.pdf",
            f"Prontuario - {self.patient.full_name}",
            sections=sections,
            tables=tables,
            landscape_page=True,
        )

# Create your views here.
