import datetime

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.text import slugify


def store_image_path(instance, filename):
    return f"stores/{instance.slug or 'unnamed'}/profile/{filename}"


def food_item_image_path(instance, filename):
    return f"stores/{instance.store.slug}/items/{filename}"


def qr_code_path(instance, filename):
    return f"stores/{instance.slug}/qr/{filename}"


def currency_icon_path(instance, filename):
    return f"stores/{instance.slug or 'unnamed'}/currency/{filename}"


class Store(models.Model):
    """
    A single food stall / store, owned by exactly one User (role=OWNER).
    Store names are enforced unique platform-wide per the spec.
    """

    # Common currencies offered as a quick pick; CUSTOM lets an owner define
    # their own symbol (text) and/or upload a small custom currency icon
    # image (e.g. for a local/regional currency without a standard glyph).
    class Currency(models.TextChoices):
        USD = "USD", "US Dollar ($)"
        EUR = "EUR", "Euro (€)"
        GBP = "GBP", "British Pound (£)"
        INR = "INR", "Indian Rupee (₹)"
        THB = "THB", "Thai Baht (฿)"
        JPY = "JPY", "Japanese Yen (¥)"
        AUD = "AUD", "Australian Dollar (A$)"
        CAD = "CAD", "Canadian Dollar (C$)"
        CNY = "CNY", "Chinese Yuan (¥)"
        SGD = "SGD", "Singapore Dollar (S$)"
        AED = "AED", "UAE Dirham (د.إ)"
        CUSTOM = "CUSTOM", "Custom symbol / upload own icon"

    CURRENCY_SYMBOLS = {
        "USD": "$", "EUR": "€", "GBP": "£", "INR": "₹", "THB": "฿",
        "JPY": "¥", "AUD": "A$", "CAD": "C$", "CNY": "¥", "SGD": "S$", "AED": "د.إ",
    }

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="stores"
    )
    name = models.CharField(max_length=150, unique=True)
    slug = models.SlugField(max_length=170, unique=True, blank=True)
    description = models.TextField(blank=True)

    store_picture = models.ImageField(upload_to=store_image_path, blank=True, null=True)
    qr_code = models.ImageField(upload_to=qr_code_path, blank=True, null=True)

    # Contact / location
    address = models.CharField(max_length=255, blank=True)
    phone_number = models.CharField(max_length=16, blank=True)

    # Currency: pick a common one, or go CUSTOM and supply a text symbol
    # and/or upload a small icon image to use instead of/alongside text.
    currency_code = models.CharField(max_length=10, choices=Currency.choices, default=Currency.USD)
    custom_currency_symbol = models.CharField(
        max_length=8, blank=True,
        help_text="Only used when Currency is set to 'Custom' -- e.g. 'Kč', '₪', 'R$'.",
    )
    custom_currency_icon = models.ImageField(
        upload_to=currency_icon_path, blank=True, null=True,
        help_text="Optional small icon/logo to use as the currency symbol instead of text (only used when Currency is 'Custom').",
    )

    # Checkout field toggles -- the store owner decides which fields are
    # mandatory at checkout for their store.
    require_table_number = models.BooleanField(default=True)
    require_phone_number = models.BooleanField(default=True)
    require_email = models.BooleanField(default=False)

    is_active = models.BooleanField(default=True, help_text="Owner can temporarily deactivate the store.")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    @property
    def currency_symbol(self) -> str:
        """
        Text symbol to prefix prices with. Falls back sensibly: a custom
        text symbol if provided, otherwise the known symbol for the chosen
        currency code, otherwise the raw currency code itself.
        """
        if self.currency_code == self.Currency.CUSTOM:
            return self.custom_currency_symbol or "¤"
        return self.CURRENCY_SYMBOLS.get(self.currency_code, self.currency_code)

    @property
    def has_custom_currency_icon(self) -> bool:
        return self.currency_code == self.Currency.CUSTOM and bool(self.custom_currency_icon)

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.name)
            slug = base_slug
            counter = 1
            while Store.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                counter += 1
                slug = f"{base_slug}-{counter}"
            self.slug = slug
        super().save(*args, **kwargs)

    def clean(self):
        # Case-insensitive uniqueness check (DB unique=True is case-sensitive
        # on SQLite/Postgres by default for CharField).
        qs = Store.objects.filter(name__iexact=self.name).exclude(pk=self.pk)
        if qs.exists():
            raise ValidationError({"name": "A store with this name already exists."})

        if self.currency_code == self.Currency.CUSTOM and not self.custom_currency_symbol and not self.custom_currency_icon:
            raise ValidationError({
                "custom_currency_symbol": "Provide a custom symbol (e.g. 'Kč') or upload a currency icon when Currency is set to Custom.",
            })

    def is_open_now(self) -> bool:
        """
        Real-time check used before accepting new orders.

        Uses Django's timezone-aware clock (django.utils.timezone), which
        respects the TIME_ZONE setting, rather than the server OS's raw
        system clock. This matters because most servers/containers run
        their system clock in UTC regardless of where the store actually
        is -- using datetime.datetime.now() directly would silently check
        the wrong hours whenever the server's OS timezone doesn't match
        the store's real-world timezone. Set DJANGO_TIME_ZONE in your .env
        to your store's actual timezone (e.g. "Asia/Bangkok") for this to
        reflect real local time.
        """
        now = timezone.localtime(timezone.now())
        weekday = now.strftime("%a").upper()[:3]
        hours = self.operating_hours.filter(day=weekday, is_closed=False).first()
        if not hours:
            return False
        current_time = now.time()
        if hours.opening_time <= hours.closing_time:
            return hours.opening_time <= current_time <= hours.closing_time
        # Overnight window (e.g. 18:00 - 02:00)
        return current_time >= hours.opening_time or current_time <= hours.closing_time


class OperatingHours(models.Model):
    class Day(models.TextChoices):
        MON = "MON", "Monday"
        TUE = "TUE", "Tuesday"
        WED = "WED", "Wednesday"
        THU = "THU", "Thursday"
        FRI = "FRI", "Friday"
        SAT = "SAT", "Saturday"
        SUN = "SUN", "Sunday"

    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name="operating_hours")
    day = models.CharField(max_length=3, choices=Day.choices)
    opening_time = models.TimeField(default=datetime.time(9, 0))
    closing_time = models.TimeField(default=datetime.time(21, 0))
    is_closed = models.BooleanField(default=False, help_text="Store is closed all day on this day.")

    class Meta:
        unique_together = ("store", "day")
        ordering = ["store", "day"]

    def __str__(self):
        if self.is_closed:
            return f"{self.store.name} - {self.day}: Closed"
        return f"{self.store.name} - {self.day}: {self.opening_time}-{self.closing_time}"


class Category(models.Model):
    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name="categories")
    name = models.CharField(max_length=100)
    display_order = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = ("store", "name")
        ordering = ["display_order", "name"]
        verbose_name_plural = "categories"

    def __str__(self):
        return f"{self.store.name} / {self.name}"


class FoodItem(models.Model):
    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name="food_items")
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, related_name="items")
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=8, decimal_places=2)
    stock_quantity = models.PositiveIntegerField(default=0)
    image = models.ImageField(upload_to=food_item_image_path, blank=True, null=True)
    is_available = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["category__display_order", "name"]

    def __str__(self):
        return f"{self.name} ({self.store.name})"

    @property
    def in_stock(self):
        return self.stock_quantity > 0 and self.is_available
