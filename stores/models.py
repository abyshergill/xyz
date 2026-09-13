import datetime
from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.text import slugify
from django.utils.translation import get_language, gettext_lazy as _


class TranslationMaster(models.Model):
    """
    Master translation table for user-generated content.
    Stores exact string matches for target languages.
    """
    original_text = models.CharField(max_length=255, db_index=True)
    language_code = models.CharField(max_length=10, db_index=True)  # e.g., 'th', 'zh-hans', 'hi', 'my'
    translated_text = models.CharField(max_length=255)

    class Meta:
        unique_together = ("original_text", "language_code")
        verbose_name = _("Translation Master")
        verbose_name_plural = _("Translation Master Records")

    def __str__(self):
        return f"{self.original_text} -> {self.language_code}: {self.translated_text}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        cache.delete(f"master_trans_{self.original_text.lower().strip()}_{self.language_code.lower()}")

    def delete(self, *args, **kwargs):
        cache.delete(f"master_trans_{self.original_text.lower().strip()}_{self.language_code.lower()}")
        super().delete(*args, **kwargs)


def get_master_translation(text: str) -> str:
    """
    Looks up translation in TranslationMaster using current session language with fallback to original text.
    Uses caching to keep database reads ultra-fast.
    """
    if not text:
        return ""

    current_lang = get_language()
    if not current_lang or current_lang.lower() in ["en", "en-us"]:
        return text

    clean_text = text.strip()
    cache_key = f"master_trans_{clean_text.lower()}_{current_lang.lower()}"
    cached_val = cache.get(cache_key)
    if cached_val is not None:
        return cached_val

    record = TranslationMaster.objects.filter(
        original_text__iexact=clean_text,
        language_code__iexact=current_lang
    ).first()

    translated = record.translated_text if (record and record.translated_text) else text
    cache.set(cache_key, translated, 86400 * 7)
    return translated


def store_image_path(instance, filename):
    return f"stores/{instance.slug or 'unnamed'}/profile/{filename}"


def food_item_image_path(instance, filename):
    return f"stores/{instance.store.slug}/items/{filename}"


def qr_code_path(instance, filename):
    return f"stores/{instance.slug}/qr/{filename}"


def currency_icon_path(instance, filename):
    return f"stores/{instance.slug or 'unnamed'}/currency/{filename}"


