from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from .models import Store, Category, FoodItem, Notification

User = get_user_model()


class StoreModelTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="testowner", email="owner@test.com",
            password="testpass123", role=User.Role.OWNER
        )
        self.store = Store.objects.create(
            owner=self.owner, name="Test Store", pincode="12345",
            store_category=Store.StoreCategory.FOOD,
        )

    def test_store_str(self):
        self.assertEqual(str(self.store), "Test Store")

    def test_store_slug_generated(self):
        self.assertEqual(self.store.slug, "test-store")

    def test_pincode_required(self):
        from django.core.exceptions import ValidationError
        store = Store(owner=self.owner, name="No Pincode", pincode="")
        with self.assertRaises(ValidationError):
            store.full_clean()

    def test_is_open_now_returns_bool(self):
        self.assertIn(self.store.is_open_now(), [True, False])


class FoodItemModelTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="testowner", email="owner@test.com",
            password="testpass123", role=User.Role.OWNER
        )
        self.store = Store.objects.create(
            owner=self.owner, name="Test Store", pincode="12345",
        )
        self.category = Category.objects.create(store=self.store, name="Drinks")
        self.item = FoodItem.objects.create(
            store=self.store, category=self.category,
            name="Coffee", price=50, stock_quantity=10,
        )

    def test_item_code_auto_generated(self):
        self.assertTrue(self.item.item_code)

    def test_in_stock_when_available_and_quantity(self):
        self.assertTrue(self.item.in_stock)

    def test_out_of_stock_when_zero(self):
        self.item.stock_quantity = 0
        self.assertFalse(self.item.in_stock)


class StoreViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.owner = User.objects.create_user(
            username="testowner", email="owner@test.com",
            password="testpass123", role=User.Role.OWNER
        )
        self.store = Store.objects.create(
            owner=self.owner, name="Test Store", pincode="12345",
        )

    def test_store_list_status_code(self):
        response = self.client.get(reverse("stores:store_list"))
        self.assertEqual(response.status_code, 200)

    def test_store_detail_status_code(self):
        response = self.client.get(reverse("stores:store_detail", args=[self.store.slug]))
        self.assertEqual(response.status_code, 200)

    def test_store_detail_with_search(self):
        response = self.client.get(reverse("stores:store_detail", args=[self.store.slug]), {"item_q": "coffee"})
        self.assertEqual(response.status_code, 200)

    def test_owner_dashboard_requires_login(self):
        response = self.client.get(reverse("stores:owner_dashboard"))
        self.assertEqual(response.status_code, 302)  # redirect to login

    def test_owner_dashboard_authenticated(self):
        self.client.login(username="testowner", password="testpass123")
        response = self.client.get(reverse("stores:owner_dashboard"))
        self.assertEqual(response.status_code, 200)


class ItemListViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.owner = User.objects.create_user(
            username="testowner", email="owner@test.com",
            password="testpass123", role=User.Role.OWNER
        )
        self.store = Store.objects.create(
            owner=self.owner, name="Test Store", pincode="12345",
        )
        self.category = Category.objects.create(store=self.store, name="Food")
        for i in range(25):
            FoodItem.objects.create(
                store=self.store, category=self.category,
                name=f"Item {i}", price=10 + i,
            )

    def test_item_list_pagination_20_per_page(self):
        self.client.login(username="testowner", password="testpass123")
        response = self.client.get(reverse("stores:item_list", args=[self.store.slug]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["page_obj"].object_list), 20)

    def test_item_list_filter_by_category(self):
        self.client.login(username="testowner", password="testpass123")
        response = self.client.get(reverse("stores:item_list", args=[self.store.slug]), {"category": "Food"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["page_obj"].object_list), 20)

    def test_item_list_search_by_name(self):
        self.client.login(username="testowner", password="testpass123")
        response = self.client.get(reverse("stores:item_list", args=[self.store.slug]), {"item_q": "Item 1"})
        self.assertEqual(response.status_code, 200)
        # Should find Item 1, Item 10-19 (names containing "Item 1")
        self.assertTrue(len(response.context["page_obj"].object_list) > 0)


class NotificationModelTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="testowner", email="owner@test.com",
            password="testpass123", role=User.Role.OWNER
        )
        self.store = Store.objects.create(
            owner=self.owner, name="Test Store", pincode="12345",
        )

    def test_notification_creation(self):
        notif = Notification.objects.create(
            user=self.owner,
            notification_type=Notification.Type.NEW_ORDER,
            title="Test Notification",
            message="Test message",
        )
        self.assertEqual(str(notif), "NEW_ORDER: Test Notification (testowner)")
        self.assertFalse(notif.is_read)

    def test_notifications_view_requires_login(self):
        response = self.client.get(reverse("stores:notifications"))
        self.assertEqual(response.status_code, 302)

    def test_notifications_view_authenticated(self):
        self.client.login(username="testowner", password="testpass123")
        response = self.client.get(reverse("stores:notifications"))
        self.assertEqual(response.status_code, 200)


class ContactUsTests(TestCase):
    def test_contact_us_page_status_code(self):
        response = self.client.get(reverse("stores:contact_us"))
        self.assertEqual(response.status_code, 200)

    def test_contact_us_form_submission(self):
        response = self.client.post(reverse("stores:contact_us"), {
            "name": "Test User",
            "email": "test@test.com",
            "phone_number": "1234567890",
            "message": "This is a test complaint.",
        })
        self.assertEqual(response.status_code, 302)  # redirect after success