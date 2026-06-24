from django.contrib import messages
from django.db import transaction
from django.db.models import F
from django.shortcuts import get_object_or_404
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, FormView, ListView, UpdateView

from accounts.models import UserProfile
from accounts.permissions import FinanceAccessMixin, RoleRequiredMixin, get_profile
from core.views import FormContextMixin, SearchableListView
from patients.models import ProfessionalPatientAssignment
from scheduling.forms import AppointmentForm, AppointmentRescheduleForm, ProfessionalAvailabilityForm, ServicePackageForm
from scheduling.models import Appointment, ProfessionalAvailability, ServicePackage, ServiceUsage


class AppointmentAccessMixin(RoleRequiredMixin):
    allowed_roles = [
        UserProfile.Role.PATIENT,
        UserProfile.Role.PROFESSIONAL,
        UserProfile.Role.ADMINISTRATION,
        UserProfile.Role.MANAGEMENT,
    ]


def appointments_for_user(user):
    queryset = Appointment.objects.select_related("patient", "professional")
    if user.is_superuser:
        return queryset

    profile = get_profile(user)
    if not profile:
        return queryset.none()
    if profile.role in {UserProfile.Role.ADMINISTRATION, UserProfile.Role.MANAGEMENT}:
        return queryset
    if profile.is_patient and profile.patient_id:
        return queryset.filter(patient=profile.patient)
    if profile.is_professional and profile.professional_id:
        return queryset.filter(professional=profile.professional)
    return queryset.none()


def profile_booking_source(profile):
    if not profile:
        return Appointment.BookingSource.ADMINISTRATION
    if profile.role == UserProfile.Role.PATIENT:
        return Appointment.BookingSource.PATIENT
    if profile.role == UserProfile.Role.PROFESSIONAL:
        return Appointment.BookingSource.PROFESSIONAL
    if profile.role == UserProfile.Role.MANAGEMENT:
        return Appointment.BookingSource.MANAGEMENT
    return Appointment.BookingSource.ADMINISTRATION


class AppointmentListView(AppointmentAccessMixin, SearchableListView, ListView):
    model = Appointment
    template_name = "scheduling/appointment_list.html"
    context_object_name = "appointments"
    paginate_by = 12
    search_fields = ["patient__full_name", "professional__full_name", "status"]

    def get_queryset(self):
        return appointments_for_user(self.request.user)


class AppointmentCreateView(FormContextMixin, AppointmentAccessMixin, CreateView):
    model = Appointment
    form_class = AppointmentForm
    template_name = "core/form.html"
    success_url = reverse_lazy("scheduling:appointments")
    page_title = "Agendamento"
    section_label = "Agenda"
    back_url_name = "scheduling:appointments"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["request"] = self.request
        return kwargs

    def form_valid(self, form):
        profile = get_profile(self.request.user)
        form.instance.booked_by = self.request.user
        if profile:
            form.instance.booking_source = profile_booking_source(profile)
            if profile.role == UserProfile.Role.PATIENT:
                form.instance.booking_source = Appointment.BookingSource.PATIENT
                form.instance.status = Appointment.Status.REQUESTED
        messages.success(self.request, "Agendamento cadastrado com sucesso.")
        return super().form_valid(form)


class AppointmentUpdateView(FormContextMixin, AppointmentAccessMixin, UpdateView):
    allowed_roles = [
        UserProfile.Role.PROFESSIONAL,
        UserProfile.Role.ADMINISTRATION,
        UserProfile.Role.MANAGEMENT,
    ]
    model = Appointment
    form_class = AppointmentForm
    template_name = "core/form.html"
    success_url = reverse_lazy("scheduling:appointments")
    page_title = "Agendamento"
    section_label = "Agenda"
    back_url_name = "scheduling:appointments"

    def get_queryset(self):
        return appointments_for_user(self.request.user)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["request"] = self.request
        return kwargs

    def form_valid(self, form):
        if form.instance.status == Appointment.Status.COMPLETED:
            form.instance.completed_by = self.request.user
            form.instance.completed_at = form.instance.completed_at or timezone.now()
        messages.success(self.request, "Agendamento atualizado com sucesso.")
        return super().form_valid(form)


