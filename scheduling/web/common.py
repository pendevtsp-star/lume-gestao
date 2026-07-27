from datetime import datetime
from datetime import time
from datetime import timedelta
from datetime import timezone as datetime_timezone

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.shortcuts import redirect
from django.shortcuts import render
from django.urls import reverse
from django.urls import reverse_lazy
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views import View
from django.views.generic import CreateView, DeleteView, FormView, ListView, UpdateView

from accounts.models import UserProfile
from accounts.permissions import FinanceAccessMixin, RoleRequiredMixin, get_profile
from core.deletion import (
    DELETE_ACTION_NOW,
    DeletionDecisionMixin,
    hard_delete_availability,
    hard_delete_service_package,
    mark_active_object_for_deletion,
    mark_package_for_deletion,
)
from core.models import ClinicSettings
from core.web.mixins import FormContextMixin, SearchableListView
from patients.models import Patient
from patients.selectors import patients_visible_to_user
from scheduling.forms import (
    AgendaSettingsForm,
    AppointmentAttendanceForm,
    AppointmentForm,
    AppointmentRescheduleSlotForm,
    AppointmentSlotSearchForm,
    PatientCheckInForm,
    PatientGoalForm,
    PatientNotificationPreferenceForm,
    OperationalCalendarEventForm,
    ProfessionalAvailabilityForm,
    ProfessionalAvailabilityBatchForm,
    RescheduleRequestForm,
    ServicePackageForm,
)
from scheduling.models import (
    Appointment,
    AppointmentAttendance,
    AppointmentSeries,
    PatientCheckIn,
    PatientGoal,
    PatientNotification,
    PatientNotificationPreference,
    OperationalCalendarEvent,
    ProfessionalAvailability,
    RescheduleRequest,
    ServicePackage,
    ServicePackageAdjustment,
    ServiceUsage,
)
from scheduling.services import (
    completion_package_for_appointment,
    ensure_credit_for_appointment,
    generate_operational_notifications,
    lock_professional_schedule,
    mark_absence,
    patient_monthly_summary,
    record_attendance_for_canceled_appointment,
    record_attendance_for_completed_appointment,
    record_attendance_for_rescheduled_appointment,
)
from scheduling.booking import (
    build_occurrence_payloads,
    create_series_for_dates,
    has_future_series_appointments,
    recurrence_dates_from_form,
)
from scheduling.selectors import (
    annotate_credit_adjustment_flags,
    appointments_for_user,
    availabilities_for_user,
    build_calendar_session_groups,
    filter_appointment_search,
    filter_availability_search,
    visible_patient_ids_for_user,
)
from core.models import WhatsAppMessageLog
from scheduling.slots import generate_available_slots, make_local_datetime, slot_availability_snapshot, slot_is_available


ACTIVE_APPOINTMENT_STATUSES = [Appointment.Status.REQUESTED, Appointment.Status.SCHEDULED]


class AppointmentAccessMixin(RoleRequiredMixin):
    allowed_roles = [
        UserProfile.Role.PATIENT,
        UserProfile.Role.PROFESSIONAL,
        UserProfile.Role.ADMINISTRATION,
        UserProfile.Role.MANAGEMENT,
    ]


class AgendaSettingsAccessMixin(RoleRequiredMixin):
    allowed_roles = [
        UserProfile.Role.PROFESSIONAL,
        UserProfile.Role.ADMINISTRATION,
        UserProfile.Role.MANAGEMENT,
    ]


class AgendaOperationalAccessMixin(RoleRequiredMixin):
    allowed_roles = [
        UserProfile.Role.PROFESSIONAL,
        UserProfile.Role.ADMINISTRATION,
        UserProfile.Role.MANAGEMENT,
    ]


class NotificationGenerationAccessMixin(RoleRequiredMixin):
    allowed_roles = [
        UserProfile.Role.ADMINISTRATION,
        UserProfile.Role.MANAGEMENT,
    ]


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


def user_can_manage_agenda(user):
    if user.is_superuser:
        return True
    profile = get_profile(user)
    return bool(
        profile
        and profile.role
        in {
            UserProfile.Role.PROFESSIONAL,
            UserProfile.Role.ADMINISTRATION,
            UserProfile.Role.MANAGEMENT,
        }
    )


def add_model_validation_errors(form, error):
    if hasattr(error, "message_dict"):
        for field_messages in error.message_dict.values():
            for message in field_messages:
                form.add_error(None, message)
        return
    for message in error.messages:
        form.add_error(None, message)


def calendar_week_start(request):
    selected = parse_date(request.GET.get("semana", "")) or timezone.localdate()
    return selected - timedelta(days=selected.weekday())


def agenda_redirect_for_date(day):
    week_start = day - timedelta(days=day.weekday())
    return redirect(f"{reverse('scheduling:appointments')}?semana={week_start.isoformat()}&dia={day.isoformat()}")


def escape_ics(value):
    return (
        str(value or "")
        .replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\n", "\\n")
    )


def format_ics_datetime(value):
    return value.astimezone(datetime_timezone.utc).strftime("%Y%m%dT%H%M%SZ")
