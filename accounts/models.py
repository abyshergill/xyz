from django.contrib.auth.models import AbstractUser
from django.core.validators import RegexValidator
from django.db import models


class User(AbstractUser):
    """
    Custom user model with a role flag used throughout the platform for
    Role-Based Access Control (RBAC). Django's built-in password hashing
    (see PASSWORD_HASHERS in settings.py, Argon2 by default) is used
    unmodified, so passwords are never stored or handled in plaintext.
    """

    class Role(models.TextChoices):
        ADMIN = "ADMIN", "Platform Admin"
        OWNER = "OWNER", "Food Stall Owner"
        CUSTOMER = "CUSTOMER", "Customer"

    role = models.CharField(max_length=10, choices=Role.choices, default=Role.CUSTOMER)
    email = models.EmailField(unique=True)

    phone_regex = RegexValidator(
        regex=r"^\+?[0-9]{7,15}$",
        message="Enter a valid mobile number (7-15 digits, optional leading +).",
    )
    mobile_number = models.CharField(max_length=16, validators=[phone_regex], blank=True)
    full_name = models.CharField(max_length=150, blank=True, help_text="Customer's full name.")

    is_verified = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    USERNAME_FIELD = "username"
    REQUIRED_FIELDS = ["email"]

    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"

    def save(self, *args, **kwargs):
        # A Django superuser (created via createsuperuser or is_superuser=True)
        # should always be treated as a Platform Admin for RBAC purposes, even
        # if 'role' was never explicitly set. Without this, createsuperuser
        # produces an account that can log into /django-admin/ but gets
        # blocked from the platform's own /platform-admin/ dashboard -- a
        # confusing "admin panel doesn't work" bug.
        if self.is_superuser:
            self.role = self.Role.ADMIN
        super().save(*args, **kwargs)

    @property
    def is_admin_role(self):
        return self.role == self.Role.ADMIN

    @property
    def is_owner_role(self):
        return self.role == self.Role.OWNER

    @property
    def is_customer_role(self):
        return self.role == self.Role.CUSTOMER


class CustomerProfile(models.Model):
    """
    Mandatory registration details for Customers, kept as a separate model
    so owners/admins are not forced to carry irrelevant fields.
    """

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="customer_profile")
    address = models.CharField("Location / Address", max_length=255)
    province = models.CharField(max_length=100)
    pincode = models.CharField(max_length=12)
    country = models.CharField(max_length=100)

    def __str__(self):
        return f"Customer profile: {self.user.username}"


class OwnerProfile(models.Model):
    """Extra profile data for Food Stall / Store Owners."""

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="owner_profile")
    business_registration_number = models.CharField(max_length=100, blank=True)
    payout_notes = models.TextField(blank=True)

    def __str__(self):
        return f"Owner profile: {self.user.username}"

class CustomerAddress(models.Model):
    """Multiple saved addresses for a customer, each with an alias."""
    class Alias(models.TextChoices):
        HOME = "HOME", "Home"
        OFFICE = "OFFICE", "Office"
        OTHER = "OTHER", "Other"

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="addresses")
    alias = models.CharField(max_length=10, choices=Alias.choices, default=Alias.HOME)
    full_name = models.CharField(max_length=150, blank=True, help_text="Recipient name at this address.")
    address = models.CharField(max_length=255)
    pincode = models.CharField(max_length=12, blank=True)
    phone_number = models.CharField(max_length=16, blank=True)
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-is_default", "-created_at"]

    def __str__(self):
        return f"{self.user.username} - {self.get_alias_display()} ({self.address[:30]})"
