from django.contrib.auth import get_user_model
from django.test import TestCase

from accounts.models import UserProfile


class UserProfileTests(TestCase):
    def test_profile_is_created_for_new_user(self):
        user = get_user_model().objects.create_user(username="teste", password="Senha@123")

        self.assertTrue(UserProfile.objects.filter(user=user).exists())
        self.assertEqual(user.profile.role, UserProfile.Role.ADMINISTRATION)
