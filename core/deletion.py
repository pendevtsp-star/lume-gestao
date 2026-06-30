from django.contrib import messages
from django.db.models import F, Q
from django.db.models import ProtectedError
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone


DELETE_ACTION_CANCEL = "cancel"
DELETE_ACTION_DEACTIVATE = "deactivate"
DELETE_ACTION_NOW = "delete_now"


FINAL_APPOINTMENT_STATUSES = {"completed", "rescheduled", "canceled", "no_show"}


def _now():
    return timezone.now()


def _delete_appointment_queryset(appointments):
    from scheduling.models import ServiceUsage

    ServiceUsage.objects.filter(appointment__in=appointments).delete()
    appointments.delete()


def _delete_membership_queryset(memberships):
    from billing.models import Payment
    from scheduling.models import ServicePackage, ServiceUsage

    packages = ServicePackage.objects.filter(membership__in=memberships)
    ServiceUsage.objects.filter(service_package__in=packages).delete()
    packages.delete()
    Payment.objects.filter(membership__in=memberships).delete()
    memberships.delete()


def set_patient_user_active(patient, active):
    profile = getattr(patient, "user_profile", None)
    if not profile or not profile.user_id:
        return
    user = profile.user
    if user.is_active == active:
        return
    user.is_active = active
    user.save(update_fields=["is_active"])


def delete_patient_user(patient):
    profile = getattr(patient, "user_profile", None)
    if profile and profile.user_id:
        profile.user.delete()


def hard_delete_patient(patient):
    from billing.models import Charge, Membership, Payment
    from scheduling.models import Appointment

    _delete_appointment_queryset(Appointment.objects.filter(patient=patient))
    _delete_membership_queryset(Membership.objects.filter(patient=patient))
    Payment.objects.filter(patient=patient).delete()
    Charge.objects.filter(patient=patient).update(patient=None)
    delete_patient_user(patient)
    patient.delete()


def hard_delete_professional(professional):
    from patients.models import ProfessionalNote, ProfessionalPatientAssignment
    from scheduling.models import Appointment

    _delete_appointment_queryset(Appointment.objects.filter(professional=professional))
    ProfessionalNote.objects.filter(professional=professional).delete()
    ProfessionalPatientAssignment.objects.filter(professional=professional).delete()
    professional.delete()


def hard_delete_service_plan(plan):
    from billing.models import Membership

    _delete_membership_queryset(Membership.objects.filter(plan=plan))
    plan.delete()


def hard_delete_membership(membership):
    _delete_membership_queryset(membership.__class__.objects.filter(pk=membership.pk))


def hard_delete_expense(expense):
    expense.delete()


def hard_delete_service_package(package):
    from scheduling.models import ServiceUsage

    ServiceUsage.objects.filter(service_package=package).delete()
    package.delete()


def hard_delete_availability(availability):
    availability.delete()


def patient_has_pending_obligations(patient):
    from billing.models import Charge, Membership, Payment
    from scheduling.models import Appointment, ServicePackage

    if Appointment.objects.filter(patient=patient).exclude(status__in=FINAL_APPOINTMENT_STATUSES).exists():
        return True
    if Charge.objects.filter(patient=patient, status__in=[Charge.Status.OPEN, Charge.Status.OVERDUE]).exists():
        return True
    memberships = Membership.objects.filter(patient=patient)
    if memberships.filter(status__in=[Membership.Status.ACTIVE, Membership.Status.PAUSED]).exists():
        return True
    if Payment.objects.filter(
        Q(membership__in=memberships) | Q(patient=patient),
        status__in=[Payment.Status.PENDING, Payment.Status.OVERDUE],
    ).exists():
        return True
    return ServicePackage.objects.filter(
        membership__in=memberships,
        status=ServicePackage.Status.ACTIVE,
        used_sessions__lt=F("total_sessions"),
    ).exists()


def professional_has_pending_obligations(professional):
    from scheduling.models import Appointment

    return Appointment.objects.filter(professional=professional).exclude(status__in=FINAL_APPOINTMENT_STATUSES).exists()


def service_plan_has_pending_obligations(plan):
    from billing.models import Membership, Payment
    from scheduling.models import ServicePackage

    memberships = Membership.objects.filter(plan=plan)
    if memberships.filter(status__in=[Membership.Status.ACTIVE, Membership.Status.PAUSED]).exists():
        return True
    if Payment.objects.filter(membership__in=memberships, status__in=[Payment.Status.PENDING, Payment.Status.OVERDUE]).exists():
        return True
    return ServicePackage.objects.filter(
        membership__in=memberships,
        status=ServicePackage.Status.ACTIVE,
        used_sessions__lt=F("total_sessions"),
    ).exists()


def service_package_has_pending_obligations(package):
    return package.status == package.Status.ACTIVE and package.used_sessions < package.total_sessions


def membership_has_pending_obligations(membership):
    from billing.models import Payment
    from scheduling.models import ServicePackage

    if Payment.objects.filter(
        membership=membership,
        status__in=[Payment.Status.PENDING, Payment.Status.OVERDUE],
    ).exists():
        return True
    return ServicePackage.objects.filter(
        membership=membership,
        status=ServicePackage.Status.ACTIVE,
        used_sessions__lt=F("total_sessions"),
    ).exists()


