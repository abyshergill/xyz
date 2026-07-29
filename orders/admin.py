from django.contrib import admin

from .models import Order, OrderItem, TaxConfiguration


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ("item_name_snapshot", "unit_price_snapshot")


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("order_number", "store", "status", "grand_total", "created_at")
    list_filter = ("status", "store")
    search_fields = ("order_number",)
    inlines = [OrderItemInline]


@admin.register(TaxConfiguration)
class TaxConfigurationAdmin(admin.ModelAdmin):
    list_display = ("store", "label", "tax_type", "value", "is_active")
    list_filter = ("store", "tax_type", "is_active")
