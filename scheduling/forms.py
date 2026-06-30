from django import forms
from django.db import models
from django.utils import timezone
from calendar import monthrange
from datetime import timedelta

from accounts.models import UserProfile
from accounts.permissions import get_profile
from billing.models import Membership, ServicePlan
from core.forms import StyledModelForm
from core.models import ClinicSettings
from patients.models import Patient
from patients.services import patient_professional_link_exists, patient_ids_for_professional, professional_ids_for_patient
from scheduling.models import Appointment, ProfessionalAvailability, ServicePackage
from scheduling.services import package_defaults_for_plan, resolve_membership_for_plan
from team.models import Professional


DURATION_CHOICES = [
    (30, "30 minutos"),
    (45, "45 minutos"),
    (60, "1 hora"),
    (90, "1 hora e 30 minutos"),
]


class StyledForm(forms.Form):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, forms.CheckboxInput):
                widget.attrs.setdefault("class", "checkbox")
            elif isinstance(widget, forms.HiddenInput):
                continue
            else:
                widget.attrs.setdefault("class", "field-control")


def visible_patients_for_request(request):
    queryset = Patient.objects.filter(active=True)
    if not request:
        return queryset
    if request.user.is_superuser:
        return queryset

    profile = get_profile(request.user)
    if not profile:
        return queryset.none()
    if profile.role in {UserProfile.Role.ADMINISTRATION, UserProfile.Role.MANAGEMENT}:
        return queryset
    if profile.is_patient and profile.patient_id:
        return queryset.filter(pk=profile.patient_id)
    if profile.is_professional and profile.professional_id:
        return queryset.filter(pk__in=patient_ids_for_professional(profile.professional))
    return queryset.none()


def visible_professionals_for_request(request, patient=None):
    queryset = Professional.objects.filter(active=True)
    if not request:
        return queryset
    if request.user.is_superuser:
        return queryset

    profile = get_profile(request.user)
    if not profile:
        return queryset.none()
    if profile.role in {UserProfile.Role.ADMINISTRATION, UserProfile.Role.MANAGEMENT}:
        return queryset
    if profile.is_professional and profile.professional_id:
        return queryset.filter(pk=profile.professional_id)
    if profile.is_patient and profile.patient_id:
        patient = patient or profile.patient
        return queryset.filter(pk__in=professional_ids_for_patient(patient))
    return queryset.none()


