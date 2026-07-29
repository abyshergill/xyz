from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import CustomerProfile, OwnerProfile, User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ("username", "email", "role", "is_verified", "is_active", "created_at")
    list_filter = ("role", "is_active", "is_verified")
    fieldsets = BaseUserAdmin.fieldsets + (
        ("Platform role", {"fields": ("role", "mobile_number", "is_verified")}),
    )


@admin.register(CustomerProfile)
class CustomerProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "province", "pincode", "country")
    search_fields = ("user__username", "user__email", "pincode")


@admin.register(OwnerProfile)
class OwnerProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "business_registration_number")
