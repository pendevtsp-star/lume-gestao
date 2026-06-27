from django.db.models import Q

from patients.models import Patient, ProfessionalPatientAssignment


LINK_APPOINTMENT_STATUSES = ["requested", "scheduled", "completed", "no_show"]


def appointment_link_exists(patient, professional):
    from scheduling.models import Appointment

    if not patient or not professional or not patient.active or not professional.active:
        return False
    return Appointment.objects.filter(
        patient=patient,
        professional=professional,
        status__in=LINK_APPOINTMENT_STATUSES,
    ).exists()


def assignment_link_exists(patient, professional):
    if not patient or not professional or not patient.active or not professional.active:
        return False
    return ProfessionalPatientAssignment.objects.filter(
        patient=patient,
        professional=professional,
        active=True,
    ).exists()


def patient_professional_link_exists(patient, professional):
    return assignment_link_exists(patient, professional) or appointment_link_exists(patient, professional)


def patient_ids_for_professional(professional):
    from scheduling.models import Appointment

    if not professional or not professional.active:
        return Patient.objects.none().values_list("pk", flat=True)

    assignment_ids = ProfessionalPatientAssignment.objects.filter(
        professional=professional,
        professional__active=True,
        patient__active=True,
        active=True,
    ).values_list("patient_id", flat=True)
    appointment_ids = Appointment.objects.filter(
        professional=professional,
        professional__active=True,
        patient__active=True,
        status__in=LINK_APPOINTMENT_STATUSES,
    ).values_list("patient_id", flat=True)
    return Patient.objects.filter(Q(pk__in=assignment_ids) | Q(pk__in=appointment_ids)).values_list("pk", flat=True)


def professional_ids_for_patient(patient):
    from scheduling.models import Appointment
    from team.models import Professional

    if not patient or not patient.active:
        return Professional.objects.none().values_list("pk", flat=True)

    assignment_ids = ProfessionalPatientAssignment.objects.filter(
        patient=patient,
        patient__active=True,
        professional__active=True,
        active=True,
    ).values_list("professional_id", flat=True)
    appointment_ids = Appointment.objects.filter(
        patient=patient,
        patient__active=True,
        professional__active=True,
        status__in=LINK_APPOINTMENT_STATUSES,
    ).values_list("professional_id", flat=True)
    return Professional.objects.filter(Q(pk__in=assignment_ids) | Q(pk__in=appointment_ids)).values_list("pk", flat=True)


def refresh_assignment_for_pair(patient, professional):
    if not patient or not professional:
        return
    should_be_active = appointment_link_exists(patient, professional)
    assignment = ProfessionalPatientAssignment.objects.filter(patient=patient, professional=professional).first()
    if should_be_active:
        if assignment:
            if not assignment.active:
                assignment.active = True
                assignment.notes = assignment.notes or "Vinculo automatico por atendimento."
                assignment.save(update_fields=["active", "notes", "updated_at"])
            return
        ProfessionalPatientAssignment.objects.create(
            patient=patient,
            professional=professional,
            active=True,
            notes="Vinculo automatico por atendimento.",
        )
    elif assignment and assignment.active and assignment.notes == "Vinculo automatico por atendimento.":
        assignment.active = False
        assignment.save(update_fields=["active", "updated_at"])


def refresh_assignment_for_appointment(appointment):
    refresh_assignment_for_pair(appointment.patient, appointment.professional)


def deactivate_patient_relationships(patient):
    from scheduling.models import ServicePackage

    for assignment in ProfessionalPatientAssignment.objects.filter(patient=patient, active=True):
        assignment.active = False
        assignment.save(update_fields=["active", "updated_at"])

    for package in ServicePackage.objects.filter(
        membership__patient=patient,
        status=ServicePackage.Status.ACTIVE,
    ):
        package.status = ServicePackage.Status.CANCELED
        package.save(update_fields=["status", "updated_at"])


def deactivate_professional_relationships(professional):
    for assignment in ProfessionalPatientAssignment.objects.filter(professional=professional, active=True):
        assignment.active = False
        assignment.save(update_fields=["active", "updated_at"])
