import datetime

from django.test import TestCase

from accounts.models import User
from stores.models import Category, FoodItem, OperatingHours, Store

from .models import Order
from .services import OrderMergeError, create_order_with_items, merge_orders


def _open_all_week(store):
    for day, _ in OperatingHours.Day.choices:
        OperatingHours.objects.create(
            store=store, day=day,
            opening_time=datetime.time(0, 0), closing_time=datetime.time(23, 59),
        )


class CheckoutStockSafetyTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="owner_c", email="c@example.com", password="StrongPass123!", role=User.Role.OWNER
        )
        self.store = Store.objects.create(owner=self.owner, name="Curry Corner", address="1 St")
        _open_all_week(self.store)
        self.category = Category.objects.create(store=self.store, name="Mains")
        self.item = FoodItem.objects.create(
            store=self.store, category=self.category, name="Green Curry", price=9.00, stock_quantity=3
        )

    def test_order_creation_decrements_stock(self):
        order = create_order_with_items(
            store=self.store, cart_rows=[{"food_item": self.item, "quantity": 2}],
        )
        self.item.refresh_from_db()
        self.assertEqual(self.item.stock_quantity, 1)
        self.assertEqual(order.grand_total, self.item.order_items.first().line_total)

    def test_cannot_oversell_stock(self):
        with self.assertRaises(OrderMergeError):
            create_order_with_items(
                store=self.store, cart_rows=[{"food_item": self.item, "quantity": 99}],
            )
        self.item.refresh_from_db()
        self.assertEqual(self.item.stock_quantity, 3)  # unchanged on failure

    def test_checkout_blocked_when_store_closed(self):
        self.store.operating_hours.all().delete()  # no hours configured => closed
        resp = self.client.post(
            f"/store/{self.store.slug}/cart/add/", {"food_item_id": self.item.pk, "quantity": 1}
        )
        self.assertEqual(resp.status_code, 302)
        resp = self.client.get(f"/store/{self.store.slug}/checkout/", follow=True)
        self.assertContains(resp, "closed")


class OrderMergeTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="owner_d", email="d@example.com", password="StrongPass123!", role=User.Role.OWNER
        )
        self.other_owner = User.objects.create_user(
            username="owner_e", email="e@example.com", password="StrongPass123!", role=User.Role.OWNER
        )
        self.store = Store.objects.create(owner=self.owner, name="Taco Town", address="1 St")
        self.other_store = Store.objects.create(owner=self.other_owner, name="Burrito Bar", address="2 St")
        _open_all_week(self.store)
        self.category = Category.objects.create(store=self.store, name="Tacos")
        self.item = FoodItem.objects.create(store=self.store, category=self.category, name="Al Pastor", price=4.00, stock_quantity=20)

    def test_merge_preserves_individual_items_and_totals(self):
        order1 = create_order_with_items(store=self.store, cart_rows=[{"food_item": self.item, "quantity": 2}])
        order2 = create_order_with_items(store=self.store, cart_rows=[{"food_item": self.item, "quantity": 3}])

        master = merge_orders([order1, order2], initiating_owner=self.owner)

        order1.refresh_from_db()
        order2.refresh_from_db()
        self.assertEqual(order1.merged_into_id, master.id)
        self.assertEqual(order2.merged_into_id, master.id)
        self.assertEqual(order1.items.count(), 1)  # individual tracking preserved
        self.assertEqual(order2.items.count(), 1)
        self.assertEqual(master.grand_total, 20.00)  # (2+3) * 4.00

    def test_cannot_merge_orders_from_different_stores(self):
        order1 = create_order_with_items(store=self.store, cart_rows=[{"food_item": self.item, "quantity": 1}])
        other_item = FoodItem.objects.create(store=self.other_store, name="Burrito", price=6.00, stock_quantity=5)
        order2 = create_order_with_items(store=self.other_store, cart_rows=[{"food_item": other_item, "quantity": 1}])

        with self.assertRaises(OrderMergeError):
            merge_orders([order1, order2], initiating_owner=self.owner)

    def test_cannot_merge_another_owners_orders(self):
        order1 = create_order_with_items(store=self.store, cart_rows=[{"food_item": self.item, "quantity": 1}])
        order2 = create_order_with_items(store=self.store, cart_rows=[{"food_item": self.item, "quantity": 1}])

        with self.assertRaises(OrderMergeError):
            merge_orders([order1, order2], initiating_owner=self.other_owner)

    def test_owner_cannot_view_other_stores_order(self):
        order1 = create_order_with_items(store=self.other_store, cart_rows=[])
        self.client.login(username="owner_d", password="StrongPass123!")
        resp = self.client.get(f"/owner/orders/{order1.order_number}/")
        self.assertEqual(resp.status_code, 403)


class CurrencyAndTrackingTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="owner_f", email="f@example.com", password="StrongPass123!", role=User.Role.OWNER
        )
        self.store = Store.objects.create(
            owner=self.owner, name="Baht Bites", address="1 St", currency_code=Store.Currency.THB,
        )
        _open_all_week(self.store)
        self.item = FoodItem.objects.create(store=self.store, name="Som Tam", price=45, stock_quantity=10)

    def test_currency_symbol_reflects_store_choice(self):
        self.assertEqual(self.store.currency_symbol, "฿")

    def test_custom_currency_requires_symbol_or_icon(self):
        from django.core.exceptions import ValidationError
        custom_store = Store(owner=self.owner, name="Custom Currency Stall", currency_code=Store.Currency.CUSTOM)
        with self.assertRaises(ValidationError):
            custom_store.full_clean()

    def test_custom_currency_symbol_used_when_provided(self):
        custom_store = Store.objects.create(
            owner=self.owner, name="Kroner Kiosk", currency_code=Store.Currency.CUSTOM,
            custom_currency_symbol="kr",
        )
        self.assertEqual(custom_store.currency_symbol, "kr")

    def test_order_confirmed_status_available_and_settable(self):
        order = create_order_with_items(store=self.store, cart_rows=[{"food_item": self.item, "quantity": 1}])
        self.client.login(username="owner_f", password="StrongPass123!")
        resp = self.client.post(f"/owner/orders/{order.order_number}/status/", {"status": "CONFIRMED"}, follow=True)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.CONFIRMED)

    def test_bill_pdf_downloads(self):
        order = create_order_with_items(store=self.store, cart_rows=[{"food_item": self.item, "quantity": 2}])
        resp = self.client.get(f"/order/{order.order_number}/bill/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "application/pdf")
        self.assertTrue(resp.content.startswith(b"%PDF-"))

    def test_track_order_requires_correct_verification(self):
        order = create_order_with_items(
            store=self.store, cart_rows=[{"food_item": self.item, "quantity": 1}],
            contact_fields={"table_number": "7"},
        )
        # Correct verification succeeds.
        resp = self.client.post("/track-order/", {"order_number": order.order_number, "verification": "7"})
        self.assertContains(resp, order.get_status_display())

        # Wrong verification does not leak the order's details -- the order
        # number naturally reappears as the pre-filled form value, but the
        # order's status/table/total must not be revealed.
        resp = self.client.post("/track-order/", {"order_number": order.order_number, "verification": "wrong"})
        self.assertNotContains(resp, order.get_status_display())
        self.assertContains(resp, "couldn")  # the "couldn't find" error message rendered

    def test_checkout_cart_shows_items_and_allows_removal(self):
        session = self.client.session
        session[f"cart_{self.store.slug}"] = {str(self.item.pk): 2}
        session.save()

        resp = self.client.get(f"/store/{self.store.slug}/checkout/")
        self.assertContains(resp, self.item.name)
        self.assertContains(resp, "฿")

        resp = self.client.post(f"/store/{self.store.slug}/cart/remove/", {"food_item_id": self.item.pk}, follow=True)
        self.assertNotIn(str(self.item.pk), self.client.session.get(f"cart_{self.store.slug}", {}))
