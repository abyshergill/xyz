from django.core.exceptions import ValidationError
from django.test import TestCase

from accounts.models import User
from .models import OperatingHours, Store


class StoreUniquenessAndIDORTests(TestCase):
    def setUp(self):
        self.owner1 = User.objects.create_user(
            username="owner_a", email="a@example.com", password="StrongPass123!", role=User.Role.OWNER
        )
        self.owner2 = User.objects.create_user(
            username="owner_b", email="b@example.com", password="StrongPass123!", role=User.Role.OWNER
        )
        self.store1 = Store.objects.create(owner=self.owner1, name="Ramen House", address="1 St")

    def test_duplicate_store_name_rejected(self):
        dupe = Store(owner=self.owner2, name="Ramen House", address="2 St")
        with self.assertRaises(ValidationError):
            dupe.full_clean()

    def test_case_insensitive_duplicate_rejected(self):
        dupe = Store(owner=self.owner2, name="ramen house", address="2 St")
        with self.assertRaises(ValidationError):
            dupe.full_clean()

    def test_owner_cannot_edit_other_owners_store(self):
        self.client.login(username="owner_b", password="StrongPass123!")
        resp = self.client.get(f"/owner/store/{self.store1.slug}/edit/")
        self.assertEqual(resp.status_code, 403)

    def test_owner_cannot_delete_other_owners_item_via_crafted_url(self):
        from .models import Category, FoodItem
        cat = Category.objects.create(store=self.store1, name="Mains")
        item = FoodItem.objects.create(store=self.store1, category=cat, name="Tonkotsu", price=10, stock_quantity=5)

        self.client.login(username="owner_b", password="StrongPass123!")
        resp = self.client.post(f"/owner/store/{self.store1.slug}/items/{item.pk}/delete/")
        self.assertEqual(resp.status_code, 403)
        self.assertTrue(FoodItem.objects.filter(pk=item.pk).exists())


class OperatingHoursFormTests(TestCase):
    """
    Regression tests for a bug where opening the hours form on a fresh
    store (no OperatingHours rows yet) produced 7 blank formset rows with
    an unset 'day' dropdown. If an owner filled in times without manually
    selecting the day for each row, hours saved against the wrong day (or
    didn't save at all), so is_open_now() could never find a match and the
    store appeared permanently closed.
    """

    def setUp(self):
        self.owner = User.objects.create_user(
            username="owner_hours", email="hours@example.com", password="StrongPass123!", role=User.Role.OWNER
        )
        self.store = Store.objects.create(owner=self.owner, name="Fresh Hours Stall", address="1 St")
        self.client.login(username="owner_hours", password="StrongPass123!")

    def test_getting_hours_form_creates_all_seven_days(self):
        self.assertEqual(self.store.operating_hours.count(), 0)
        resp = self.client.get(f"/owner/store/{self.store.slug}/hours/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(self.store.operating_hours.count(), 7)
        days_present = set(self.store.operating_hours.values_list("day", flat=True))
        self.assertEqual(days_present, {code for code, _ in OperatingHours.Day.choices})

    def test_reopening_form_does_not_duplicate_rows(self):
        self.client.get(f"/owner/store/{self.store.slug}/hours/")
        self.client.get(f"/owner/store/{self.store.slug}/hours/")
        self.assertEqual(self.store.operating_hours.count(), 7)

    def test_saving_hours_without_day_in_post_still_saves_to_correct_day(self):
        # Simulates exactly what a real browser submits: the 'day' field is
        # disabled, so browsers omit it from POST entirely.
        self.client.get(f"/owner/store/{self.store.slug}/hours/")  # creates the 7 rows
        hours = list(self.store.operating_hours.order_by("day"))
        today_code = __import__("datetime").datetime.now().strftime("%a").upper()[:3]

        post_data = {
            "operating_hours-TOTAL_FORMS": str(len(hours)),
            "operating_hours-INITIAL_FORMS": str(len(hours)),
            "operating_hours-MIN_NUM_FORMS": "0",
            "operating_hours-MAX_NUM_FORMS": "7",
        }
        for i, h in enumerate(hours):
            post_data[f"operating_hours-{i}-id"] = str(h.pk)
            if h.day == today_code:
                post_data[f"operating_hours-{i}-opening_time"] = "00:00"
                post_data[f"operating_hours-{i}-closing_time"] = "23:59"
            else:
                post_data[f"operating_hours-{i}-opening_time"] = "09:00"
                post_data[f"operating_hours-{i}-closing_time"] = "21:00"
                post_data[f"operating_hours-{i}-is_closed"] = "on"

        resp = self.client.post(f"/owner/store/{self.store.slug}/hours/", post_data, follow=True)
        self.assertEqual(resp.status_code, 200)

        self.store.refresh_from_db()
        # Every row must still have exactly its original, correct day --
        # none were reassigned to the wrong day despite 'day' being absent
        # from the POST body entirely.
        days_after = set(self.store.operating_hours.values_list("day", flat=True))
        self.assertEqual(days_after, {code for code, _ in OperatingHours.Day.choices})
        self.assertEqual(self.store.operating_hours.count(), 7)  # no duplicates created

        today_hours = self.store.operating_hours.get(day=today_code)
        self.assertFalse(today_hours.is_closed)
        self.assertTrue(self.store.is_open_now())