def mark_membership_for_deletion(membership):
    from billing.models import Payment
    from scheduling.models import ServicePackage

    membership.status = membership.Status.CANCELED
    membership.notes = append_deletion_note(membership.notes)
    membership.full_clean()
    membership.save(update_fields=["status", "notes", "updated_at"])
    Payment.objects.filter(
        membership=membership,
        status__in=[Payment.Status.PENDING, Payment.Status.OVERDUE],
    ).update(status=Payment.Status.CANCELED, paid_at=None, updated_at=_now())
    ServicePackage.objects.filter(membership=membership, status=ServicePackage.Status.ACTIVE).update(
        status=ServicePackage.Status.CANCELED,
        deletion_requested_at=_now(),
        updated_at=_now(),
    )


def mark_expense_for_deletion(expense):
    expense.status = expense.Status.CANCELED
    expense.paid_at = None
    expense.notes = append_deletion_note(expense.notes)
    expense.full_clean()
    expense.save(update_fields=["status", "paid_at", "notes", "updated_at"])


def append_deletion_note(notes):
    timestamp = timezone.localtime(_now()).strftime("%d/%m/%Y %H:%M")
    note = f"Cancelado para nao compor relatorios em {timestamp}."
    return f"{notes}\n{note}".strip() if notes else note


def mark_active_object_for_deletion(instance):
    instance.active = False
    instance.deletion_requested_at = _now()
    instance.full_clean()
    instance.save(update_fields=["active", "deletion_requested_at", "updated_at"])


def mark_package_for_deletion(package):
    package.status = package.Status.CANCELED
    package.deletion_requested_at = _now()
    package.full_clean()
    package.save(update_fields=["status", "deletion_requested_at", "updated_at"])


def cleanup_pending_deletions(limit=25):
    from billing.models import ServicePlan
    from patients.models import Patient
    from scheduling.models import ProfessionalAvailability, ServicePackage
    from team.models import Employee, Professional

    deleted = 0

    for patient in Patient.objects.filter(active=False, deletion_requested_at__isnull=False).order_by("deletion_requested_at")[:limit]:
        if not patient_has_pending_obligations(patient):
            hard_delete_patient(patient)
            deleted += 1

    for professional in Professional.objects.filter(active=False, deletion_requested_at__isnull=False).order_by("deletion_requested_at")[:limit]:
        if not professional_has_pending_obligations(professional):
            hard_delete_professional(professional)
            deleted += 1

    for employee in Employee.objects.filter(active=False, deletion_requested_at__isnull=False).order_by("deletion_requested_at")[:limit]:
        employee.delete()
        deleted += 1

    for plan in ServicePlan.objects.filter(active=False, deletion_requested_at__isnull=False).order_by("deletion_requested_at")[:limit]:
        if not service_plan_has_pending_obligations(plan):
            hard_delete_service_plan(plan)
            deleted += 1

    for availability in ProfessionalAvailability.objects.filter(active=False, deletion_requested_at__isnull=False).order_by("deletion_requested_at")[:limit]:
        hard_delete_availability(availability)
        deleted += 1

    for package in ServicePackage.objects.filter(deletion_requested_at__isnull=False).order_by("deletion_requested_at")[:limit]:
        if not service_package_has_pending_obligations(package):
            hard_delete_service_package(package)
            deleted += 1

    return {"deleted": deleted}


class DeletionDecisionMixin:
    default_delete_action = DELETE_ACTION_DEACTIVATE
    cleanup_after_deactivate = False
    delete_button_label = "Excluir agora"
    deactivate_button_label = "Inativar"
    cancel_button_label = "Cancelar"
    delete_now_explanation = (
        "Remove definitivamente este cadastro e os dados vinculados conhecidos. Use apenas quando tiver certeza."
    )
    deactivate_explanation = (
        "Tira o cadastro da rotina ativa agora. O sistema tentara excluir automaticamente quando nao houver "
        "agendamentos, planos ou cobrancas abertas."
    )

    def get_cancel_url(self):
        return reverse(self.back_url_name)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "delete_button_label": self.delete_button_label,
                "deactivate_button_label": self.deactivate_button_label,
                "cancel_button_label": self.cancel_button_label,
                "delete_now_explanation": self.delete_now_explanation,
                "deactivate_explanation": self.deactivate_explanation,
            }
        )
        return context

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        action = request.POST.get("delete_action") or self.get_default_delete_action()
        if action == DELETE_ACTION_CANCEL:
            return redirect(self.get_cancel_url())
        if action == DELETE_ACTION_NOW:
            return self._handle_delete_now()
        if action == DELETE_ACTION_DEACTIVATE:
            return self._handle_deactivate()
        messages.error(request, "Escolha se deseja inativar ou excluir definitivamente.")
        return redirect(self.get_cancel_url())

    def get_default_delete_action(self):
        return self.default_delete_action

    def _handle_delete_now(self):
        try:
            self.perform_delete_now()
        except ProtectedError:
            messages.error(
                self.request,
                "Nao foi possivel excluir definitivamente porque ainda existem vinculos protegidos no historico.",
            )
            return redirect(self.get_cancel_url())
        messages.success(self.request, self.get_delete_now_success_message())
        return redirect(self.success_url)

    def _handle_deactivate(self):
        self.perform_deactivate()
        if self.cleanup_after_deactivate:
            cleanup_pending_deletions()
        messages.success(self.request, self.get_deactivate_success_message())
        return redirect(self.success_url)

    def perform_delete_now(self):
        self.object.delete()

    def perform_deactivate(self):
        mark_active_object_for_deletion(self.object)

    def get_delete_now_success_message(self):
        return f"{self.entity_label.capitalize()} excluido definitivamente."

    def get_deactivate_success_message(self):
        return (
            f"{self.entity_label.capitalize()} inativado. Se nao houver obrigacoes abertas, "
            "a exclusao definitiva sera feita automaticamente."
        )
