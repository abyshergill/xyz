from django.contrib import admin

from .models import Category, FoodItem, OperatingHours, Store


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
