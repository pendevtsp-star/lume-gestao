from datetime import datetime, time, timedelta

from django.conf import settings
from django.db.models import Count, Sum
from django.contrib.auth import authenticate
from django.shortcuts import get_object_or_404
from django.utils.dateparse import parse_date
from django.utils import timezone
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import UserProfile
from accounts.permissions import get_profile
from billing.models import Membership, Payment
from lume_connect.models import ConnectComment, ConnectLike, ConnectNotification, ConnectPost
from patients.models import Patient, ProfessionalNote, ProfessionalPatientAssignment
from patients.views import patients_for_user
from scheduling.models import Appointment, ServicePackage, ServiceUsage
from team.models import Employee, Professional


def profile_payload(profile):
    return {
        "username": profile.user.username,
        "display_name": profile.display_name,
        "role": profile.role,
        "role_label": profile.get_role_display(),
        "patient_id": profile.patient_id,
        "professional_id": profile.professional_id,
        "avatar_url": profile.avatar_url,
        "initials": profile.initials,
        "whatsapp_number": profile.whatsapp_number,
        "whatsapp_notifications_enabled": profile.whatsapp_notifications_enabled,
    }


def features_for(profile, is_superuser):
    features = ["dashboard", "agenda", "minha_conta"]
    if getattr(settings, "LUME_CONNECT_ENABLED", True):
        features.append("lume_connect")
    if profile.is_patient:
        features.extend(["meu_plano", "meus_creditos", "meus_pagamentos"])
    if profile.is_professional:
        features.extend(["pacientes", "prontuario", "disponibilidade"])
    if is_superuser or profile.role in {UserProfile.Role.ADMINISTRATION, UserProfile.Role.MANAGEMENT}:
        features.extend(["financeiro", "relatorios", "pacientes", "equipe"])
    if is_superuser or profile.role == UserProfile.Role.MANAGEMENT:
        features.extend(["usuarios", "auditoria", "configuracoes"])
    return features


def absolute_media_url(request, value):
    if not value:
        return ""
    try:
        url = value.url
    except ValueError:
        return ""
    if url.startswith(("http://", "https://")):
        return url
    return request.build_absolute_uri(url)


def connect_comment_payload(comment):
    return {
        "id": comment.id,
        "content": comment.content,
        "author_name": comment.author_name,
        "author_initials": comment.author_initials,
        "created_at": comment.created_at.isoformat(),
    }


def connect_post_payload(request, post, liked_post_ids=None):
    liked_post_ids = liked_post_ids or set()
    recent_comments = list(getattr(post, "recent_mobile_comments", []))
    return {
        "id": post.id,
        "content": post.content,
        "image_url": absolute_media_url(request, post.image),
        "author_name": post.author_name,
        "author_initials": post.author_initials,
        "created_at": post.created_at.isoformat(),
        "is_pinned": post.is_pinned,
        "is_announcement": post.is_announcement,
        "liked_by_me": post.id in liked_post_ids,
        "likes_count": getattr(post, "likes_count", 0),
        "comments_count": getattr(post, "comments_count", 0),
        "recent_comments": [connect_comment_payload(comment) for comment in recent_comments],
    }


def _local_datetime(value, fallback):
    parsed = parse_date(value or "")
    date_value = parsed or fallback
    return timezone.make_aware(datetime.combine(date_value, time.min))


def _date_range_from_request(request):
    today = timezone.localdate()
    start_at = _local_datetime(request.query_params.get("from"), today)
    end_date = parse_date(request.query_params.get("to") or "") or (today + timedelta(days=30))
    end_at = timezone.make_aware(datetime.combine(end_date + timedelta(days=1), time.min))
    return start_at, end_at


def appointments_for_user(user, profile):
    queryset = Appointment.objects.select_related("patient", "professional")
    if user.is_superuser:
        return queryset
    if not profile:
        return queryset.none()
    if profile.role in {UserProfile.Role.ADMINISTRATION, UserProfile.Role.MANAGEMENT}:
        return queryset
    if profile.is_patient and profile.patient_id:
        return queryset.filter(patient=profile.patient)
    if profile.is_professional and profile.professional_id:
        return queryset.filter(professional=profile.professional)
    return queryset.none()


def appointment_payload(appointment):
    return {
        "id": appointment.id,
        "starts_at": appointment.starts_at.isoformat(),
        "ends_at": appointment.ends_at.isoformat(),
        "status": appointment.status,
        "status_label": appointment.get_status_display(),
        "booking_source": appointment.booking_source,
        "patient": {
            "id": appointment.patient_id,
            "name": appointment.patient.full_name,
        },
        "professional": {
            "id": appointment.professional_id,
            "name": appointment.professional.full_name,
        },
        "service_units": appointment.service_units,
        "displayed_credit_units": appointment.displayed_credit_units,
        "is_group_session": appointment.is_group_session,
        "needs_confirmation": appointment.needs_confirmation,
    }


