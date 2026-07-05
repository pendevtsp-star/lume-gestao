from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import UserProfile
from billing.models import Charge, Membership, Payment, ServicePlan
from homecare.models import (
    HomecareCategory,
    HomecarePlan,
    HomecareSubscription,
    HomecareUploadJob,
    HomecareVideo,
    HomecareVideoComment,
    HomecareVideoLike,
    HomecareVideoProgress,
)
from homecare.services.bunny import process_upload_job
from patients.models import Patient
from scheduling.models import ServicePackage
from team.models import Professional


class HomecareTestMixin:
    def create_user(self, username, role, patient=None, professional=None):
        user = get_user_model().objects.create_user(username=username, password="Senha@123")
        UserProfile.objects.update_or_create(
            user=user,
            defaults={"role": role, "patient": patient, "professional": professional},
        )
        return user

    def setUp(self):
        self.category = HomecareCategory.objects.create(name="Pilates")
        self.plan = HomecarePlan.objects.create(
            name="Plano mensal",
            monthly_price=Decimal("49.90"),
            description="Acesso mensal",
        )
        self.patient = Patient.objects.create(full_name="Paciente Canal", email="paciente@example.com")
        self.professional = Professional.objects.create(
            full_name="Helena Fisio",
            specialty=Professional.Specialty.PILATES,
            active=True,
        )
        self.other_professional = Professional.objects.create(
            full_name="Laura Fisio",
            specialty=Professional.Specialty.PHYSIOTHERAPY,
            active=True,
        )


class HomecareModelTests(HomecareTestMixin, TestCase):
    def test_plan_requires_positive_price(self):
        plan = HomecarePlan(name="Gratis", monthly_price=Decimal("0.00"))

        with self.assertRaises(ValidationError):
            plan.full_clean()

    def test_active_subscription_without_end_date_grants_access(self):
        subscription = HomecareSubscription.objects.create(
            patient=self.patient,
            plan=self.plan,
            status=HomecareSubscription.Status.ACTIVE,
            source=HomecareSubscription.Source.MANUAL,
        )

        self.assertTrue(subscription.has_access)

    def test_expired_subscription_blocks_access(self):
        subscription = HomecareSubscription.objects.create(
            patient=self.patient,
            plan=self.plan,
            status=HomecareSubscription.Status.ACTIVE,
            current_period_end=timezone.now() - timedelta(days=1),
        )

        self.assertFalse(subscription.has_access)