class AppointmentCancelView(AppointmentAccessMixin, View):
    def post(self, request, pk):
        appointment = get_object_or_404(appointments_for_user(request.user), pk=pk)
        if appointment.status == Appointment.Status.COMPLETED:
            messages.error(request, "Atendimento realizado nao pode ser cancelado.")
            return redirect("scheduling:appointments")
        if hasattr(appointment, "service_usage"):
            messages.error(request, "Atendimento ja baixado nao pode ser cancelado.")
            return redirect("scheduling:appointments")

        appointment.status = Appointment.Status.CANCELED
        appointment.full_clean()
        appointment.save(update_fields=["status", "updated_at"])
        messages.success(request, "Agendamento cancelado sem consumo de credito.")
        return redirect("scheduling:appointments")


class AppointmentRescheduleView(FormContextMixin, AppointmentAccessMixin, FormView):
    form_class = AppointmentRescheduleForm
    template_name = "core/form.html"
    success_url = reverse_lazy("scheduling:appointments")
    page_title = "Reagendamento"
    section_label = "Agenda"
    back_url_name = "scheduling:appointments"

    def dispatch(self, request, *args, **kwargs):
        self.original_appointment = get_object_or_404(appointments_for_user(request.user), pk=kwargs["pk"])
        return super().dispatch(request, *args, **kwargs)

    def get_initial(self):
        initial = super().get_initial()
        initial.update(
            {
                "professional": self.original_appointment.professional,
                "starts_at": self.original_appointment.starts_at,
                "ends_at": self.original_appointment.ends_at,
                "notes": self.original_appointment.notes,
            }
        )
        return initial

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["request"] = self.request
        kwargs["original_appointment"] = self.original_appointment
        return kwargs

    def form_valid(self, form):
        if self.original_appointment.status == Appointment.Status.COMPLETED or hasattr(
            self.original_appointment, "service_usage"
        ):
            messages.error(self.request, "Atendimento ja baixado nao pode ser reagendado.")
            return redirect("scheduling:appointments")

        profile = get_profile(self.request.user)
        new_status = Appointment.Status.REQUESTED if profile and profile.is_patient else Appointment.Status.SCHEDULED

        with transaction.atomic():
            original = Appointment.objects.select_for_update().get(pk=self.original_appointment.pk)
            original.status = Appointment.Status.RESCHEDULED
            original.full_clean()
            original.save(update_fields=["status", "updated_at"])

            new_appointment = Appointment(
                patient=original.patient,
                professional=form.cleaned_data["professional"],
                starts_at=form.cleaned_data["starts_at"],
                ends_at=form.cleaned_data["ends_at"],
                status=new_status,
                booking_source=profile_booking_source(profile),
                booked_by=self.request.user,
                rescheduled_from=original,
                service_units=original.service_units,
                notes=form.cleaned_data.get("notes", ""),
            )
            new_appointment.full_clean()
            new_appointment.save()

        messages.success(self.request, "Agendamento reagendado sem consumo de credito.")
        return super().form_valid(form)


class AppointmentCompleteView(AppointmentAccessMixin, View):
    def post(self, request, pk):
        with transaction.atomic():
            appointment = get_object_or_404(appointments_for_user(request.user).select_for_update(), pk=pk)
            if appointment.status in {Appointment.Status.CANCELED, Appointment.Status.RESCHEDULED}:
                messages.error(request, "Agendamentos cancelados ou reagendados nao consomem credito.")
                return redirect("scheduling:appointments")
            if hasattr(appointment, "service_usage"):
                messages.error(request, "Este atendimento ja foi baixado.")
                return redirect("scheduling:appointments")

            package = (
                ServicePackage.objects.select_for_update()
                .filter(
                    membership__patient=appointment.patient,
                    status=ServicePackage.Status.ACTIVE,
                    used_sessions__lt=F("total_sessions"),
                )
                .order_by("expires_on", "created_at")
                .first()
            )
            if not package:
                messages.error(request, "Nao ha pacote ativo com saldo para este paciente.")
                return redirect("scheduling:appointments")
            if package.remaining_sessions < appointment.service_units:
                messages.error(request, "O pacote nao possui saldo suficiente.")
                return redirect("scheduling:appointments")
            appointment.status = Appointment.Status.COMPLETED
            appointment.completed_by = request.user
            appointment.completed_at = timezone.now()
            appointment.full_clean()
            appointment.save()
            ServiceUsage.objects.create(
                service_package=package,
                appointment=appointment,
                units=appointment.service_units,
                registered_by=request.user,
            )
            package.used_sessions += appointment.service_units
            if package.used_sessions >= package.total_sessions:
                package.status = ServicePackage.Status.FINISHED
            package.full_clean()
            package.save()

        messages.success(request, "Atendimento baixado e pacote atualizado.")
        return redirect("scheduling:appointments")