def payment_payload(payment):
    return {
        "id": payment.id,
        "plan": payment.membership.plan.name,
        "due_date": payment.due_date.isoformat(),
        "reference_month": payment.reference_month.isoformat(),
        "amount": str(payment.amount),
        "status": payment.status,
        "status_label": payment.get_status_display(),
        "method": payment.method,
        "paid_at": payment.paid_at.isoformat() if payment.paid_at else None,
    }


def patient_card_payload(patient):
    return {
        "id": patient.id,
        "full_name": patient.full_name,
        "photo_url": patient.photo.url if patient.photo else "",
        "active": patient.active,
    }


class MobileBootstrapView(APIView):
    def get(self, request):
        profile = get_profile(request.user)
        if not profile:
            return Response({"profile": None, "dashboard": {}, "features": []})

        payload = {
            "profile": profile_payload(profile),
            "features": features_for(profile, request.user.is_superuser),
            "dashboard": self.dashboard_payload(profile, request.user.is_superuser),
        }
        return Response(payload)

    def profile_payload(self, profile):
        return {
            "username": profile.user.username,
            "display_name": profile.display_name,
            "role": profile.role,
            "role_label": profile.get_role_display(),
            "avatar_url": profile.avatar_url,
            "initials": profile.initials,
            "whatsapp_number": profile.whatsapp_number,
            "whatsapp_notifications_enabled": profile.whatsapp_notifications_enabled,
        }

    def features_for(self, profile, is_superuser):
        features = ["dashboard", "agenda", "minha_conta"]
        if getattr(settings, "LUME_CONNECT_ENABLED", True):
            features.append("lume_connect")
        if profile.is_patient:
            features.extend(["meu_plano", "meus_creditos"])
        if profile.is_professional:
            features.extend(["pacientes", "prontuario", "disponibilidade"])
        if is_superuser or profile.role in {
            UserProfile.Role.ADMINISTRATION,
            UserProfile.Role.MANAGEMENT,
            UserProfile.Role.VIEWER,
        }:
            features.extend(["financeiro", "relatorios", "pacientes", "equipe"])
        if is_superuser or profile.role in {UserProfile.Role.MANAGEMENT, UserProfile.Role.VIEWER}:
            features.extend(["usuarios", "auditoria", "configuracoes"])
        return features

    def dashboard_payload(self, profile, is_superuser):
        if profile.is_patient and profile.patient_id:
            return self.patient_dashboard(profile)
        if profile.is_professional and profile.professional_id:
            return self.professional_dashboard(profile)
        if is_superuser or profile.role in {
            UserProfile.Role.ADMINISTRATION,
            UserProfile.Role.MANAGEMENT,
            UserProfile.Role.VIEWER,
        }:
            return self.backoffice_dashboard()
        return {}

    def patient_dashboard(self, profile):
        today = timezone.localdate()
        week_start = today - timedelta(days=today.weekday())
        week_end = week_start + timedelta(days=6)
        memberships = Membership.objects.select_related("plan").filter(
            patient=profile.patient,
            status=Membership.Status.ACTIVE,
        )
        packages = ServicePackage.objects.select_related("membership__plan").filter(
            membership__patient=profile.patient,
            status=ServicePackage.Status.ACTIVE,
        )
        usages = ServiceUsage.objects.select_related("appointment__professional").filter(
            appointment__patient=profile.patient,
        )
        next_payment = (
            Payment.objects.select_related("membership__plan")
            .filter(
                membership__patient=profile.patient,
                status__in=[Payment.Status.PENDING, Payment.Status.OVERDUE],
            )
            .order_by("due_date")
            .first()
        )

        weekly_allowed = sum(membership.plan.sessions_per_week for membership in memberships)
        weekly_used = (
            usages.filter(registered_at__date__gte=week_start, registered_at__date__lte=week_end).aggregate(
                total=Sum("units")
            )["total"]
            or 0
        )
        package_total = sum(package.total_sessions for package in packages)
        package_used = sum(package.used_sessions for package in packages)

        return {
            "memberships": [
                {
                    "plan": membership.plan.name,
                    "sessions_per_week": membership.plan.sessions_per_week,
                    "status": membership.status,
                }
                for membership in memberships
            ],
            "next_payment": self.payment_payload(next_payment),
            "weekly_credits": {
                "allowed": weekly_allowed,
                "used": weekly_used,
                "remaining": max(weekly_allowed - weekly_used, 0),
            },
            "package_credits": {
                "total": package_total,
                "used": package_used,
                "remaining": max(package_total - package_used, 0),
            },
            "recent_usages": [
                {
                    "date": usage.registered_at.isoformat(),
                    "professional": usage.appointment.professional.full_name,
                    "units": usage.units,
                }
                for usage in usages.order_by("-registered_at")[:8]
            ],
        }

    def payment_payload(self, payment):
        if not payment:
            return None
        return payment_payload(payment)

    def professional_dashboard(self, profile):
        today = timezone.localdate()
        assigned_patients = ProfessionalPatientAssignment.objects.filter(
            professional=profile.professional,
            active=True,
        )
        appointments = Appointment.objects.filter(
            professional=profile.professional,
            starts_at__date__gte=today,
        ).exclude(status__in=[Appointment.Status.CANCELED, Appointment.Status.RESCHEDULED])
        return {
            "assigned_patients": assigned_patients.count(),
            "upcoming_appointments": appointments.count(),
            "next_appointments": [
                {
                    "patient": appointment.patient.full_name,
                    "starts_at": appointment.starts_at.isoformat(),
                    "status": appointment.status,
                }
                for appointment in appointments.select_related("patient").order_by("starts_at")[:8]
            ],
        }

    def backoffice_dashboard(self):
        today = timezone.localdate()
        return {
            "active_patients": Patient.objects.filter(active=True).count(),
            "active_professionals": Professional.objects.filter(active=True).count(),
            "employees": Employee.objects.filter(active=True).count(),
            "upcoming_appointments": Appointment.objects.filter(starts_at__date__gte=today).exclude(
                status__in=[Appointment.Status.CANCELED, Appointment.Status.RESCHEDULED]
            ).count(),
            "pending_payments": Payment.objects.filter(
                status__in=[Payment.Status.PENDING, Payment.Status.OVERDUE]
            ).count(),
        }


