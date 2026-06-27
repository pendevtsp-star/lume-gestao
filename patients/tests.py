from datetime import timedelta

from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import UserProfile
from billing.models import Membership, ServicePlan
from patients.models import Patient
from patients.models import ProfessionalNote
from patients.models import ProfessionalPatientAssignment
from scheduling.models import Appointment, ServicePackage
from team.models import Professional


class PatientModelTests(TestCase):
    def test_cpf_is_normalized_when_valid(self):
        patient = Patient(full_name="Ana Teste", cpf="123.456.789-01")

        patient.full_clean()

        self.assertEqual(patient.cpf, "12345678901")

    def test_cpf_rejects_invalid_length(self):
        patient = Patient(full_name="Ana Teste", cpf="123")

        with self.assertRaises(ValidationError):
            patient.full_clean()

    def test_blank_cpf_is_stored_as_null(self):
        patient = Patient(full_name="Ana Teste", cpf="")

        patient.full_clean()

        self.assertIsNone(patient.cpf)


class PatientAccessTests(TestCase):
    def test_professional_only_sees_assigned_patients(self):
        professional = Professional.objects.create(full_name="Dra. Teste", specialty=Professional.Specialty.PILATES)
        assigned = Patient.objects.create(full_name="Paciente Vinculado")
        other = Patient.objects.create(full_name="Paciente Outro")
        ProfessionalPatientAssignment.objects.create(patient=assigned, professional=professional)
        user = get_user_model().objects.create_user(username="prof", password="Senha@123")
        UserProfile.objects.update_or_create(
            user=user,
            defaults={"role": UserProfile.Role.PROFESSIONAL, "professional": professional},
        )
        self.client.force_login(user)

        response = self.client.get(reverse("patients:list"))

        self.assertContains(response, assigned.full_name)
        self.assertNotContains(response, other.full_name)

    def test_professional_sees_patient_from_automatic_appointment_link(self):
        professional = Professional.objects.create(full_name="Dra. Agenda Auto", specialty=Professional.Specialty.PILATES)
        patient = Patient.objects.create(full_name="Paciente Atendimento Auto")
        other = Patient.objects.create(full_name="Paciente Sem Atendimento")
        Appointment.objects.create(
            patient=patient,
            professional=professional,
            starts_at=timezone.now() + timedelta(days=1),
            ends_at=timezone.now() + timedelta(days=1, hours=1),
        )
        user = get_user_model().objects.create_user(username="prof-auto", password="Senha@123")
        UserProfile.objects.update_or_create(
            user=user,
            defaults={"role": UserProfile.Role.PROFESSIONAL, "professional": professional},
        )
        self.client.force_login(user)

        response = self.client.get(reverse("patients:list"))

        self.assertContains(response, patient.full_name)
        self.assertNotContains(response, other.full_name)

    def test_professional_record_only_shows_own_notes_by_patient(self):
        patient = Patient.objects.create(full_name="Paciente Prontuario")
        professional = Professional.objects.create(full_name="Dra. Uma", specialty=Professional.Specialty.PILATES)
        other_professional = Professional.objects.create(
            full_name="Dra. Outra",
            specialty=Professional.Specialty.PHYSIOTHERAPY,
        )
        ProfessionalPatientAssignment.objects.create(patient=patient, professional=professional)
        ProfessionalPatientAssignment.objects.create(patient=patient, professional=other_professional)
        own_note = ProfessionalNote.objects.create(
            patient=patient,
            professional=professional,
            title="Evolucao visivel",
            body="Conteudo do profissional logado.",
        )
        ProfessionalNote.objects.create(
            patient=patient,
            professional=other_professional,
            title="Evolucao sigilosa",
            body="Conteudo de outro profissional.",
        )
        user = get_user_model().objects.create_user(username="prof-prontuario", password="Senha@123")
        UserProfile.objects.update_or_create(
            user=user,
            defaults={"role": UserProfile.Role.PROFESSIONAL, "professional": professional},
        )
        self.client.force_login(user)

        response = self.client.get(reverse("patients:patient_notes", args=[patient.pk]))

        self.assertContains(response, own_note.title)
        self.assertNotContains(response, "Evolucao sigilosa")

    def test_professional_cannot_edit_note_from_another_professional(self):
        patient = Patient.objects.create(full_name="Paciente Edicao")
        professional = Professional.objects.create(full_name="Dra. Dona", specialty=Professional.Specialty.PILATES)
        other_professional = Professional.objects.create(
            full_name="Dra. Autora",
            specialty=Professional.Specialty.PHYSIOTHERAPY,
        )
        ProfessionalPatientAssignment.objects.create(patient=patient, professional=professional)
        note = ProfessionalNote.objects.create(
            patient=patient,
            professional=other_professional,
            title="Nao editar",
            body="Restrito ao autor.",
        )
        user = get_user_model().objects.create_user(username="prof-sem-acesso", password="Senha@123")
        UserProfile.objects.update_or_create(
            user=user,
            defaults={"role": UserProfile.Role.PROFESSIONAL, "professional": professional},
        )
        self.client.force_login(user)

        response = self.client.get(reverse("patients:note_update", args=[patient.pk, note.pk]))

        self.assertEqual(response.status_code, 404)

    def test_professional_can_export_own_patient_record(self):
        patient = Patient.objects.create(full_name="Paciente Exportacao", phone="11999998888")
        professional = Professional.objects.create(
            full_name="Dra. Exportadora",
            specialty=Professional.Specialty.PHYSIOTHERAPY,
            registration_number="CREFITO-999",
        )
        ProfessionalPatientAssignment.objects.create(patient=patient, professional=professional)
        ProfessionalNote.objects.create(
            patient=patient,
            professional=professional,
            title="Evolucao exportavel",
            body="Paciente evoluindo bem.",
        )
        user = get_user_model().objects.create_user(username="prof-exporta", password="Senha@123")
        UserProfile.objects.update_or_create(
            user=user,
            defaults={"role": UserProfile.Role.PROFESSIONAL, "professional": professional},
        )
        self.client.force_login(user)

        pdf_response = self.client.get(reverse("patients:note_export", args=[patient.pk, "pdf"]))
        xlsx_response = self.client.get(reverse("patients:note_export", args=[patient.pk, "xlsx"]))

        self.assertEqual(pdf_response.status_code, 200)
        self.assertEqual(pdf_response["Content-Type"], "application/pdf")
        self.assertEqual(xlsx_response.status_code, 200)
        self.assertEqual(
            xlsx_response["Content-Type"],
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    def test_professional_can_create_structured_record(self):
        patient = Patient.objects.create(full_name="Paciente Estruturado")
        professional = Professional.objects.create(full_name="Dra. Estrutura", specialty=Professional.Specialty.PILATES)
        ProfessionalPatientAssignment.objects.create(patient=patient, professional=professional)
        user = get_user_model().objects.create_user(username="prof-estrutura", password="Senha@123")
        UserProfile.objects.update_or_create(
            user=user,
            defaults={"role": UserProfile.Role.PROFESSIONAL, "professional": professional},
        )
        self.client.force_login(user)

        response = self.client.post(
            reverse("patients:note_create", args=[patient.pk]),
            {
                "patient": patient.pk,
                "professional": professional.pk,
                "title": "Evolucao guiada",
                "record_type": ProfessionalNote.RecordType.EVOLUTION,
                "session_focus": ProfessionalNote.SessionFocus.PILATES,
                "objective": "Fortalecimento de core.",
                "exercise_groups": ["solo_livre", "reformer_membros_inferiores"],
                "pain_level": "2",
                "clinical_status": ProfessionalNote.ClinicalStatus.IMPROVED,
                "conduct": ProfessionalNote.Conduct.PROGRESS,
                "body": "Paciente respondeu bem.",
            },
        )

        self.assertEqual(response.status_code, 302)
        note = ProfessionalNote.objects.get(title="Evolucao guiada")
        self.assertEqual(note.exercise_groups, ["solo_livre", "reformer_membros_inferiores"])
        self.assertEqual(note.pain_level, 2)

    def test_professional_record_type_menu_pages_render_expected_fields(self):
        patient = Patient.objects.create(full_name="Paciente Formularios")
        professional = Professional.objects.create(full_name="Dra. Formularios", specialty=Professional.Specialty.PILATES)
        ProfessionalPatientAssignment.objects.create(patient=patient, professional=professional)
        user = get_user_model().objects.create_user(username="prof-formularios", password="Senha@123")
        UserProfile.objects.update_or_create(
            user=user,
            defaults={"role": UserProfile.Role.PROFESSIONAL, "professional": professional},
        )
        self.client.force_login(user)

        expected_labels = {
            "clinical_evaluation": "Historia clinica / Anamnese",
            "diagnosis": "Fisioterapeutico",
            "physical_exam": "Apresentacao",
            "daily_evolution": "Selecoes do atendimento",
        }
        for record_type, label in expected_labels.items():
            response = self.client.get(reverse("patients:note_create", args=[patient.pk]), {"tipo": record_type})

            self.assertEqual(response.status_code, 200)
            self.assertContains(response, label)

    def test_professional_can_save_clinical_evaluation_structured_data(self):
        patient = Patient.objects.create(full_name="Paciente Avaliacao")
        professional = Professional.objects.create(full_name="Dra. Avaliacao", specialty=Professional.Specialty.PILATES)
        ProfessionalPatientAssignment.objects.create(patient=patient, professional=professional)
        user = get_user_model().objects.create_user(username="prof-avaliacao", password="Senha@123")
        UserProfile.objects.update_or_create(
            user=user,
            defaults={"role": UserProfile.Role.PROFESSIONAL, "professional": professional},
        )
        self.client.force_login(user)

        response = self.client.post(
            reverse("patients:note_create", args=[patient.pk]) + "?tipo=clinical_evaluation",
            {
                "patient": patient.pk,
                "professional": professional.pk,
                "title": "Avaliacao inicial guiada",
                "record_type": ProfessionalNote.RecordType.CLINICAL_EVALUATION,
                "clinical_history": "Dor lombar recorrente.",
                "life_habits": ["sedentarismo"],
                "current_disease_history": "Piora ao permanecer sentada.",
                "past_disease_history": "",
                "personal_history": "",
                "family_history": "",
                "previous_treatments": "Fisioterapia previa.",
                "body": "Observacao livre.",
            },
        )

        self.assertEqual(response.status_code, 302)
        note = ProfessionalNote.objects.get(title="Avaliacao inicial guiada")
        self.assertEqual(note.record_type, ProfessionalNote.RecordType.CLINICAL_EVALUATION)
        self.assertEqual(note.structured_data["life_habits"], ["sedentarismo"])
        self.assertEqual(note.structured_data["clinical_history"], "Dor lombar recorrente.")

    def test_patient_api_only_returns_own_patient(self):
        own = Patient.objects.create(full_name="Paciente API Proprio")
        other = Patient.objects.create(full_name="Paciente API Outro")
        user = get_user_model().objects.create_user(username="paciente-api", password="Senha@123")
        UserProfile.objects.update_or_create(user=user, defaults={"role": UserProfile.Role.PATIENT, "patient": own})
        self.client.force_login(user)

        list_response = self.client.get("/api/v1/patients/")
        detail_response = self.client.get(f"/api/v1/patients/{other.pk}/")

        self.assertContains(list_response, own.full_name)
        self.assertNotContains(list_response, other.full_name)
        self.assertEqual(detail_response.status_code, 404)

    def test_management_can_soft_delete_patient_from_web(self):
        patient = Patient.objects.create(full_name="Paciente Excluir")
        user = get_user_model().objects.create_user(username="gerente-paciente", password="Senha@123")
        UserProfile.objects.update_or_create(user=user, defaults={"role": UserProfile.Role.MANAGEMENT})
        self.client.force_login(user)

        response = self.client.post(reverse("patients:delete", args=[patient.pk]))

        patient.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertFalse(patient.active)

    def test_patient_delete_cancels_active_package(self):
        patient = Patient.objects.create(full_name="Paciente Pacote Excluir")
        plan = ServicePlan.objects.create(
            name="Plano Pacote",
            category=ServicePlan.Category.PILATES,
            monthly_price="300.00",
        )
        membership = Membership.objects.create(patient=patient, plan=plan, due_day=10)
        package = ServicePackage.objects.create(membership=membership, total_sessions=8)
        user = get_user_model().objects.create_user(username="gerente-pacote-paciente", password="Senha@123")
        UserProfile.objects.update_or_create(user=user, defaults={"role": UserProfile.Role.MANAGEMENT})
        self.client.force_login(user)

        response = self.client.post(reverse("patients:delete", args=[patient.pk]))

        package.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(package.status, ServicePackage.Status.CANCELED)

    def test_patient_list_shows_package_details_in_cascade(self):
        patient = Patient.objects.create(full_name="Paciente Detalhe Pacote")
        plan = ServicePlan.objects.create(
            name="Pilates Detalhado",
            category=ServicePlan.Category.PILATES,
            monthly_price="350.00",
        )
        membership = Membership.objects.create(patient=patient, plan=plan, due_day=10)
        ServicePackage.objects.create(membership=membership, total_sessions=8, used_sessions=2)
        user = get_user_model().objects.create_user(username="gerente-detalhe-paciente", password="Senha@123")
        UserProfile.objects.update_or_create(user=user, defaults={"role": UserProfile.Role.MANAGEMENT})
        self.client.force_login(user)

        response = self.client.get(reverse("patients:list"))

        self.assertContains(response, "Pacote atual")
        self.assertContains(response, "Pilates Detalhado")

    def test_patient_search_matches_partial_patient_context(self):
        matched = Patient.objects.create(full_name="Mariana Contexto")
        other = Patient.objects.create(full_name="Bianca Fora")
        user = get_user_model().objects.create_user(username="gerente-busca-paciente", password="Senha@123")
        UserProfile.objects.update_or_create(user=user, defaults={"role": UserProfile.Role.MANAGEMENT})
        self.client.force_login(user)

        response = self.client.get(reverse("patients:list"), {"q": "rian"})

        self.assertContains(response, matched.full_name)
        self.assertNotContains(response, other.full_name)

    def test_patient_search_matches_plan_and_professional_context(self):
        patient = Patient.objects.create(full_name="Paciente Contexto Relacionado")
        other = Patient.objects.create(full_name="Paciente Sem Contexto")
        professional = Professional.objects.create(
            full_name="Dra. Aurora Busca",
            specialty=Professional.Specialty.PILATES,
        )
        plan = ServicePlan.objects.create(
            name="Pilates Clinico Busca",
            category=ServicePlan.Category.PILATES,
            monthly_price="360.00",
        )
        Membership.objects.create(patient=patient, plan=plan, due_day=10)
        Appointment.objects.create(
            patient=patient,
            professional=professional,
            starts_at=timezone.now() + timedelta(days=1),
            ends_at=timezone.now() + timedelta(days=1, hours=1),
        )
        user = get_user_model().objects.create_user(username="gerente-busca-contexto", password="Senha@123")
        UserProfile.objects.update_or_create(user=user, defaults={"role": UserProfile.Role.MANAGEMENT})
        self.client.force_login(user)

        plan_response = self.client.get(reverse("patients:list"), {"q": "clinico busca"})
        professional_response = self.client.get(reverse("patients:list"), {"q": "aurora"})

        self.assertContains(plan_response, patient.full_name)
        self.assertNotContains(plan_response, other.full_name)
        self.assertContains(professional_response, patient.full_name)
        self.assertNotContains(professional_response, other.full_name)

    def test_patient_api_destroy_soft_deletes_patient(self):
        patient = Patient.objects.create(full_name="Paciente API Excluir")
        user = get_user_model().objects.create_user(username="admin-api-paciente", password="Senha@123")
        UserProfile.objects.update_or_create(user=user, defaults={"role": UserProfile.Role.ADMINISTRATION})
        self.client.force_login(user)

        response = self.client.delete(f"/api/v1/patients/{patient.pk}/")

        patient.refresh_from_db()
        self.assertEqual(response.status_code, 204)
        self.assertFalse(patient.active)
