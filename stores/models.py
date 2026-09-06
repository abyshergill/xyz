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

    # Common timezones grouped by region for the dropdown
    TIMEZONE_CHOICES = [
        # Thailand
        ("Asia/Bangkok", "Thailand (Bangkok)"),
        # India
        ("Asia/Kolkata", "India (Kolkata)"),
        # Singapore
        ("Asia/Singapore", "Singapore"),
        # Malaysia
        ("Asia/Kuala_Lumpur", "Malaysia (Kuala Lumpur)"),
        # Japan
        ("Asia/Tokyo", "Japan (Tokyo)"),
        # China
        ("Asia/Shanghai", "China (Shanghai)"),
        # UAE
        ("Asia/Dubai", "UAE (Dubai)"),
        # USA
        ("America/New_York", "USA (New York)"),
        ("America/Chicago", "USA (Chicago)"),
        ("America/Los_Angeles", "USA (Los Angeles)"),
        # UK
        ("Europe/London", "UK (London)"),
        # Europe
        ("Europe/Paris", "France (Paris)"),
        ("Europe/Berlin", "Germany (Berlin)"),
        ("Europe/Madrid", "Spain (Madrid)"),
        # Australia
        ("Australia/Sydney", "Australia (Sydney)"),
        # Default
        ("UTC", "UTC"),
    ]

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="stores"
    )
    name = models.CharField(max_length=150, unique=True)
    slug = models.SlugField(max_length=170, unique=True, blank=True)
    description = models.TextField(blank=True)

    store_picture = models.ImageField(upload_to=store_image_path, blank=True, null=True)
    qr_code = models.ImageField(upload_to=qr_code_path, blank=True, null=True)

     # Store category — what kind of store is this?
    class StoreCategory(models.TextChoices):
        FOOD = "FOOD", "Food & Beverage"
        ELECTRONICS = "ELECTRONICS", "Electronics"
        FASHION = "FASHION", "Fashion & Apparel"
        GROCERY = "GROCERY", "Grocery & Daily Needs"
        HEALTH = "HEALTH", "Health & Beauty"
        HOME = "HOME", "Home & Living"
        SPORTS = "SPORTS", "Sports & Fitness"
        BOOKS = "BOOKS", "Books & Stationery"
        TOYS = "TOYS", "Toys & Games"
        AUTOMOTIVE = "AUTOMOTIVE", "Automotive"
        OTHER = "OTHER", "Other"

    store_category = models.CharField(
        max_length=20,
        choices=StoreCategory.choices,
        default=StoreCategory.FOOD,
        help_text="What kind of store is this? Customers can filter by this on the main page.",
    )

    pincode = models.CharField(
        max_length=10,
        blank=False,
        null=False,
        default="",
        help_text="Required. Customers can search for your store by pincode.",
    )

    # ===== ADD THESE TWO LINES =====
    address = models.CharField(max_length=255, blank=True)
    phone_number = models.CharField(max_length=16, blank=True)
    # ===============================

    # Store timezone — determines what "now" means for is_open_now()
    timezone = models.CharField(
        max_length=50, default="UTC",
        help_text="Select your country/timezone so operating hours match your local time.",
    )

    # Allow owner to accept orders even when store is closed
    accept_orders_when_closed = models.BooleanField(
        default=False,
        help_text="If enabled, customers can place orders even when your store is closed.",
    )


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
    require_customer_name = models.BooleanField(default=False, help_text="Ask for the customer's name at checkout.")
    require_customer_address = models.BooleanField(default=False, help_text="Ask for the customer's address at checkout.")

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
        # Case-insensitive uniqueness check
        qs = Store.objects.filter(name__iexact=self.name).exclude(pk=self.pk)
        if qs.exists():
            raise ValidationError({"name": "A store with this name already exists."})

        if self.currency_code == self.Currency.CUSTOM and not self.custom_currency_symbol and not self.custom_currency_icon:
            raise ValidationError({
                "custom_currency_symbol": "Provide a custom symbol (e.g. 'K') or upload a currency icon when Currency is set to Custom.",
            })

        # Pincode is compulsory
        if not self.pincode or not self.pincode.strip():
            raise ValidationError({"pincode": "Pincode is required."})

    def is_open_now(self) -> bool:
        """
        Real-time check using the store's own timezone (not the server's).
        Falls back to TIME_ZONE setting if store.timezone is not set.
        """
        import zoneinfo
        from django.utils import timezone as tz

        try:
            tz_info = zoneinfo.ZoneInfo(self.timezone)
        except Exception:
            from django.conf import settings
            tz_info = zoneinfo.ZoneInfo(settings.TIME_ZONE)

        now = tz.now().astimezone(tz_info)
        weekday = now.strftime("%a").upper()[:3]
        hours = self.operating_hours.filter(day=weekday, is_closed=False).first()
        if not hours:
            return False
        current_time = now.time()
        if hours.opening_time <= hours.closing_time:
            return hours.opening_time <= current_time <= hours.closing_time
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
    item_code = models.CharField(
        max_length=50, blank=True, default="",
        help_text="Unique code for this item (e.g. SKU, PLU). Leave blank to auto-generate.",
    )
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=8, decimal_places=2)
    tax_percentage = models.DecimalField(
        max_digits=5, decimal_places=2, default=0,
        help_text="Tax % for this item (e.g. 7.00 for 7%). Set to 0 if price is final (no tax).",
    )
    stock_quantity = models.PositiveIntegerField(default=0)

    # ===== ADD THESE TWO FIELDS =====
    item_code = models.CharField(
        max_length=50, blank=True, default="",
        help_text="Unique code for this item (e.g. SKU, PLU). Leave blank to auto-generate.",
    )
    min_stock_quantity = models.PositiveIntegerField(
        default=10,
        help_text="Alert when stock falls below this number.",
    )
    # ===== END NEW FIELDS =====

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

    @property
    def is_low_stock(self):
        return self.stock_quantity <= self.min_stock_quantity

    def save(self, *args, **kwargs):
        if not self.item_code:
            # Auto-generate: STORE-ITEM-PK format
            prefix = self.store.slug[:10].upper() if self.store_id else "ITEM"
            self.item_code = f"{prefix}-{self.pk or 'NEW'}"
        super().save(*args, **kwargs)


    # --- Store category (what kind of store is this?) ---
    class StoreCategory(models.TextChoices):
        FOOD = "FOOD", "Food & Beverage"
        ELECTRONICS = "ELECTRONICS", "Electronics"
        FASHION = "FASHION", "Fashion & Apparel"
        GROCERY = "GROCERY", "Grocery & Daily Needs"
        HEALTH = "HEALTH", "Health & Beauty"
        HOME = "HOME", "Home & Living"
        SPORTS = "SPORTS", "Sports & Fitness"
        BOOKS = "BOOKS", "Books & Stationery"
        TOYS = "TOYS", "Toys & Games"
        AUTOMOTIVE = "AUTOMOTIVE", "Automotive"
        OTHER = "OTHER", "Other"

    store_category = models.CharField(
        max_length=20,
        choices=StoreCategory.choices,
        default=StoreCategory.FOOD,
        help_text="What kind of store is this? Customers can filter by this on the main page.",
    )

    # --- Pincode (compulsory) ---
    pincode = models.CharField(
        max_length=10,
        blank=False,
        null=False,
        help_text="Required. Customers can search for stores by pincode.",
    )


class ContactMessage(models.Model):
    """Stores complaints/concerns submitted by visitors via the Contact Us page."""
    name = models.CharField(max_length=150, blank=True, help_text="Optional.")
    email = models.EmailField()
    phone_number = models.CharField(max_length=16)
    message = models.CharField(max_length=1000, help_text="Maximum 1000 characters.")
    submitted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-submitted_at"]
        verbose_name = "Contact Message"
        verbose_name_plural = "Contact Messages"

    def __str__(self):
        return f"{self.email} — {self.submitted_at:%Y-%m-%d %H:%M}"

class Notification(models.Model):
    """Notifications for both owners and customers."""
    class Type(models.TextChoices):
        NEW_ORDER = "NEW_ORDER", "New Order"
        STATUS_CHANGED = "STATUS_CHANGED", "Status Changed"
        LOW_STOCK = "LOW_STOCK", "Low Stock"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="notifications"
    )
    notification_type = models.CharField(max_length=20, choices=Type.choices)
    title = models.CharField(max_length=200)
    message = models.TextField()
    order = models.ForeignKey(
        "orders.Order", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="notifications"
    )
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.notification_type}: {self.title} ({self.user.username})"