class MobileLoginView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        username = (request.data.get("username") or "").strip()
        password = request.data.get("password") or ""
        user = authenticate(request, username=username, password=password)
        if not user:
            return Response({"detail": "Credenciais invalidas."}, status=status.HTTP_400_BAD_REQUEST)
        if not user.is_active:
            return Response({"detail": "Usuario inativo."}, status=status.HTTP_403_FORBIDDEN)

        token, _created = Token.objects.get_or_create(user=user)
        profile = get_profile(user)
        return Response(
            {
                "token": token.key,
                "profile": profile_payload(profile),
                "features": features_for(profile, user.is_superuser),
            }
        )


class MobileLogoutView(APIView):
    def post(self, request):
        if isinstance(request.auth, Token):
            request.auth.delete()
        else:
            Token.objects.filter(user=request.user).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class MobileProfileView(APIView):
    def get(self, request):
        profile = get_profile(request.user)
        if not profile:
            return Response({"profile": None, "features": []})
        return Response(
            {
                "profile": profile_payload(profile),
                "features": features_for(profile, request.user.is_superuser),
            }
        )


class MobileAgendaView(APIView):
    def get(self, request):
        profile = get_profile(request.user)
        start_at, end_at = _date_range_from_request(request)
        appointments = (
            appointments_for_user(request.user, profile)
            .filter(starts_at__gte=start_at, starts_at__lt=end_at)
            .exclude(status__in=[Appointment.Status.CANCELED, Appointment.Status.RESCHEDULED])
            .order_by("starts_at")[:100]
        )
        return Response(
            {
                "from": start_at.date().isoformat(),
                "to": (end_at.date() - timedelta(days=1)).isoformat(),
                "appointments": [appointment_payload(appointment) for appointment in appointments],
            }
        )


class MobileCreditsView(APIView):
    def get(self, request):
        profile = get_profile(request.user)
        if not profile or not profile.is_patient or not profile.patient_id:
            return Response({"memberships": [], "weekly_credits": None, "package_credits": None, "packages": []})

        bootstrap = MobileBootstrapView()
        dashboard = bootstrap.patient_dashboard(profile)
        packages = ServicePackage.objects.select_related("membership__plan").filter(
            membership__patient=profile.patient,
            status=ServicePackage.Status.ACTIVE,
        )
        dashboard["packages"] = [
            {
                "id": package.id,
                "plan": package.membership.plan.name,
                "total_sessions": package.total_sessions,
                "used_sessions": package.used_sessions,
                "remaining_sessions": package.remaining_sessions,
                "starts_on": package.starts_on.isoformat(),
                "expires_on": package.expires_on.isoformat() if package.expires_on else None,
                "status": package.status,
                "status_label": package.get_status_display(),
            }
            for package in packages.order_by("-starts_on")
        ]
        return Response(dashboard)