class Store(models.Model):
    class Currency(models.TextChoices):
        USD = "USD", _("US Dollar ($)")
        EUR = "EUR", _("Euro (€)")
        GBP = "GBP", _("British Pound (£)")
        INR = "INR", _("Indian Rupee (₹)")
        THB = "THB", _("Thai Baht (฿)")
        JPY = "JPY", _("Japanese Yen (¥)")
        AUD = "AUD", _("Australian Dollar (A$)")
        CAD = "CAD", _("Canadian Dollar (C$)")
        CNY = "CNY", _("Chinese Yuan (¥)")
        SGD = "SGD", _("Singapore Dollar (S$)")
        AED = "AED", _("UAE Dirham (د.إ)")
        CUSTOM = "CUSTOM", _("Custom symbol / upload own icon")

    CURRENCY_SYMBOLS = {
        "USD": "$", "EUR": "€", "GBP": "£", "INR": "₹", "THB": "฿",
        "JPY": "¥", "AUD": "A$", "CAD": "C$", "CNY": "¥", "SGD": "S$", "AED": "د.إ",
    }

    TIMEZONE_CHOICES = [
        ("Asia/Bangkok", "Thailand (Bangkok)"),
        ("Asia/Kolkata", "India (Kolkata)"),
        ("Asia/Singapore", "Singapore"),
        ("Asia/Kuala_Lumpur", "Malaysia (Kuala Lumpur)"),
        ("Asia/Tokyo", "Japan (Tokyo)"),
        ("Asia/Shanghai", "China (Shanghai)"),
        ("Asia/Dubai", "UAE (Dubai)"),
        ("America/New_York", "USA (New York)"),
        ("America/Chicago", "USA (Chicago)"),
        ("America/Los_Angeles", "USA (Los Angeles)"),
        ("Europe/London", "UK (London)"),
        ("Europe/Paris", "France (Paris)"),
        ("Europe/Berlin", "Germany (Berlin)"),
        ("Europe/Madrid", "Spain (Madrid)"),
        ("Australia/Sydney", "Australia (Sydney)"),
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

    class StoreCategory(models.TextChoices):
        FOOD = "FOOD", _("Food & Beverage")
        ELECTRONICS = "ELECTRONICS", _("Electronics")
        FASHION = "FASHION", _("Fashion & Apparel")
        GROCERY = "GROCERY", _("Grocery & Daily Needs")
        HEALTH = "HEALTH", _("Health & Beauty")
        HOME = "HOME", _("Home & Living")
        SPORTS = "SPORTS", _("Sports & Fitness")
        BOOKS = "BOOKS", _("Books & Stationery")
        TOYS = "TOYS", _("Toys & Games")
        AUTOMOTIVE = "AUTOMOTIVE", _("Automotive")
        OTHER = "OTHER", _("Other")

    store_category = models.CharField(
        max_length=20,
        choices=StoreCategory.choices,
        default=StoreCategory.FOOD,
        help_text=_("What kind of store is this? Customers can filter by this on the main page."),
    )

    pincode = models.CharField(
        max_length=10,
        blank=False,
        null=False,
        default="",
        help_text=_("Required. Customers can search for your store by pincode."),
    )

    address = models.CharField(max_length=255, blank=True)
    phone_number = models.CharField(max_length=16, blank=True)

    timezone = models.CharField(
        max_length=50, default="UTC",
        help_text=_("Select your country/timezone so operating hours match your local time."),
    )

    accept_orders_when_closed = models.BooleanField(
        default=False,
        help_text=_("If enabled, customers can place orders even when your store is closed."),
    )

    currency_code = models.CharField(max_length=10, choices=Currency.choices, default=Currency.USD)
    custom_currency_symbol = models.CharField(
        max_length=8, blank=True,
        help_text=_("Only used when Currency is set to 'Custom' -- e.g. 'Kč', '₪', 'R$'."),
    )
    custom_currency_icon = models.ImageField(
        upload_to=currency_icon_path, blank=True, null=True,
        help_text=_("Optional small icon/logo to use as currency symbol."),
    )

    require_table_number = models.BooleanField(default=True)
    require_phone_number = models.BooleanField(default=True)
    require_email = models.BooleanField(default=False)
    require_customer_name = models.BooleanField(default=False)
    require_customer_address = models.BooleanField(default=False)

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    # ===== LOCALIZED PROPERTIES FOR STORE =====
    @property
    def localized_name(self):
        return get_master_translation(self.name)

    @property
    def localized_description(self):
        return get_master_translation(self.description)

    @property
    def localized_address(self):
        return get_master_translation(self.address)

    @property
    def currency_symbol(self) -> str:
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
        qs = Store.objects.filter(name__iexact=self.name).exclude(pk=self.pk)
        if qs.exists():
            raise ValidationError({"name": _("A store with this name already exists.")})

        if self.currency_code == self.Currency.CUSTOM and not self.custom_currency_symbol and not self.custom_currency_icon:
            raise ValidationError({
                "custom_currency_symbol": _("Provide a custom symbol or upload a currency icon when Currency is Custom."),
            })

        if not self.pincode or not self.pincode.strip():
            raise ValidationError({"pincode": _("Pincode is required.")})

    def is_open_now(self) -> bool:
        import zoneinfo
        from django.utils import timezone as tz

        try:
            tz_info = zoneinfo.ZoneInfo(self.timezone)
        except Exception:
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
        MON = "MON", _("Monday")
        TUE = "TUE", _("Tuesday")
        WED = "WED", _("Wednesday")
        THU = "THU", _("Thursday")
        FRI = "FRI", _("Friday")
        SAT = "SAT", _("Saturday")
        SUN = "SUN", _("Sunday")

    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name="operating_hours")
    day = models.CharField(max_length=3, choices=Day.choices)
    opening_time = models.TimeField(default=datetime.time(9, 0))
    closing_time = models.TimeField(default=datetime.time(21, 0))
    is_closed = models.BooleanField(default=False)

    class Meta:
        unique_together = ("store", "day")
        ordering = ["store", "day"]

    def __str__(self):
        if self.is_closed:
            return f"{self.store.name} - {self.get_day_display()}: {_('Closed')}"
        return f"{self.store.name} - {self.get_day_display()}: {self.opening_time}-{self.closing_time}"


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

    # ===== LOCALIZED PROPERTIES FOR CATEGORY =====
    @property
    def localized_name(self):
        return get_master_translation(self.name)


class FoodItem(models.Model):
    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name="food_items")
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, related_name="items")
    name = models.CharField(max_length=150)
    item_code = models.CharField(
        max_length=50, blank=True, default="",
        help_text=_("Unique code for this item (e.g. SKU, PLU). Leave blank to auto-generate."),
    )
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=8, decimal_places=2)
    tax_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    stock_quantity = models.PositiveIntegerField(default=0)
    min_stock_quantity = models.PositiveIntegerField(default=10)

    image = models.ImageField(upload_to=food_item_image_path, blank=True, null=True)
    is_available = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["category__display_order", "name"]

    def __str__(self):
        return f"{self.name} ({self.store.name})"

    # ===== LOCALIZED PROPERTIES FOR FOOD ITEM =====
    @property
    def localized_name(self):
        return get_master_translation(self.name)

    @property
    def localized_description(self):
        return get_master_translation(self.description)

    @property
    def in_stock(self):
        return self.stock_quantity > 0 and self.is_available

    @property
    def is_low_stock(self):
        return self.stock_quantity <= self.min_stock_quantity

    def save(self, *args, **kwargs):
        if not self.item_code:
            prefix = self.store.slug[:10].upper() if self.store_id else "ITEM"
            self.item_code = f"{prefix}-{self.pk or 'NEW'}"
        super().save(*args, **kwargs)


class ContactMessage(models.Model):
    name = models.CharField(max_length=150, blank=True)
    email = models.EmailField()
    phone_number = models.CharField(max_length=16)
    message = models.CharField(max_length=1000)
    submitted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-submitted_at"]
        verbose_name = "Contact Message"
        verbose_name_plural = "Contact Messages"

    def __str__(self):
        return f"{self.email} — {self.submitted_at:%Y-%m-%d %H:%M}"


class Notification(models.Model):
    class Type(models.TextChoices):
        NEW_ORDER = "NEW_ORDER", _("New Order")
        STATUS_CHANGED = "STATUS_CHANGED", _("Status Changed")
        LOW_STOCK = "LOW_STOCK", _("Low Stock")

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

    # ===== LOCALIZED PROPERTIES FOR NOTIFICATION =====
    @property
    def localized_title(self):
        return get_master_translation(self.title)

    @property
    def localized_message(self):
        return get_master_translation(self.message)