def availabilities_for_user(user):
    queryset = ProfessionalAvailability.objects.select_related("professional")
    if user.is_superuser:
        return queryset
    profile = get_profile(user)
    if not profile:
        return queryset.none()
    if profile.role in {UserProfile.Role.ADMINISTRATION, UserProfile.Role.MANAGEMENT}:
        return queryset
    if profile.is_professional and profile.professional_id:
        return queryset.filter(professional=profile.professional)
    return queryset.none()


class ProfessionalAvailabilityAccessMixin(RoleRequiredMixin):
    allowed_roles = [
        UserProfile.Role.PROFESSIONAL,
        UserProfile.Role.ADMINISTRATION,
        UserProfile.Role.MANAGEMENT,
    ]


class ProfessionalAvailabilityListView(ProfessionalAvailabilityAccessMixin, SearchableListView, ListView):
    model = ProfessionalAvailability
    template_name = "scheduling/availability_list.html"
    context_object_name = "availabilities"
    paginate_by = 12
    search_fields = ["professional__full_name", "notes"]

    def get_queryset(self):
        return availabilities_for_user(self.request.user)


class ProfessionalAvailabilityCreateView(FormContextMixin, ProfessionalAvailabilityAccessMixin, CreateView):
    model = ProfessionalAvailability
    form_class = ProfessionalAvailabilityForm
    template_name = "core/form.html"
    success_url = reverse_lazy("scheduling:availabilities")
    page_title = "Disponibilidade"
    section_label = "Agenda"
    back_url_name = "scheduling:availabilities"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["request"] = self.request
        return kwargs

    def form_valid(self, form):
        messages.success(self.request, "Disponibilidade cadastrada com sucesso.")
        return super().form_valid(form)


class ProfessionalAvailabilityUpdateView(FormContextMixin, ProfessionalAvailabilityAccessMixin, UpdateView):
    model = ProfessionalAvailability
    form_class = ProfessionalAvailabilityForm
    template_name = "core/form.html"
    success_url = reverse_lazy("scheduling:availabilities")
    page_title = "Disponibilidade"
    section_label = "Agenda"
    back_url_name = "scheduling:availabilities"

    def get_queryset(self):
        return availabilities_for_user(self.request.user)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["request"] = self.request
        return kwargs

    def form_valid(self, form):
        messages.success(self.request, "Disponibilidade atualizada com sucesso.")
        return super().form_valid(form)


class ServicePackageListView(FinanceAccessMixin, SearchableListView, ListView):
    model = ServicePackage
    template_name = "scheduling/package_list.html"
    context_object_name = "packages"
    paginate_by = 12
    search_fields = ["membership__patient__full_name", "membership__plan__name", "status"]

    def get_queryset(self):
        return super().get_queryset().select_related("membership__patient", "membership__plan")


class ServicePackageCreateView(FormContextMixin, FinanceAccessMixin, CreateView):
    model = ServicePackage
    form_class = ServicePackageForm
    template_name = "core/form.html"
    success_url = reverse_lazy("scheduling:packages")
    page_title = "Pacote"
    section_label = "Agenda"
    back_url_name = "scheduling:packages"

    def form_valid(self, form):
        messages.success(self.request, "Pacote cadastrado com sucesso.")
        return super().form_valid(form)


class ServicePackageUpdateView(FormContextMixin, FinanceAccessMixin, UpdateView):
    model = ServicePackage
    form_class = ServicePackageForm
    template_name = "core/form.html"
    success_url = reverse_lazy("scheduling:packages")
    page_title = "Pacote"
    section_label = "Agenda"
    back_url_name = "scheduling:packages"

    def form_valid(self, form):
        messages.success(self.request, "Pacote atualizado com sucesso.")
        return super().form_valid(form)

# Create your views here.