class MobilePaymentsView(APIView):
    def get(self, request):
        profile = get_profile(request.user)
        if not profile or not profile.is_patient or not profile.patient_id:
            return Response({"payments": []})

        payments = (
            Payment.objects.select_related("membership__plan")
            .filter(membership__patient=profile.patient)
            .order_by("-due_date")[:50]
        )
        return Response({"payments": [payment_payload(payment) for payment in payments]})


class MobilePatientsView(APIView):
    def get(self, request):
        query = (request.query_params.get("q") or "").strip()
        patients = patients_for_user(request.user).filter(active=True)
        if query:
            patients = patients.filter(full_name__icontains=query)
        return Response({"patients": [patient_card_payload(patient) for patient in patients.order_by("full_name")[:100]]})


class MobileProfessionalNotesView(APIView):
    def get(self, request):
        profile = get_profile(request.user)
        if not profile or not profile.is_professional or not profile.professional_id:
            return Response({"notes": []})

        patient_id = request.query_params.get("patient")
        notes = ProfessionalNote.objects.select_related("patient", "professional").filter(professional=profile.professional)
        if patient_id:
            notes = notes.filter(patient_id=patient_id)
        return Response(
            {
                "notes": [
                    {
                        "id": note.id,
                        "patient": {"id": note.patient_id, "name": note.patient.full_name},
                        "title": note.title,
                        "created_at": note.created_at.isoformat(),
                        "updated_at": note.updated_at.isoformat(),
                    }
                    for note in notes.order_by("-created_at")[:50]
                ]
            }
        )


class MobileConnectFeedView(APIView):
    def get(self, request):
        posts = list(
            ConnectPost.objects.select_related("author", "author__profile")
            .filter(is_active=True)
            .annotate(likes_count=Count("likes"), comments_count=Count("comments"))
            .order_by("-is_pinned", "-created_at")[:30]
        )
        post_ids = [post.id for post in posts]
        comments_by_post = {post_id: [] for post_id in post_ids}
        if post_ids:
            for comment in (
                ConnectComment.objects.select_related("author", "author__profile")
                .filter(is_active=True, post_id__in=post_ids)
                .order_by("created_at")
            ):
                bucket = comments_by_post.get(comment.post_id)
                if bucket is not None and len(bucket) < 3:
                    bucket.append(comment)
            liked_post_ids = set(
                ConnectLike.objects.filter(post_id__in=post_ids, user=request.user).values_list("post_id", flat=True)
            )
        else:
            liked_post_ids = set()
        for post in posts:
            post.recent_mobile_comments = comments_by_post.get(post.id, [])

        unread = ConnectNotification.objects.filter(recipient=request.user, is_read=False).count()
        return Response(
            {
                "unread_notifications": unread,
                "posts": [connect_post_payload(request, post, liked_post_ids) for post in posts],
            }
        )

    def post(self, request):
        content = (request.data.get("content") or "").strip()
        if not content:
            return Response({"detail": "Informe um texto para publicar."}, status=status.HTTP_400_BAD_REQUEST)
        post = ConnectPost.objects.create(author=request.user, content=content)
        post.likes_count = 0
        post.comments_count = 0
        post.recent_mobile_comments = []
        return Response(connect_post_payload(request, post), status=status.HTTP_201_CREATED)


class MobileConnectLikeView(APIView):
    def post(self, request, pk):
        post = get_object_or_404(ConnectPost.objects.filter(is_active=True), pk=pk)
        like = ConnectLike.objects.filter(post=post, user=request.user).first()
        liked = False
        if like:
            like.delete()
        else:
            ConnectLike.objects.create(post=post, user=request.user)
            liked = True
            if post.author_id != request.user.id:
                ConnectNotification.objects.create(
                    recipient=post.author,
                    actor=request.user,
                    post=post,
                    notification_type=ConnectNotification.NotificationType.LIKE,
                )
        return Response({"liked": liked, "likes_count": post.likes.count()})


class MobileConnectCommentView(APIView):
    def post(self, request, pk):
        post = get_object_or_404(ConnectPost.objects.filter(is_active=True), pk=pk)
        content = (request.data.get("content") or "").strip()
        if not content:
            return Response({"detail": "Informe um comentario."}, status=status.HTTP_400_BAD_REQUEST)
        comment = ConnectComment.objects.create(post=post, author=request.user, content=content)
        if post.author_id != request.user.id:
            ConnectNotification.objects.create(
                recipient=post.author,
                actor=request.user,
                post=post,
                comment=comment,
                notification_type=ConnectNotification.NotificationType.COMMENT,
            )
        return Response(connect_comment_payload(comment), status=status.HTTP_201_CREATED)