@override_settings(HOMECARE_ENABLED=True, HOMECARE_INTERNAL_ENABLED=True)
class HomecarePermissionTests(HomecareTestMixin, TestCase):
    def test_professional_sees_only_own_videos(self):
        user = self.create_user("helena", UserProfile.Role.PROFESSIONAL, professional=self.professional)
        own_video = HomecareVideo.objects.create(
            title="Respiracao",
            category=self.category,
            author=self.professional,
            status=HomecareVideo.Status.READY,
        )
        other_video = HomecareVideo.objects.create(
            title="Mobilidade",
            category=self.category,
            author=self.other_professional,
            status=HomecareVideo.Status.READY,
        )
        self.client.force_login(user)

        response = self.client.get(reverse("homecare:videos"))

        self.assertContains(response, own_video.title)
        self.assertNotContains(response, other_video.title)

    def test_professional_cannot_edit_other_professional_video(self):
        user = self.create_user("helena-edita", UserProfile.Role.PROFESSIONAL, professional=self.professional)
        other_video = HomecareVideo.objects.create(
            title="Video de outra pessoa",
            category=self.category,
            author=self.other_professional,
            status=HomecareVideo.Status.READY,
        )
        self.client.force_login(user)

        response = self.client.get(reverse("homecare:video_update", args=[other_video.pk]))

        self.assertEqual(response.status_code, 404)

    def test_professional_cannot_manage_plans(self):
        user = self.create_user("prof-planos", UserProfile.Role.PROFESSIONAL, professional=self.professional)
        self.client.force_login(user)

        response = self.client.get(reverse("homecare:plans"))

        self.assertEqual(response.status_code, 302)

    @override_settings(HOMECARE_PUBLIC_ENABLED=True)
    def test_internal_menu_shows_homecare_entries(self):
        user = self.create_user("gestao-menu-homecare", UserProfile.Role.MANAGEMENT)
        self.client.force_login(user)

        response = self.client.get(reverse("homecare:videos"))

        self.assertContains(response, "Lume em casa")
        self.assertContains(response, "Gestao Lume em casa")

    def test_management_can_schedule_video_upload(self):
        user = self.create_user("gestao-agenda-video", UserProfile.Role.MANAGEMENT)
        scheduled_at = (timezone.now() + timedelta(days=3)).replace(second=0, microsecond=0)
        upload = SimpleUploadedFile("aula-programada.mp4", b"video-bytes", content_type="video/mp4")
        self.client.force_login(user)

        response = self.client.post(
            reverse("homecare:video_create"),
            data={
                "title": "Aula com lancamento programado",
                "description": "Conteudo preparado para entrar no ar depois.",
                "category": self.category.pk,
                "author": self.professional.pk,
                "specialty": Professional.Specialty.PILATES,
                "difficulty": HomecareVideo.Difficulty.BEGINNER,
                "duration_seconds": 900,
                "scheduled_publish_at": scheduled_at.strftime("%Y-%m-%dT%H:%M"),
                "upload_file": upload,
            },
        )

        self.assertRedirects(response, reverse("homecare:videos"))
        video = HomecareVideo.objects.get(title="Aula com lancamento programado")
        self.assertTrue(video.is_published)
        self.assertEqual(video.status, HomecareVideo.Status.QUEUED)
        self.assertEqual(
            timezone.localtime(video.scheduled_publish_at).strftime("%Y-%m-%dT%H:%M"),
            scheduled_at.strftime("%Y-%m-%dT%H:%M"),
        )
        self.assertTrue(HomecareUploadJob.objects.filter(video=video).exists())

    def test_dashboard_shows_homecare_storage_usage(self):
        user = self.create_user("gestao-storage-homecare", UserProfile.Role.MANAGEMENT)
        local_upload = SimpleUploadedFile("aula-storage.mp4", b"video-bytes", content_type="video/mp4")
        temp_upload = SimpleUploadedFile("aula-pendente.mp4", b"temporary-video", content_type="video/mp4")
        video = HomecareVideo.objects.create(
            title="Aula com armazenamento local",
            category=self.category,
            author=self.professional,
            status=HomecareVideo.Status.READY,
            local_video_file=local_upload,
            temporary_file=temp_upload,
        )
        self.client.force_login(user)

        response = self.client.get(reverse("homecare:dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Uso de armazenamento")
        self.assertContains(response, "Videos protegidos")
        self.assertEqual(response.context["storage_usage"]["local_video_count"], 1)
        self.assertEqual(response.context["storage_usage"]["temporary_count"], 1)
        self.assertEqual(response.context["storage_usage"]["local_video_bytes"], len(b"video-bytes"))
        default_storage.delete(video.local_video_file.name)
        default_storage.delete(video.temporary_file.name)


@override_settings(HOMECARE_ENABLED=True, HOMECARE_PUBLIC_ENABLED=True)
class HomecarePortalTests(HomecareTestMixin, TestCase):
    def create_ready_video(self, **overrides):
        defaults = {
            "title": "Aula liberada",
            "category": self.category,
            "author": self.professional,
            "status": HomecareVideo.Status.READY,
            "provider": HomecareVideo.Provider.BUNNY,
            "provider_video_id": "video-123",
            "provider_library_id": "lib-123",
            "is_published": True,
        }
        defaults.update(overrides)
        return HomecareVideo.objects.create(**defaults)

    def create_active_subscription(self):
        return HomecareSubscription.objects.create(
            patient=self.patient,
            plan=self.plan,
            status=HomecareSubscription.Status.ACTIVE,
            current_period_end=timezone.now() + timedelta(days=30),
        )

    def create_service_plan(self, **overrides):
        defaults = {
            "name": f"Plano clinica {ServicePlan.objects.count() + 1}",
            "category": ServicePlan.Category.PILATES,
            "plan_type": ServicePlan.PlanType.RECURRING,
            "delivery_mode": ServicePlan.DeliveryMode.IN_PERSON,
            "grants_homecare_access": False,
            "monthly_price": Decimal("300.00"),
            "duration_months": 1,
            "sessions_per_week": 2,
            "included_sessions": 8,
            "active": True,
        }
        defaults.update(overrides)
        return ServicePlan.objects.create(**defaults)

    def create_membership_for_patient(self, plan=None, patient=None, status=None):
        return Membership.objects.create(
            patient=patient or self.patient,
            plan=plan or self.create_service_plan(),
            status=status or Membership.Status.ACTIVE,
            due_day=10,
        )

    def create_service_package(self, membership, status=None, expires_on=None):
        return ServicePackage.objects.create(
            membership=membership,
            total_sessions=membership.plan.default_total_sessions,
            used_sessions=0,
            starts_on=timezone.localdate(),
            expires_on=expires_on if expires_on is not None else timezone.localdate() + timedelta(days=30),
            status=status or ServicePackage.Status.ACTIVE,
        )

    def create_plan_access(self, **plan_overrides):
        plan_defaults = {
            "delivery_mode": ServicePlan.DeliveryMode.HYBRID,
            "grants_homecare_access": True,
        }
        plan_defaults.update(plan_overrides)
        plan = self.create_service_plan(**plan_defaults)
        membership = self.create_membership_for_patient(plan=plan)
        self.create_service_package(membership)
        return membership

    def test_anonymous_user_is_redirected_to_login_before_library_access_check(self):
        response = self.client.get(reverse("homecare_public:library"))

        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response["Location"])

    def test_active_patient_without_subscription_or_enabled_plan_is_redirected_to_access_required(self):
        user = self.create_user("paciente-sem-plano-digital", UserProfile.Role.PATIENT, patient=self.patient)
        video = self.create_ready_video()
        self.client.force_login(user)

        response = self.client.get(reverse("homecare_public:library"))

        self.assertRedirects(response, reverse("homecare_public:access_required"))
        self.assertNotContains(self.client.get(reverse("homecare_public:access_required")), video.title)

    def test_patient_with_active_service_plan_homecare_access_can_access_library(self):
        user = self.create_user("paciente-plano-lume", UserProfile.Role.PATIENT, patient=self.patient)
        video = self.create_ready_video()
        self.create_plan_access()
        self.client.force_login(user)

        response = self.client.get(reverse("homecare_public:library"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, video.title)

    def test_patient_with_active_service_plan_without_homecare_access_is_blocked(self):
        user = self.create_user("paciente-plano-sem-lume", UserProfile.Role.PATIENT, patient=self.patient)
        plan = self.create_service_plan(grants_homecare_access=False)
        membership = self.create_membership_for_patient(plan=plan)
        self.create_service_package(membership)
        self.client.force_login(user)

        response = self.client.get(reverse("homecare_public:library"))

        self.assertRedirects(response, reverse("homecare_public:access_required"))

    def test_patient_with_canceled_membership_is_blocked_even_if_plan_grants_access(self):
        user = self.create_user("paciente-plano-cancelado", UserProfile.Role.PATIENT, patient=self.patient)
        plan = self.create_service_plan(grants_homecare_access=True, delivery_mode=ServicePlan.DeliveryMode.HYBRID)
        membership = self.create_membership_for_patient(plan=plan, status=Membership.Status.CANCELED)
        self.create_service_package(membership)
        self.client.force_login(user)

        response = self.client.get(reverse("homecare_public:library"))

        self.assertRedirects(response, reverse("homecare_public:access_required"))

    def test_patient_with_expired_package_is_blocked_even_if_plan_grants_access(self):
        user = self.create_user("paciente-pacote-vencido", UserProfile.Role.PATIENT, patient=self.patient)
        plan = self.create_service_plan(grants_homecare_access=True, delivery_mode=ServicePlan.DeliveryMode.HYBRID)
        membership = self.create_membership_for_patient(plan=plan)
        self.create_service_package(membership, expires_on=timezone.localdate() - timedelta(days=1))
        self.client.force_login(user)

        response = self.client.get(reverse("homecare_public:library"))

        self.assertRedirects(response, reverse("homecare_public:access_required"))

    def test_patient_with_inactive_plan_is_blocked_even_if_field_is_marked(self):
        user = self.create_user("paciente-plano-inativo", UserProfile.Role.PATIENT, patient=self.patient)
        plan = self.create_service_plan(
            grants_homecare_access=True,
            delivery_mode=ServicePlan.DeliveryMode.HYBRID,
            active=False,
        )
        membership = self.create_membership_for_patient(plan=plan)
        self.create_service_package(membership)
        self.client.force_login(user)

        response = self.client.get(reverse("homecare_public:library"))

        self.assertRedirects(response, reverse("homecare_public:access_required"))

    def test_patient_with_overdue_membership_payment_is_blocked_even_if_plan_grants_access(self):
        user = self.create_user("paciente-pagamento-vencido", UserProfile.Role.PATIENT, patient=self.patient)
        plan = self.create_service_plan(grants_homecare_access=True, delivery_mode=ServicePlan.DeliveryMode.HYBRID)
        membership = self.create_membership_for_patient(plan=plan)
        self.create_service_package(membership)
        Payment.objects.create(
            membership=membership,
            reference_month=timezone.localdate().replace(day=1),
            due_date=timezone.localdate() - timedelta(days=1),
            amount=membership.monthly_amount,
            status=Payment.Status.OVERDUE,
        )
        self.client.force_login(user)

        response = self.client.get(reverse("homecare_public:library"))

        self.assertRedirects(response, reverse("homecare_public:access_required"))

    def test_active_homecare_subscription_allows_patient_even_with_overdue_membership_payment(self):
        user = self.create_user("paciente-assinatura-vencido", UserProfile.Role.PATIENT, patient=self.patient)
        plan = self.create_service_plan(grants_homecare_access=True, delivery_mode=ServicePlan.DeliveryMode.HYBRID)
        membership = self.create_membership_for_patient(plan=plan)
        self.create_service_package(membership)
        Payment.objects.create(
            membership=membership,
            reference_month=timezone.localdate().replace(day=1),
            due_date=timezone.localdate() - timedelta(days=1),
            amount=membership.monthly_amount,
            status=Payment.Status.OVERDUE,
        )
        self.create_active_subscription()
        self.client.force_login(user)

        response = self.client.get(reverse("homecare_public:library"))

        self.assertEqual(response.status_code, 200)

    def test_user_without_patient_or_staff_role_does_not_receive_patient_access(self):
        user = self.create_user("usuario-sem-paciente", UserProfile.Role.PATIENT)
        self.client.force_login(user)

        response = self.client.get(reverse("homecare_public:library"))

        self.assertRedirects(response, reverse("homecare_public:access_required"))

    def test_changing_plan_homecare_access_updates_patient_permission(self):
        user = self.create_user("paciente-altera-plano", UserProfile.Role.PATIENT, patient=self.patient)
        plan = self.create_service_plan(grants_homecare_access=False)
        membership = self.create_membership_for_patient(plan=plan)
        self.create_service_package(membership)
        self.client.force_login(user)

        blocked_response = self.client.get(reverse("homecare_public:library"))
        plan.grants_homecare_access = True
        plan.delivery_mode = ServicePlan.DeliveryMode.HYBRID
        plan.save(update_fields=["grants_homecare_access", "delivery_mode", "updated_at"])
        allowed_response = self.client.get(reverse("homecare_public:library"))

        self.assertRedirects(blocked_response, reverse("homecare_public:access_required"))
        self.assertEqual(allowed_response.status_code, 200)

    def test_inactive_patient_without_subscription_is_redirected_to_access_required(self):
        self.patient.active = False
        self.patient.save(update_fields=["active", "updated_at"])
        user = self.create_user("paciente-inativo", UserProfile.Role.PATIENT, patient=self.patient)
        self.client.force_login(user)

        response = self.client.get(reverse("homecare_public:library"))

        self.assertRedirects(response, reverse("homecare_public:access_required"))

    def test_professional_can_access_library_without_subscription(self):
        user = self.create_user("prof-biblioteca", UserProfile.Role.PROFESSIONAL, professional=self.professional)
        video = self.create_ready_video()
        self.client.force_login(user)

        response = self.client.get(reverse("homecare_public:library"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, video.title)

    def test_patient_with_active_subscription_can_watch_video(self):
        user = self.create_user("paciente-com-acesso", UserProfile.Role.PATIENT, patient=self.patient)
        video = self.create_ready_video()
        self.create_active_subscription()
        self.client.force_login(user)

        response = self.client.get(reverse("homecare_public:video_detail", args=[video.slug]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, video.title)
        self.assertContains(response, "iframe.mediadelivery.net")

    def test_future_scheduled_video_is_hidden_from_patient(self):
        user = self.create_user("paciente-agendado-futuro", UserProfile.Role.PATIENT, patient=self.patient)
        video = self.create_ready_video(
            title="Aula programada futura",
            scheduled_publish_at=timezone.now() + timedelta(days=2),
        )
        self.create_active_subscription()
        self.client.force_login(user)

        library_response = self.client.get(reverse("homecare_public:library"))
        detail_response = self.client.get(reverse("homecare_public:video_detail", args=[video.slug]))

        self.assertNotContains(library_response, video.title)
        self.assertEqual(detail_response.status_code, 404)

    def test_past_scheduled_video_is_available_to_patient(self):
        user = self.create_user("paciente-agendado-passado", UserProfile.Role.PATIENT, patient=self.patient)
        video = self.create_ready_video(
            title="Aula programada liberada",
            scheduled_publish_at=timezone.now() - timedelta(minutes=5),
        )
        self.create_active_subscription()
        self.client.force_login(user)

        response = self.client.get(reverse("homecare_public:library"))

        self.assertContains(response, video.title)

    def test_library_filters_by_query_difficulty_and_duration(self):
        user = self.create_user("paciente-filtros", UserProfile.Role.PATIENT, patient=self.patient)
        keep_video = self.create_ready_video(
            title="Mobilidade cervical",
            difficulty=HomecareVideo.Difficulty.BEGINNER,
            duration_seconds=600,
        )
        other_video = self.create_ready_video(
            title="Fortalecimento avancado",
            difficulty=HomecareVideo.Difficulty.ADVANCED,
            duration_seconds=1800,
        )
        self.create_active_subscription()
        self.client.force_login(user)

        response = self.client.get(
            reverse("homecare_public:library"),
            {"q": "Mobilidade", "nivel": HomecareVideo.Difficulty.BEGINNER, "duracao": "short"},
        )

        self.assertContains(response, keep_video.title)
        self.assertNotContains(response, other_video.title)

    def test_library_shows_continue_watching_progress(self):
        user = self.create_user("paciente-progresso", UserProfile.Role.PATIENT, patient=self.patient)
        video = self.create_ready_video(title="Rotina de continuidade", duration_seconds=600)
        HomecareVideoProgress.objects.create(patient=self.patient, video=video, watched_seconds=120)
        self.create_active_subscription()
        self.client.force_login(user)

        response = self.client.get(reverse("homecare_public:library"))

        self.assertContains(response, "Continuar assistindo")
        self.assertContains(response, video.title)

    def test_dry_run_video_uses_preview_placeholder(self):
        user = self.create_user("paciente-preview", UserProfile.Role.PATIENT, patient=self.patient)
        video = self.create_ready_video(provider_video_id="dry-run-123")
        self.create_active_subscription()
        self.client.force_login(user)

        response = self.client.get(reverse("homecare_public:video_detail", args=[video.slug]))

        self.assertContains(response, "Preview seguro")
        self.assertNotContains(response, "<iframe", html=False)

    @override_settings(HOMECARE_LOCAL_VIDEO_ACCEL_REDIRECT=False)
    def test_local_video_uses_protected_player_and_stream_route(self):
        user = self.create_user("paciente-video-local", UserProfile.Role.PATIENT, patient=self.patient)
        local_file = SimpleUploadedFile("aula-local.mp4", b"local-video", content_type="video/mp4")
        video = self.create_ready_video(
            title="Aula local protegida",
            provider=HomecareVideo.Provider.LOCAL,
            provider_video_id="local-123",
            provider_library_id="",
            provider_embed_url="",
            local_video_file=local_file,
        )
        self.create_plan_access()
        self.client.force_login(user)

        detail_response = self.client.get(reverse("homecare_public:video_detail", args=[video.slug]))
        stream_response = self.client.get(reverse("homecare_public:video_stream", args=[video.slug]))

        self.assertContains(detail_response, "<video", html=False)
        self.assertContains(detail_response, reverse("homecare_public:video_stream", args=[video.slug]))
        self.assertEqual(stream_response.status_code, 200)
        self.assertEqual(stream_response["Content-Type"], "video/mp4")
        stream_response.close()
        default_storage.delete(video.local_video_file.name)

    @override_settings(HOMECARE_LOCAL_VIDEO_ACCEL_REDIRECT=True)
    def test_local_video_stream_uses_x_accel_redirect_in_production_mode(self):
        user = self.create_user("paciente-x-accel", UserProfile.Role.PATIENT, patient=self.patient)
        local_file = SimpleUploadedFile("aula-x-accel.mp4", b"local-video", content_type="video/mp4")
        video = self.create_ready_video(
            title="Aula com x accel",
            provider=HomecareVideo.Provider.LOCAL,
            provider_video_id="local-456",
            provider_library_id="",
            provider_embed_url="",
            local_video_file=local_file,
        )
        self.create_plan_access()
        self.client.force_login(user)

        response = self.client.get(reverse("homecare_public:video_stream", args=[video.slug]))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response["X-Accel-Redirect"].startswith("/protected-homecare-media/"))
        self.assertNotIn("homecare/private", response["X-Accel-Redirect"])
        self.assertEqual(response["Cache-Control"], "private, no-store")
        default_storage.delete(video.local_video_file.name)

    def test_patient_can_toggle_video_like(self):
        user = self.create_user("paciente-curte-aula", UserProfile.Role.PATIENT, patient=self.patient)
        video = self.create_ready_video()
        self.create_plan_access()
        self.client.force_login(user)
        url = reverse("homecare_public:toggle_like", args=[video.slug])

        first_response = self.client.post(url)
        second_response = self.client.post(url)

        self.assertRedirects(first_response, reverse("homecare_public:video_detail", args=[video.slug]))
        self.assertRedirects(second_response, reverse("homecare_public:video_detail", args=[video.slug]))
        self.assertFalse(HomecareVideoLike.objects.filter(video=video, user=user).exists())

    def test_patient_can_comment_and_reply_on_video(self):
        user = self.create_user("paciente-comenta-aula", UserProfile.Role.PATIENT, patient=self.patient)
        video = self.create_ready_video()
        self.create_plan_access()
        self.client.force_login(user)
        url = reverse("homecare_public:add_comment", args=[video.slug])

        comment_response = self.client.post(url, {"content": "Senti alivio no final."})
        comment = HomecareVideoComment.objects.get(video=video, author=user, parent__isnull=True)
        reply_response = self.client.post(url, {"content": "Vou repetir amanha.", "parent_id": comment.pk})

        self.assertEqual(comment_response.status_code, 302)
        self.assertEqual(reply_response.status_code, 302)
        self.assertTrue(
            HomecareVideoComment.objects.filter(
                video=video,
                author=user,
                parent=comment,
                content="Vou repetir amanha.",
            ).exists()
        )

    def test_reply_to_reply_is_rejected(self):
        user = self.create_user("paciente-resposta-profunda", UserProfile.Role.PATIENT, patient=self.patient)
        video = self.create_ready_video()
        parent = HomecareVideoComment.objects.create(video=video, author=user, content="Comentario principal")
        reply = HomecareVideoComment.objects.create(video=video, author=user, parent=parent, content="Resposta")
        self.create_plan_access()
        self.client.force_login(user)

        response = self.client.post(
            reverse("homecare_public:add_comment", args=[video.slug]),
            {"content": "Outra camada", "parent_id": reply.pk},
        )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(HomecareVideoComment.objects.filter(video=video, content="Outra camada").exists())

    def test_anonymous_user_cannot_like_or_comment(self):
        video = self.create_ready_video()

        like_response = self.client.post(reverse("homecare_public:toggle_like", args=[video.slug]))
        comment_response = self.client.post(
            reverse("homecare_public:add_comment", args=[video.slug]),
            {"content": "Sem login"},
        )

        self.assertEqual(like_response.status_code, 302)
        self.assertIn("/login/", like_response["Location"])
        self.assertEqual(comment_response.status_code, 302)
        self.assertIn("/login/", comment_response["Location"])
        self.assertFalse(HomecareVideoLike.objects.filter(video=video).exists())
        self.assertFalse(HomecareVideoComment.objects.filter(video=video).exists())


@override_settings(
    HOMECARE_ENABLED=True,
    HOMECARE_UPLOAD_WORKER_ENABLED=True,
    HOMECARE_VIDEO_PROVIDER="bunny",
    BUNNY_STREAM_DRY_RUN=True,
    BUNNY_STREAM_LIBRARY_ID="library-test",
)
class HomecareUploadTests(HomecareTestMixin, TestCase):
    def test_upload_job_bunny_dry_run_marks_video_ready_and_removes_temp_file(self):
        upload = SimpleUploadedFile("aula.mp4", b"video-bytes", content_type="video/mp4")
        video = HomecareVideo.objects.create(
            title="Upload teste",
            category=self.category,
            author=self.professional,
            temporary_file=upload,
            status=HomecareVideo.Status.QUEUED,
        )
        job = HomecareUploadJob.objects.create(video=video)

        processed = process_upload_job(job)

        self.assertTrue(processed)
        video.refresh_from_db()
        job.refresh_from_db()
        self.assertEqual(video.status, HomecareVideo.Status.READY)
        self.assertEqual(job.status, HomecareUploadJob.Status.DONE)
        self.assertEqual(video.provider, HomecareVideo.Provider.BUNNY)
        self.assertTrue(video.provider_video_id.startswith("dry-run-"))
        self.assertFalse(video.temporary_file)

    @override_settings(HOMECARE_VIDEO_PROVIDER="local")
    def test_upload_job_local_moves_video_to_private_storage(self):
        upload = SimpleUploadedFile("aula-local.mp4", b"video-bytes", content_type="video/mp4")
        video = HomecareVideo.objects.create(
            title="Upload local teste",
            category=self.category,
            author=self.professional,
            temporary_file=upload,
            status=HomecareVideo.Status.QUEUED,
        )
        job = HomecareUploadJob.objects.create(video=video)

        processed = process_upload_job(job)

        self.assertTrue(processed)
        video.refresh_from_db()
        job.refresh_from_db()
        self.assertEqual(video.status, HomecareVideo.Status.READY)
        self.assertEqual(job.status, HomecareUploadJob.Status.DONE)
        self.assertEqual(video.provider, HomecareVideo.Provider.LOCAL)
        self.assertTrue(video.provider_video_id.startswith("local-"))
        self.assertTrue(video.local_video_file.name.startswith("homecare/private/videos/"))
        self.assertNotIn("homecare/private/videos/homecare/private", video.local_video_file.name)
        self.assertTrue(default_storage.exists(video.local_video_file.name))
        self.assertFalse(video.temporary_file)
        default_storage.delete(video.local_video_file.name)


@override_settings(HOMECARE_ENABLED=True, HOMECARE_WEBHOOK_ENABLED=True, ASAAS_WEBHOOK_TOKEN="token-seguro")
class HomecareAsaasWebhookTests(HomecareTestMixin, TestCase):
    def test_asaas_webhook_activates_subscription_and_is_idempotent(self):
        subscription = HomecareSubscription.objects.create(
            patient=self.patient,
            plan=self.plan,
            status=HomecareSubscription.Status.PENDING,
            provider=HomecareSubscription.Provider.ASAAS,
            provider_subscription_id="sub_123",
        )
        payload = {
            "id": "evt_123",
            "event": "PAYMENT_CONFIRMED",
            "payment": {
                "id": "pay_123",
                "subscription": "sub_123",
                "externalReference": subscription.external_reference,
                "value": 49.90,
                "confirmedDate": "2026-06-29",
            },
        }

        first_response = self.client.post(
            reverse("homecare:asaas_webhook"),
            data=payload,
            content_type="application/json",
            HTTP_ASAAS_ACCESS_TOKEN="token-seguro",
        )
        second_response = self.client.post(
            reverse("homecare:asaas_webhook"),
            data=payload,
            content_type="application/json",
            HTTP_ASAAS_ACCESS_TOKEN="token-seguro",
        )

        self.assertEqual(first_response.status_code, 200)
        self.assertTrue(first_response.json()["created"])
        self.assertEqual(second_response.status_code, 200)
        self.assertFalse(second_response.json()["created"])
        subscription.refresh_from_db()
        self.assertEqual(subscription.status, HomecareSubscription.Status.ACTIVE)
        charge = Charge.objects.get()
        self.assertEqual(charge.patient, self.patient)
        self.assertEqual(charge.status, Charge.Status.RECEIVED)
        self.assertEqual(charge.amount, Decimal("49.90"))
        self.assertIn("Fisioterapia em Casa", charge.description)

    def test_asaas_webhook_does_not_duplicate_finance_charge_for_same_payment(self):
        subscription = HomecareSubscription.objects.create(
            patient=self.patient,
            plan=self.plan,
            status=HomecareSubscription.Status.PENDING,
            provider=HomecareSubscription.Provider.ASAAS,
            provider_subscription_id="sub_456",
        )
        confirmed_payload = {
            "id": "evt_confirmed",
            "event": "PAYMENT_CONFIRMED",
            "payment": {
                "id": "pay_456",
                "subscription": "sub_456",
                "externalReference": subscription.external_reference,
                "value": 49.90,
                "confirmedDate": "2026-06-29",
            },
        }
        received_payload = {
            "id": "evt_received",
            "event": "PAYMENT_RECEIVED",
            "payment": {
                "id": "pay_456",
                "subscription": "sub_456",
                "externalReference": subscription.external_reference,
                "value": 49.90,
                "paymentDate": "2026-06-29",
            },
        }

        self.client.post(
            reverse("homecare:asaas_webhook"),
            data=confirmed_payload,
            content_type="application/json",
            HTTP_ASAAS_ACCESS_TOKEN="token-seguro",
        )
        self.client.post(
            reverse("homecare:asaas_webhook"),
            data=received_payload,
            content_type="application/json",
            HTTP_ASAAS_ACCESS_TOKEN="token-seguro",
        )

        self.assertEqual(Charge.objects.count(), 1)

    def test_asaas_webhook_rejects_invalid_token(self):
        response = self.client.post(
            reverse("homecare:asaas_webhook"),
            data={"id": "evt_bad", "event": "PAYMENT_CONFIRMED"},
            content_type="application/json",
            HTTP_ASAAS_ACCESS_TOKEN="errado",
        )

        self.assertEqual(response.status_code, 400)


class HomecareFeatureFlagTests(HomecareTestMixin, TestCase):
    @override_settings(HOMECARE_ENABLED=True, HOMECARE_INTERNAL_ENABLED=False)
    def test_internal_panel_disabled_returns_404(self):
        user = self.create_user("gestao-homecare-off", UserProfile.Role.MANAGEMENT)
        self.client.force_login(user)

        response = self.client.get(reverse("homecare:videos"))

        self.assertEqual(response.status_code, 404)

    @override_settings(HOMECARE_ENABLED=True, HOMECARE_PUBLIC_ENABLED=False)
    def test_public_portal_disabled_returns_404(self):
        response = self.client.get(reverse("homecare_public:landing"))

        self.assertEqual(response.status_code, 404)

    @override_settings(
        HOMECARE_ENABLED=True,
        HOMECARE_PUBLIC_ENABLED=True,
        WEBSITE_HOSTS=["clinicafisiolume.com.br"],
        ALLOWED_HOSTS=["testserver", "clinicafisiolume.com.br"],
    )
    def test_public_portal_is_available_on_website_host(self):
        response = self.client.get(reverse("homecare_public:landing"), HTTP_HOST="clinicafisiolume.com.br")

        self.assertEqual(response.status_code, 200)

    @override_settings(HOMECARE_ENABLED=True, HOMECARE_PUBLIC_ENABLED=True, HOMECARE_CHECKOUT_ENABLED=False)
    def test_checkout_disabled_does_not_create_subscription(self):
        user = self.create_user("paciente-checkout-off", UserProfile.Role.PATIENT, patient=self.patient)
        self.client.force_login(user)

        response = self.client.post(reverse("homecare_public:subscribe", args=[self.plan.slug]))

        self.assertRedirects(response, reverse("homecare_public:access_required"))
        self.assertFalse(HomecareSubscription.objects.filter(patient=self.patient).exists())
