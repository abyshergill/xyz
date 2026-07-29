import uuid

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models, transaction

from stores.models import FoodItem, Store


class TaxConfiguration(models.Model):
    """Per-store billing rule: either a flat fee or a percentage surcharge."""

    class TaxType(models.TextChoices):
        PERCENTAGE = "PERCENT", "Percentage of subtotal"
        FIXED = "FIXED", "Fixed amount"

    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name="tax_configurations")
    label = models.CharField(max_length=60, help_text="e.g. 'GST', 'Service Charge'")
    tax_type = models.CharField(max_length=10, choices=TaxType.choices, default=TaxType.PERCENTAGE)
    value = models.DecimalField(
        max_digits=8, decimal_places=2,
        help_text="Percentage (e.g. 5.00 for 5%) or fixed currency amount, depending on Tax Type.",
    )
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.store.name}: {self.label}"

    def apply(self, subtotal):
        if self.tax_type == self.TaxType.PERCENTAGE:
            return (subtotal * self.value) / 100
        return self.value


class Order(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        CONFIRMED = "CONFIRMED", "Order Received (Confirmed)"
        PREPARING = "PREPARING", "Preparing"
        COMPLETED = "COMPLETED", "Completed"
        CANCELLED = "CANCELLED", "Cancelled"

    order_number = models.CharField(max_length=20, unique=True, editable=False)
    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name="orders")
    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="orders"
    )

    # Guest / checkout-time contact fields (toggle-controlled by Store settings)
    table_number = models.CharField(max_length=20, blank=True)
    contact_phone = models.CharField(max_length=16, blank=True)
    contact_email = models.EmailField(blank=True)

    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)

    # Order merging: when several active orders are consolidated onto a
    # single master ticket, each merged order points at the master while
    # keeping its own OrderItems intact for individual tracking.
    merged_into = models.ForeignKey(
        "self", on_delete=models.SET_NULL, null=True, blank=True, related_name="merged_orders"
    )

    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    tax_total = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    grand_total = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.order_number

    def save(self, *args, **kwargs):
        if not self.order_number:
            self.order_number = f"ORD-{uuid.uuid4().hex[:10].upper()}"
        super().save(*args, **kwargs)

    @property
    def is_master(self):
        return self.merged_orders.exists()

    @property
    def is_merged_child(self):
        return self.merged_into_id is not None

    def recalculate_totals(self, commit=True):
        """
        Recomputes subtotal/tax/grand_total from line items (+ merged child
        orders, if this is a master ticket) and the store's active tax rules.
        """
        with transaction.atomic():
            items = OrderItem.objects.filter(order=self)
            if self.is_master:
                items = OrderItem.objects.filter(
                    models.Q(order=self) | models.Q(order__merged_into=self)
                )
            subtotal = sum((i.line_total for i in items), start=0)

            tax_total = 0
            for tax in self.store.tax_configurations.filter(is_active=True):
                tax_total += tax.apply(subtotal)

            self.subtotal = subtotal
            self.tax_total = tax_total
            self.grand_total = subtotal + tax_total
            if commit:
                self.save(update_fields=["subtotal", "tax_total", "grand_total", "updated_at"])
        return self.grand_total


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    food_item = models.ForeignKey(FoodItem, on_delete=models.PROTECT, related_name="order_items")
    item_name_snapshot = models.CharField(max_length=150)
    unit_price_snapshot = models.DecimalField(max_digits=8, decimal_places=2)
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])

    def save(self, *args, **kwargs):
        if not self.item_name_snapshot:
            self.item_name_snapshot = self.food_item.name
        if not self.unit_price_snapshot:
            self.unit_price_snapshot = self.food_item.price
        super().save(*args, **kwargs)

    @property
    def line_total(self):
        return self.unit_price_snapshot * self.quantity

    def __str__(self):
        return f"{self.quantity} x {self.item_name_snapshot}"
