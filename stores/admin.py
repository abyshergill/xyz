from django.contrib import admin

from .models import Category, FoodItem, OperatingHours, Store, ContactMessage


class OperatingHoursInline(admin.TabularInline):
    model = OperatingHours
    extra = 0


@admin.register(Store)
class StoreAdmin(admin.ModelAdmin):
    list_display = ("name", "owner", "currency_code", "is_active", "created_at")
    search_fields = ("name", "owner__username")
    prepopulated_fields = {"slug": ("name",)}
    inlines = [OperatingHoursInline]


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "store", "display_order")
    list_filter = ("store",)


@admin.register(FoodItem)
class FoodItemAdmin(admin.ModelAdmin):
    list_display = ("name", "store", "category", "price", "stock_quantity", "is_available")
    list_filter = ("store", "category", "is_available")
    search_fields = ("name",)

@admin.register(ContactMessage)
class ContactMessageAdmin(admin.ModelAdmin):
    list_display = ("email", "phone_number", "submitted_at", "short_message")
    list_filter = ("submitted_at",)
    search_fields = ("email", "phone_number", "message")
    readonly_fields = ("submitted_at",)
    date_hierarchy = "submitted_at"

    def short_message(self, obj):
        return obj.message[:80] + "..." if len(obj.message) > 80 else obj.message
    short_message.short_description = "Message"

