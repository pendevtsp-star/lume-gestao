from io import BytesIO

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from PIL import Image

from accounts.models import UserProfile
from lume_connect.models import ConnectComment, ConnectLike, ConnectPost, ConnectShareLog
from lume_connect.services.video_metadata import build_test_mp4


def tiny_png():
    image_file = BytesIO()
    Image.new("RGB", (1, 1), color=(255, 255, 255)).save(image_file, format="PNG")
    return image_file.getvalue()


def tiny_mp4(duration_seconds=30):
    return build_test_mp4(duration_seconds)


@override_settings(MEDIA_ROOT=".codex-tmp/test-media")
class LumeConnectTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(username="marina", password="Senha@123")
        self.other = user_model.objects.create_user(username="helena", password="Senha@123")
        self.admin = user_model.objects.create_user(username="admin-connect", password="Senha@123", is_staff=True)
        self.inactive = user_model.objects.create_user(username="bloqueado", password="Senha@123", is_active=False)
        UserProfile.objects.update_or_create(user=self.user, defaults={"role": UserProfile.Role.PATIENT})
        UserProfile.objects.update_or_create(user=self.other, defaults={"role": UserProfile.Role.PROFESSIONAL})
        UserProfile.objects.update_or_create(user=self.admin, defaults={"role": UserProfile.Role.MANAGEMENT})
        UserProfile.objects.update_or_create(user=self.inactive, defaults={"role": UserProfile.Role.PATIENT})

    def test_authenticated_user_can_open_feed(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("lume_connect:feed"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Lume Connect")

    def test_inactive_user_cannot_open_feed(self):
        self.client.force_login(self.inactive)
        response = self.client.get(reverse("lume_connect:feed"))
        self.assertIn(response.status_code, {302, 403})

    def test_user_creates_text_post(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse("lume_connect:create_post"), {"content": "Hoje foi um treino leve."})
        self.assertRedirects(response, reverse("lume_connect:feed"))
        self.assertTrue(ConnectPost.objects.filter(author=self.user, content__icontains="treino leve").exists())

    def test_user_creates_post_with_image(self):
        self.client.force_login(self.user)
        image = SimpleUploadedFile("foto.png", tiny_png(), content_type="image/png")
        response = self.client.post(reverse("lume_connect:create_post"), {"content": "Foto do studio", "image": image})
        self.assertRedirects(response, reverse("lume_connect:feed"))
        post = ConnectPost.objects.get(author=self.user)
        self.assertTrue(post.image.name.startswith("lume_connect/posts/"))

    def test_user_creates_valid_short_video_post(self):
        self.client.force_login(self.user)
        video = SimpleUploadedFile("alongamento.mp4", tiny_mp4(30), content_type="video/mp4")

        response = self.client.post(
            reverse("lume_connect:create_post"),
            {"content": "Sequencia curta", "video": video},
        )

        self.assertRedirects(response, reverse("lume_connect:feed"))
        post = ConnectPost.objects.get(author=self.user)
        self.assertTrue(post.video.name.startswith("lume_connect/videos/"))
        self.assertEqual(post.media_type, ConnectPost.MediaType.SHORT_VIDEO)
        self.assertTrue(post.is_short_video)
        self.assertEqual(float(post.video_duration_seconds), 30.0)
        self.assertGreater(post.video_size_bytes, 0)

    def test_upload_rejects_short_video_above_sixty_seconds(self):
        self.client.force_login(self.user)
        video = SimpleUploadedFile("longo.mp4", tiny_mp4(61), content_type="video/mp4")

        response = self.client.post(
            reverse("lume_connect:create_post"),
            {"content": "Video longo", "video": video},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Videos curtos devem ter no maximo")
        self.assertFalse(ConnectPost.objects.exists())

    def test_upload_rejects_invalid_video_format(self):
        self.client.force_login(self.user)
        video = SimpleUploadedFile("arquivo.exe", b"conteudo", content_type="application/x-msdownload")

        response = self.client.post(
            reverse("lume_connect:create_post"),
            {"content": "Arquivo invalido", "video": video},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Use um video MP4 ou MOV.")
        self.assertFalse(ConnectPost.objects.exists())

    def test_feed_renders_short_video_player(self):
        video = SimpleUploadedFile("feed.mp4", tiny_mp4(24), content_type="video/mp4")
        ConnectPost.objects.create(
            author=self.user,
            content="Video no feed",
            video=video,
            video_duration_seconds=24,
            video_size_bytes=len(tiny_mp4(24)),
            is_short_video=True,
        )
        self.client.force_login(self.user)

        response = self.client.get(reverse("lume_connect:feed"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "data-connect-short-video")
        self.assertContains(response, 'preload="metadata"')
        self.assertContains(response, "playsinline")
        self.assertContains(response, "muted")
        self.assertContains(response, "loop")

    def test_legacy_text_post_still_renders(self):
        ConnectPost.objects.create(author=self.user, content="Post antigo sem midia")
        self.client.force_login(self.user)

        response = self.client.get(reverse("lume_connect:feed"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Post antigo sem midia")

    def test_unauthenticated_user_cannot_create_post(self):
        response = self.client.post(reverse("lume_connect:create_post"), {"content": "Sem login"})

        self.assertEqual(response.status_code, 302)
        self.assertFalse(ConnectPost.objects.exists())

    def test_author_sees_share_button_only_on_own_image_post(self):
        image = SimpleUploadedFile("share.png", tiny_png(), content_type="image/png")
        own_post = ConnectPost.objects.create(author=self.user, content="Com foto", image=image)
        ConnectPost.objects.create(author=self.user, content="Sem foto")
        other_image = SimpleUploadedFile("other-share.png", tiny_png(), content_type="image/png")
        other_post = ConnectPost.objects.create(author=self.other, content="Foto de outro usuario", image=other_image)
        self.client.force_login(self.user)

        response = self.client.get(reverse("lume_connect:feed"))

        self.assertContains(response, reverse("lume_connect:share_post", args=[own_post.pk]))
        self.assertNotContains(response, reverse("lume_connect:share_post", args=[other_post.pk]))

    def test_non_author_cannot_open_share_page(self):
        image = SimpleUploadedFile("protected.png", tiny_png(), content_type="image/png")
        post = ConnectPost.objects.create(author=self.other, content="Imagem protegida", image=image)
        self.client.force_login(self.user)

        response = self.client.get(reverse("lume_connect:share_post", args=[post.pk]))

        self.assertEqual(response.status_code, 403)

    def test_post_without_image_cannot_open_share_page(self):
        post = ConnectPost.objects.create(author=self.user, content="Sem imagem")
        self.client.force_login(self.user)

        response = self.client.get(reverse("lume_connect:share_post", args=[post.pk]))

        self.assertEqual(response.status_code, 403)

    def test_inactive_user_cannot_open_share_page(self):
        image = SimpleUploadedFile("inactive.png", tiny_png(), content_type="image/png")
        post = ConnectPost.objects.create(author=self.inactive, content="Foto", image=image)
        self.client.force_login(self.inactive)

        response = self.client.get(reverse("lume_connect:share_post", args=[post.pk]))

        self.assertIn(response.status_code, {302, 403})

    def test_generate_caption_uses_local_fallback_and_requires_post(self):
        image = SimpleUploadedFile("caption.png", tiny_png(), content_type="image/png")
        post = ConnectPost.objects.create(author=self.user, content="Movimento com leveza", image=image)
        self.client.force_login(self.user)
        url = reverse("lume_connect:generate_caption", args=[post.pk])

        get_response = self.client.get(url)
        post_response = self.client.post(url, HTTP_ACCEPT="application/json")

        self.assertEqual(get_response.status_code, 405)
        self.assertEqual(post_response.status_code, 200)
        payload = post_response.json()
        self.assertIn("Studio Lume", payload["caption"])
        self.assertEqual(payload["source"], "local_fallback")

    def test_generate_caption_requires_csrf_when_checks_are_enforced(self):
        image = SimpleUploadedFile("csrf.png", tiny_png(), content_type="image/png")
        post = ConnectPost.objects.create(author=self.user, content="CSRF", image=image)
        strict_client = Client(enforce_csrf_checks=True)
        strict_client.force_login(self.user)

        response = strict_client.post(reverse("lume_connect:generate_caption", args=[post.pk]))

        self.assertEqual(response.status_code, 403)

    def test_download_image_only_works_for_author(self):
        image = SimpleUploadedFile("download.png", tiny_png(), content_type="image/png")
        post = ConnectPost.objects.create(author=self.user, content="Download", image=image)
        url = reverse("lume_connect:download_post_image", args=[post.pk])

        self.client.force_login(self.other)
        forbidden = self.client.post(url)
        self.client.force_login(self.user)
        ok = self.client.post(url, {"final_caption": "Legenda final"})

        self.assertEqual(forbidden.status_code, 403)
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(ConnectShareLog.objects.filter(post=post, target_platform=ConnectShareLog.TargetPlatform.DOWNLOAD).count(), 1)

    def test_log_share_saves_intent_without_external_publication(self):
        image = SimpleUploadedFile("log.png", tiny_png(), content_type="image/png")
        post = ConnectPost.objects.create(author=self.user, content="Log", image=image)
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("lume_connect:log_share", args=[post.pk]),
            {
                "target_platform": ConnectShareLog.TargetPlatform.COPY_CAPTION,
                "generated_caption": "Legenda gerada",
                "final_caption": "Legenda editada",
            },
            HTTP_ACCEPT="application/json",
        )

        self.assertEqual(response.status_code, 200)
        log = ConnectShareLog.objects.get(post=post)
        self.assertEqual(log.user, self.user)
        self.assertEqual(log.final_caption, "Legenda editada")

    def test_user_toggles_like(self):
        post = ConnectPost.objects.create(author=self.other, content="Novidade")
        self.client.force_login(self.user)
        url = reverse("lume_connect:toggle_like", args=[post.pk])
        response = self.client.post(url, HTTP_ACCEPT="application/json")
        self.assertEqual(response.json()["liked"], True)
        self.assertEqual(ConnectLike.objects.filter(post=post, user=self.user).count(), 1)
        response = self.client.post(url, HTTP_ACCEPT="application/json")
        self.assertEqual(response.json()["liked"], False)
        self.assertFalse(ConnectLike.objects.filter(post=post, user=self.user).exists())

    def test_user_comments(self):
        post = ConnectPost.objects.create(author=self.other, content="Comunicado")
        self.client.force_login(self.user)
        response = self.client.post(reverse("lume_connect:add_comment", args=[post.pk]), {"content": "Adorei!"})
        self.assertRedirects(response, reverse("lume_connect:feed"))
        self.assertTrue(ConnectComment.objects.filter(post=post, author=self.user, content="Adorei!").exists())

    def test_author_edits_and_deletes_own_post(self):
        post = ConnectPost.objects.create(author=self.user, content="Texto inicial")
        self.client.force_login(self.user)
        response = self.client.post(reverse("lume_connect:edit_post", args=[post.pk]), {"content": "Texto editado"})
        self.assertRedirects(response, reverse("lume_connect:feed"))
        post.refresh_from_db()
        self.assertEqual(post.content, "Texto editado")
        response = self.client.post(reverse("lume_connect:delete_post", args=[post.pk]))
        self.assertRedirects(response, reverse("lume_connect:feed"))
        post.refresh_from_db()
        self.assertFalse(post.is_active)

    def test_regular_user_cannot_edit_or_delete_other_post(self):
        post = ConnectPost.objects.create(author=self.other, content="De outro usuario")
        self.client.force_login(self.user)
        edit_response = self.client.post(reverse("lume_connect:edit_post", args=[post.pk]), {"content": "Tentativa"})
        delete_response = self.client.post(reverse("lume_connect:delete_post", args=[post.pk]))
        self.assertEqual(edit_response.status_code, 403)
        self.assertEqual(delete_response.status_code, 403)
        post.refresh_from_db()
        self.assertTrue(post.is_active)

    def test_admin_can_moderate_post_and_comment(self):
        post = ConnectPost.objects.create(author=self.user, content="Post")
        comment = ConnectComment.objects.create(post=post, author=self.user, content="Comentario")
        self.client.force_login(self.admin)
        post_response = self.client.post(reverse("lume_connect:delete_post", args=[post.pk]))
        comment_response = self.client.post(reverse("lume_connect:delete_comment", args=[comment.pk]))
        self.assertRedirects(post_response, reverse("lume_connect:feed"))
        self.assertRedirects(comment_response, reverse("lume_connect:feed"))
        post.refresh_from_db()
        comment.refresh_from_db()
        self.assertFalse(post.is_active)
        self.assertFalse(comment.is_active)

    def test_upload_rejects_invalid_image_extension(self):
        self.client.force_login(self.user)
        file = SimpleUploadedFile("arquivo.txt", b"texto", content_type="text/plain")
        response = self.client.post(reverse("lume_connect:create_post"), {"content": "Teste", "image": file})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(ConnectPost.objects.exists())
