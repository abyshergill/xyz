from django.test import TestCase
from django.urls import reverse

from .models import User


class RegistrationAndLoginTests(TestCase):
    def test_customer_registration_creates_profile(self):
        resp = self.client.post(reverse("accounts:register_customer"), {
            "username": "cust1", "email": "cust1@example.com", "mobile_number": "+15551230000",
            "address": "1 Main St", "province": "CA", "pincode": "90001", "country": "USA",
            "password1": "StrongPass123!", "password2": "StrongPass123!",
        })
        self.assertEqual(resp.status_code, 302)
        user = User.objects.get(username="cust1")
        self.assertEqual(user.role, User.Role.CUSTOMER)
        self.assertTrue(hasattr(user, "customer_profile"))

    def test_duplicate_email_rejected(self):
        User.objects.create_user(username="existing", email="dup@example.com", password="x")
        resp = self.client.post(reverse("accounts:register_customer"), {
            "username": "cust2", "email": "dup@example.com", "mobile_number": "+15551230000",
            "address": "1 Main St", "province": "CA", "pincode": "90001", "country": "USA",
            "password1": "StrongPass123!", "password2": "StrongPass123!",
        })
        self.assertEqual(resp.status_code, 200)  # re-renders form with error
        self.assertFalse(User.objects.filter(username="cust2").exists())

    def test_owner_area_blocked_for_customer(self):
        User.objects.create_user(username="cust3", email="c3@example.com", password="StrongPass123!", role=User.Role.CUSTOMER)
        self.client.login(username="cust3", password="StrongPass123!")
        resp = self.client.get("/owner/dashboard/")
        self.assertEqual(resp.status_code, 302)  # redirected away by RBAC middleware

    def test_csrf_required_on_login_post(self):
        csrf_client = self.client_class(enforce_csrf_checks=True)
        resp = csrf_client.post(reverse("accounts:login"), {"username": "x", "password": "y"})
        self.assertEqual(resp.status_code, 403)

    def test_superuser_automatically_gets_admin_role(self):
        # Regression test: createsuperuser must not leave 'role' at the
        # CUSTOMER default, or the superuser gets blocked from the
        # platform's own /platform-admin/ dashboard by RBAC middleware.
        su = User.objects.create_superuser(username="root", email="root@example.com", password="RootPass123!")
        self.assertEqual(su.role, User.Role.ADMIN)
        self.client.login(username="root", password="RootPass123!")
        resp = self.client.get("/platform-admin/dashboard/")
        self.assertEqual(resp.status_code, 200)


class BruteForceLockoutTests(TestCase):
    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        self.user = User.objects.create_user(username="target", email="t@example.com", password="RealPassword123!")

    def test_account_locked_after_max_failed_attempts(self):
        for _ in range(5):
            resp = self.client.post(reverse("accounts:login"), {"username": "target", "password": "wrong"})
            self.assertEqual(resp.status_code, 200)

        # 6th attempt (even with the correct password) should now be locked out.
        resp = self.client.post(reverse("accounts:login"), {"username": "target", "password": "RealPassword123!"})
        self.assertEqual(resp.status_code, 429)
        # Confirm the user genuinely was NOT logged in.
        self.assertFalse(resp.wsgi_request.user.is_authenticated)

    def test_successful_login_clears_that_accounts_lockout_counter(self):
        for _ in range(3):
            self.client.post(reverse("accounts:login"), {"username": "target", "password": "wrong"})
        resp = self.client.post(reverse("accounts:login"), {"username": "target", "password": "RealPassword123!"})
        self.assertEqual(resp.status_code, 302)  # successful login, not locked out yet

        self.client.logout()
        # Counter should have been cleared -- a fresh set of failed attempts
        # should NOT immediately be locked out.
        resp = self.client.post(reverse("accounts:login"), {"username": "target", "password": "wrong"})
        self.assertEqual(resp.status_code, 200)  # normal invalid-login response, not 429

    def test_ip_wide_lockout_across_different_usernames(self):
        from .throttling import MAX_ATTEMPTS_PER_IP
        for i in range(MAX_ATTEMPTS_PER_IP):
            self.client.post(reverse("accounts:login"), {"username": f"nosuchuser{i}", "password": "wrong"})
        resp = self.client.post(reverse("accounts:login"), {"username": "yet_another_user", "password": "wrong"})
        self.assertEqual(resp.status_code, 429)
