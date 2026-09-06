from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from stores.models import Store, Category, FoodItem
from .models import Order, OrderItem
from decimal import Decimal


User = get_user_model()


class OrderModelTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="testowner", email="owner@test.com",
            password="testpass123", role=User.Role.OWNER
        )
        self.store = Store.objects.create(
            owner=self.owner, name="Test Store", pincode="12345",
        )
        self.category = Category.objects.create(store=self.store, name="Food")
        self.item = FoodItem.objects.create(
            store=self.store, category=self.category,
            name="Burger", price=100, stock_quantity=10,
        )

    def test_order_number_generated(self):
        order = Order.objects.create(store=self.store, grand_total=100)
        self.assertTrue(order.order_number.startswith("ORD-"))

    def test_order_status_default_pending(self):
        order = Order.objects.create(store=self.store, grand_total=100)
        self.assertEqual(order.status, Order.Status.PENDING)


class CheckoutTests(TestCase):
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
        self.item = FoodItem.objects.create(
            store=self.store, category=self.category,
            name="Burger", price=100, stock_quantity=10,
        )

    def test_add_to_cart(self):
        response = self.client.post(reverse("orders:add_to_cart", args=[self.store.slug]), {
            "food_item_id": self.item.pk,
            "quantity": 2,
        })
        self.assertEqual(response.status_code, 302)  # redirect fallback
        cart = self.client.session.get(f"cart_{self.store.slug}", {})
        self.assertEqual(cart.get(str(self.item.pk)), 2)

    def test_checkout_page_status_code(self):
        # Allow orders even when closed (no operating hours in test)
        self.store.accept_orders_when_closed = True
        self.store.save()

        # Add item to cart session
        session = self.client.session
        session[f"cart_{self.store.slug}"] = {str(self.item.pk): 1}
        session.save()

        response = self.client.get(reverse("orders:checkout", args=[self.store.slug]))
        self.assertEqual(response.status_code, 200)



    def test_track_order_page_status_code(self):
        response = self.client.get(reverse("orders:track_order"))
        self.assertEqual(response.status_code, 200)


class OrderListViewTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="owner", password="testpass", role="OWNER")
        self.store = Store.objects.create(name="Test Store", owner=self.owner, pincode="12345")
        self.category = Category.objects.create(name="Drinks", store=self.store)
        self.item = FoodItem.objects.create(
            name="Coffee", price=5.00, store=self.store, category=self.category, is_available=True
        )

    def test_order_list_requires_login(self):
        response = self.client.get(reverse("orders:order_list"))
        self.assertEqual(response.status_code, 302)

    def test_order_list_authenticated(self):
        self.client.login(username="owner", password="testpass")
        response = self.client.get(reverse("orders:order_list"))
        self.assertEqual(response.status_code, 200)

    def test_order_list_filter_by_number(self):
        self.client.login(username="owner", password="testpass")
        order = Order.objects.create(
            store=self.store,
            order_number="ORD-TEST123",
            subtotal=Decimal("10.00"),
            tax_total=Decimal("0.00"),
            grand_total=Decimal("10.00"),
            status=Order.Status.PENDING,
        )
        response = self.client.get(reverse("orders:order_list"), {"order_number": "TEST123"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "ORD-TEST123")


class BillGenerationTests(TestCase):
    def setUp(self):
        from decimal import Decimal
        from orders.models import Order, OrderItem

        self.owner = User.objects.create_user(
            username="owner", password="testpass", email="owner@test.com", role="OWNER"
        )
        self.store = Store.objects.create(
            name="Bill Test Store", owner=self.owner, pincode="12345",
            accept_orders_when_closed=True,
        )
        self.category = Category.objects.create(name="Food", store=self.store)
        self.item = FoodItem.objects.create(
            name="Burger", price=Decimal("10.00"), store=self.store,
            category=self.category, is_available=True, stock_quantity=10,
        )
        self.order = Order.objects.create(
            store=self.store,
            order_number="ORD-BILLTEST",
            subtotal=Decimal("10.00"),
            tax_total=Decimal("0.00"),
            grand_total=Decimal("10.00"),
            status=Order.Status.PENDING,
        )
        OrderItem.objects.create(
            order=self.order,
            food_item=self.item,
            item_name_snapshot="Burger",
            unit_price_snapshot=Decimal("10.00"),
            quantity=1,
        )

    def test_bill_pdf_generation(self):
        from .services import generate_order_bill_pdf
        pdf_bytes = generate_order_bill_pdf(self.order)
        self.assertTrue(len(pdf_bytes) > 0)
        self.assertTrue(pdf_bytes.startswith(b"%PDF"))

    def test_bill_download_view(self):
        response = self.client.get(reverse("orders:order_bill", args=[self.order.order_number]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")