class AppointmentForm(StyledModelForm):
    class Meta:
        model = Appointment
        fields = [
            "patient",
            "professional",
            "service_plan",
            "starts_at",
            "ends_at",
            "status",
            "slot_capacity",
            "service_units",
            "notes",
        ]
        widgets = {
            "starts_at": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "ends_at": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "notes": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop("request", None)
        super().__init__(*args, **kwargs)
        if not self.request:
            return

        profile = get_profile(self.request.user)
        if not profile or self.request.user.is_superuser or profile.role in {
            UserProfile.Role.ADMINISTRATION,
            UserProfile.Role.MANAGEMENT,
        }:
            return

        if profile.is_patient and profile.patient_id:
            self.fields["patient"].queryset = self.fields["patient"].queryset.filter(pk=profile.patient_id)
            self.fields["professional"].queryset = Professional.objects.filter(
                pk__in=professional_ids_for_patient(profile.patient),
                active=True,
            )
            self.fields["status"].choices = [
                (Appointment.Status.REQUESTED, "Solicitado"),
                (Appointment.Status.CANCELED, "Cancelado"),
            ]
            self.fields["slot_capacity"].widget = forms.HiddenInput()

        if profile.is_professional and profile.professional_id:
            self.fields["professional"].queryset = self.fields["professional"].queryset.filter(pk=profile.professional_id)
            self.fields["patient"].queryset = self.fields["patient"].queryset.filter(
                pk__in=patient_ids_for_professional(profile.professional)
            )


class AppointmentSlotSearchForm(StyledForm):
    class RepeatMode(models.TextChoices):
        NONE = "none", "Somente esta sessao"
        WEEKLY = "weekly", "Repetir semanalmente"

    patients = forms.ModelMultipleChoiceField(
        label="Paciente(s)",
        queryset=Patient.objects.none(),
        widget=forms.SelectMultiple(attrs={"size": 6}),
    )
    service_plan = forms.ModelChoiceField(
        label="Plano/Servico",
        queryset=ServicePlan.objects.none(),
        required=False,
        help_text="Opcional quando o paciente tem apenas uma adesao ativa. Obrigatorio se houver mais de um servico ativo.",
    )
    professional = forms.ModelChoiceField(label="Profissional", queryset=Professional.objects.none())
    appointment_date = forms.DateField(
        label="Data",
        initial=timezone.localdate,
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    duration_minutes = forms.ChoiceField(label="Duracao", choices=DURATION_CHOICES, initial=60)
    service_units = forms.IntegerField(label="Creditos previstos", min_value=1, initial=1)
    session_capacity = forms.IntegerField(
        label="Capacidade da sessao",
        min_value=1,
        initial=1,
        required=False,
        widget=forms.HiddenInput,
    )
    repeat_mode = forms.ChoiceField(
        label="Recorrencia",
        choices=RepeatMode.choices,
        initial=RepeatMode.NONE,
        required=False,
    )
    repeat_interval_weeks = forms.IntegerField(label="Repetir a cada", min_value=1, initial=1, required=False)
    repeat_until = forms.DateField(
        label="Repetir ate",
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    repeat_count = forms.IntegerField(label="Quantidade de sessoes", min_value=2, required=False)
    notes = forms.CharField(
        label="Observacoes",
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
    )
    selected_start = forms.TimeField(required=False, input_formats=["%H:%M"], widget=forms.HiddenInput)

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop("request", None)
        super().__init__(*args, **kwargs)
        self.fields["patients"].queryset = visible_patients_for_request(self.request)
        self.fields["service_plan"].queryset = ServicePlan.objects.filter(active=True).order_by("category", "name")
        self.fields["professional"].queryset = visible_professionals_for_request(self.request)
        self.fields["service_units"].widget = forms.HiddenInput()

        if self.request:
            profile = get_profile(self.request.user)
            if profile and profile.is_patient and profile.patient_id:
                self.fields["patients"].initial = [profile.patient.pk]
                self.fields["patients"].widget = forms.MultipleHiddenInput()
                self.fields["session_capacity"].widget = forms.HiddenInput()
                self.fields["repeat_mode"].widget = forms.HiddenInput()
                self.fields["repeat_interval_weeks"].widget = forms.HiddenInput()
                self.fields["repeat_until"].widget = forms.HiddenInput()
                self.fields["repeat_count"].widget = forms.HiddenInput()
            if profile and profile.is_professional and profile.professional_id:
                self.fields["professional"].initial = profile.professional
                self.fields["professional"].widget = forms.HiddenInput()

    def clean_duration_minutes(self):
        return int(self.cleaned_data["duration_minutes"])

    def clean_repeat_interval_weeks(self):
        value = self.cleaned_data.get("repeat_interval_weeks") or 1
        return int(value)

    def clean(self):
        cleaned_data = super().clean()
        patients = cleaned_data.get("patients") or []
        professional = cleaned_data.get("professional")
        repeat_mode = cleaned_data.get("repeat_mode") or self.RepeatMode.NONE
        repeat_until = cleaned_data.get("repeat_until")
        repeat_count = cleaned_data.get("repeat_count")
        session_capacity = cleaned_data.get("session_capacity") or 1
        service_plan = cleaned_data.get("service_plan")
        cleaned_data["repeat_mode"] = repeat_mode
        cleaned_data["session_capacity"] = session_capacity

        if self.request and patients and professional:
            for patient in patients:
                allowed_professionals = visible_professionals_for_request(self.request, patient=patient)
                if not allowed_professionals.filter(pk=professional.pk).exists() and not patient_professional_link_exists(
                    patient, professional
                ):
                    raise forms.ValidationError(f"{patient.full_name} nao pode ser agendado com este profissional.")

        if patients:
            inferred_plan_ids = []
            for patient in patients:
                active_plan_ids = list(
                    ServicePackage.objects.filter(
                        membership__patient=patient,
                        status=ServicePackage.Status.ACTIVE,
                        used_sessions__lt=models.F("total_sessions"),
                    )
                    .values_list("membership__plan_id", flat=True)
                    .distinct()
                )
                if service_plan:
                    if active_plan_ids and service_plan.pk not in active_plan_ids:
                        self.add_error(
                            "service_plan",
                            f"{patient.full_name} nao possui saldo ativo para este plano/servico.",
                        )
                elif len(active_plan_ids) == 1:
                    inferred_plan_ids.append(active_plan_ids[0])
                elif len(active_plan_ids) > 1:
                    self.add_error(
                        "service_plan",
                        f"{patient.full_name} possui mais de uma adesao ativa. Escolha o plano/servico do agendamento.",
                    )
            if not service_plan and inferred_plan_ids and len(set(inferred_plan_ids)) == 1:
                cleaned_data["service_plan"] = ServicePlan.objects.get(pk=inferred_plan_ids[0])
            elif not service_plan and len(set(inferred_plan_ids)) > 1:
                self.add_error("service_plan", "Escolha um plano/servico comum aos pacientes selecionados.")

        if repeat_mode == self.RepeatMode.WEEKLY:
            if not repeat_until and not repeat_count:
                raise forms.ValidationError("Informe uma data final ou a quantidade de sessoes para a recorrencia.")
            if repeat_until and cleaned_data.get("appointment_date") and repeat_until < cleaned_data["appointment_date"]:
                self.add_error("repeat_until", "A data final nao pode ser anterior a primeira sessao.")
        return cleaned_data


class AppointmentRescheduleSlotForm(StyledForm):
    class Scope(models.TextChoices):
        CURRENT = "current", "Apenas esta sessao"
        CURRENT_AND_FUTURE = "current_and_future", "Esta e as proximas sessoes"

    professional = forms.ModelChoiceField(label="Profissional", queryset=Professional.objects.none())
    appointment_date = forms.DateField(
        label="Nova data",
        initial=timezone.localdate,
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    duration_minutes = forms.ChoiceField(label="Duracao", choices=DURATION_CHOICES, initial=60)
    reschedule_scope = forms.ChoiceField(
        label="Aplicar reagendamento",
        choices=Scope.choices,
        initial=Scope.CURRENT,
        required=False,
    )
    notes = forms.CharField(
        label="Observacoes",
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
    )
    selected_start = forms.TimeField(required=False, input_formats=["%H:%M"], widget=forms.HiddenInput)

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop("request", None)
        self.original_appointment = kwargs.pop("original_appointment", None)
        self.has_future_series = kwargs.pop("has_future_series", False)
        super().__init__(*args, **kwargs)
        patient = self.original_appointment.patient if self.original_appointment else None
        self.fields["professional"].queryset = visible_professionals_for_request(self.request, patient=patient)

        if self.original_appointment:
            self.fields["professional"].initial = self.original_appointment.professional
            self.fields["appointment_date"].initial = timezone.localtime(self.original_appointment.starts_at).date()
            duration = self.original_appointment.ends_at - self.original_appointment.starts_at
            self.fields["duration_minutes"].initial = int(duration.total_seconds() // 60)
            self.fields["duration_minutes"].widget = forms.HiddenInput()
            self.fields["notes"].initial = self.original_appointment.notes

        if not self.has_future_series:
            self.fields["reschedule_scope"].widget = forms.HiddenInput()
            self.fields["reschedule_scope"].initial = self.Scope.CURRENT

        if self.request:
            profile = get_profile(self.request.user)
            if profile and profile.is_professional and profile.professional_id:
                self.fields["professional"].initial = profile.professional
                self.fields["professional"].widget = forms.HiddenInput()

    def clean_duration_minutes(self):
        return int(self.cleaned_data["duration_minutes"])


class ProfessionalAvailabilityForm(StyledModelForm):
    class Meta:
        model = ProfessionalAvailability
        fields = [
            "professional",
            "weekday",
            "starts_at",
            "ends_at",
            "session_capacity",
            "valid_from",
            "valid_until",
            "active",
            "notes",
        ]
        widgets = {
            "starts_at": forms.TimeInput(attrs={"type": "time"}),
            "ends_at": forms.TimeInput(attrs={"type": "time"}),
            "valid_from": forms.DateInput(attrs={"type": "date"}),
            "valid_until": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop("request", None)
        super().__init__(*args, **kwargs)
        if not self.request:
            return
        profile = get_profile(self.request.user)
        if profile and profile.is_professional and profile.professional_id:
            self.fields["professional"].queryset = Professional.objects.filter(pk=profile.professional_id, active=True)


class ProfessionalAvailabilityBatchForm(StyledForm):
    class ValidScope(models.TextChoices):
        WEEK = "week", "Apenas a semana da data escolhida"
        MONTH = "month", "Apenas o mes da data escolhida"
        CONTINUOUS = "continuous", "Sem data final"
        CUSTOM = "custom", "Periodo personalizado"

    professional = forms.ModelChoiceField(label="Profissional", queryset=Professional.objects.none())
    weekdays = forms.MultipleChoiceField(
        label="Dias da semana",
        choices=ProfessionalAvailability.Weekday.choices,
        widget=forms.CheckboxSelectMultiple,
    )
    reference_date = forms.DateField(
        label="Data de referencia",
        initial=timezone.localdate,
        widget=forms.DateInput(attrs={"type": "date"}),
        help_text="Usada para calcular a semana ou o mes em que esta regra vale.",
    )
    valid_scope = forms.ChoiceField(
        label="Validade",
        choices=ValidScope.choices,
        initial=ValidScope.CONTINUOUS,
        widget=forms.RadioSelect,
    )
    custom_valid_from = forms.DateField(
        label="Inicio personalizado",
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    custom_valid_until = forms.DateField(
        label="Fim personalizado",
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    window_1_start = forms.TimeField(label="Inicio 1", widget=forms.TimeInput(attrs={"type": "time"}))
    window_1_end = forms.TimeField(label="Fim 1", widget=forms.TimeInput(attrs={"type": "time"}))
    window_2_start = forms.TimeField(label="Inicio 2", required=False, widget=forms.TimeInput(attrs={"type": "time"}))
    window_2_end = forms.TimeField(label="Fim 2", required=False, widget=forms.TimeInput(attrs={"type": "time"}))
    window_3_start = forms.TimeField(label="Inicio 3", required=False, widget=forms.TimeInput(attrs={"type": "time"}))
    window_3_end = forms.TimeField(label="Fim 3", required=False, widget=forms.TimeInput(attrs={"type": "time"}))
    session_capacity = forms.IntegerField(label="Capacidade por sessao", min_value=1, initial=1)
    active = forms.BooleanField(label="Ativa", required=False, initial=True)
    notes = forms.CharField(label="Observacoes", required=False, widget=forms.Textarea(attrs={"rows": 3}))

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop("request", None)
        super().__init__(*args, **kwargs)
        self.fields["professional"].queryset = visible_professionals_for_request(self.request)
        self.fields["weekdays"].widget.attrs.setdefault("class", "weekday-checkboxes")
        self.fields["valid_scope"].widget.attrs.setdefault("class", "validity-radios")

        if self.request:
            profile = get_profile(self.request.user)
            if profile and profile.is_professional and profile.professional_id:
                self.fields["professional"].initial = profile.professional
                self.fields["professional"].widget = forms.HiddenInput()

    def clean_weekdays(self):
        weekdays = self.cleaned_data.get("weekdays") or []
        return [int(value) for value in weekdays]

    def clean(self):
        cleaned_data = super().clean()
        reference_date = cleaned_data.get("reference_date") or timezone.localdate()
        valid_scope = cleaned_data.get("valid_scope") or self.ValidScope.CONTINUOUS
        windows = []

        for index in range(1, 4):
            start = cleaned_data.get(f"window_{index}_start")
            end = cleaned_data.get(f"window_{index}_end")
            if bool(start) != bool(end):
                self.add_error(f"window_{index}_start", "Preencha inicio e fim deste horario.")
                self.add_error(f"window_{index}_end", "Preencha inicio e fim deste horario.")
                continue
            if not start and not end:
                continue
            if end <= start:
                self.add_error(f"window_{index}_end", "O fim deve ser posterior ao inicio.")
                continue
            windows.append((start, end))

        for current_start, current_end in windows:
            for other_start, other_end in windows:
                if (current_start, current_end) == (other_start, other_end):
                    continue
                if current_start < other_end and current_end > other_start:
                    raise forms.ValidationError("As janelas de horario nao podem se sobrepor.")

        if not windows:
            raise forms.ValidationError("Informe ao menos um horario de atendimento.")

        if valid_scope == self.ValidScope.WEEK:
            valid_from = reference_date - timedelta(days=reference_date.weekday())
            valid_until = valid_from + timedelta(days=6)
        elif valid_scope == self.ValidScope.MONTH:
            last_day = monthrange(reference_date.year, reference_date.month)[1]
            valid_from = reference_date.replace(day=1)
            valid_until = reference_date.replace(day=last_day)
        elif valid_scope == self.ValidScope.CUSTOM:
            valid_from = cleaned_data.get("custom_valid_from")
            valid_until = cleaned_data.get("custom_valid_until")
            if not valid_from or not valid_until:
                raise forms.ValidationError("Informe inicio e fim para o periodo personalizado.")
            if valid_until < valid_from:
                self.add_error("custom_valid_until", "A data final nao pode ser anterior ao inicio.")
        else:
            valid_from = reference_date
            valid_until = None

        cleaned_data["time_windows"] = windows
        cleaned_data["valid_from"] = valid_from
        cleaned_data["valid_until"] = valid_until
        return cleaned_data


class ServicePackageForm(StyledModelForm):
    patient = forms.ModelChoiceField(label="Paciente", queryset=Patient.objects.none())
    plan = forms.ModelChoiceField(label="Plano/Servico", queryset=ServicePlan.objects.none())

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["patient"].queryset = Patient.objects.filter(active=True).order_by("full_name")
        self.fields["plan"].queryset = ServicePlan.objects.filter(active=True).order_by("category", "name")
        self.fields["patient"].help_text = "Escolha o paciente que aderiu ao plano ou servico."
        self.fields["plan"].help_text = "Total de atendimentos, validade e mensalidade serao herdados automaticamente."
        self.fields["starts_on"].help_text = "A validade sera calculada pela duracao configurada no plano/servico."

        if self.instance and self.instance.pk and self.instance.membership_id:
            self.fields["patient"].initial = self.instance.membership.patient_id
            self.fields["plan"].initial = self.instance.membership.plan_id

    class Meta:
        model = ServicePackage
        fields = ["patient", "plan", "starts_on", "status", "notes"]
        widgets = {
            "starts_on": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 4}),
        }

    def clean(self):
        cleaned_data = super().clean()
        patient = cleaned_data.get("patient")
        plan = cleaned_data.get("plan")
        if not patient or not plan:
            return cleaned_data

        starts_on = cleaned_data.get("starts_on") or timezone.localdate()
        defaults = package_defaults_for_plan(plan, starts_on)
        self.instance.total_sessions = defaults["total_sessions"]
        self.instance.expires_on = defaults["expires_on"]
        self.instance.used_sessions = self.instance.used_sessions or 0
        used_sessions = self.instance.used_sessions if self.instance and self.instance.pk else 0
        if used_sessions > defaults["total_sessions"]:
            self.add_error(
                "plan",
                "Este plano/servico possui menos atendimentos do que ja foi usado nesta adesao.",
            )
        return cleaned_data

    def resolve_membership(self):
        patient = self.cleaned_data["patient"]
        plan = self.cleaned_data["plan"]
        membership, _created = resolve_membership_for_plan(
            patient,
            plan,
            starts_on=self.cleaned_data.get("starts_on") or timezone.localdate(),
        )
        return membership

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.membership = self.resolve_membership()
        defaults = package_defaults_for_plan(instance.membership.plan, instance.starts_on)
        instance.total_sessions = defaults["total_sessions"]
        instance.expires_on = defaults["expires_on"]
        if not instance.pk:
            instance.used_sessions = 0
        if commit:
            instance.save()
            self.save_m2m()
        return instance


class AgendaSettingsForm(StyledModelForm):
    class Meta:
        model = ClinicSettings
        fields = [
            "opening_time",
            "closing_time",
            "cancellation_deadline_hours",
            "rescheduling_deadline_hours",
            "cancellation_policy",
            "rescheduling_policy",
        ]
        widgets = {
            "opening_time": forms.TimeInput(attrs={"type": "time"}),
            "closing_time": forms.TimeInput(attrs={"type": "time"}),
            "cancellation_policy": forms.Textarea(attrs={"rows": 4}),
            "rescheduling_policy": forms.Textarea(attrs={"rows": 4}),
        }
