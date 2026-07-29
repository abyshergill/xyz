from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.core.exceptions import ValidationError

from .models import CustomerProfile, OwnerProfile, User


class CustomerRegistrationForm(UserCreationForm):
    """
    Registration form enforcing the mandatory customer fields:
    Mobile Number, Email, Location/Address, Province, Pincode, Country.
    Uses Django's UserCreationForm so password confirmation + strength
    validation (AUTH_PASSWORD_VALIDATORS) are inherited for free.
    """

    email = forms.EmailField(required=True)
    mobile_number = forms.CharField(max_length=16, required=True, label="Mobile Number")
    address = forms.CharField(max_length=255, required=True, label="Location / Address")
    province = forms.CharField(max_length=100, required=True)
    pincode = forms.CharField(max_length=12, required=True)
    country = forms.CharField(max_length=100, required=True)

    class Meta:
        model = User
        fields = ["username", "email", "mobile_number", "password1", "password2"]

    def clean_email(self):
        email = self.cleaned_data["email"].lower().strip()
        if User.objects.filter(email__iexact=email).exists():
            raise ValidationError("An account already exists with this email address.")
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"]
        user.mobile_number = self.cleaned_data["mobile_number"]
        user.role = User.Role.CUSTOMER
        if commit:
            user.save()
            CustomerProfile.objects.create(
                user=user,
                address=self.cleaned_data["address"],
                province=self.cleaned_data["province"],
                pincode=self.cleaned_data["pincode"],
                country=self.cleaned_data["country"],
            )
        return user


class OwnerRegistrationForm(UserCreationForm):
    """Registration for a new Food Stall / Store Owner account."""

    email = forms.EmailField(required=True)
    mobile_number = forms.CharField(max_length=16, required=True, label="Mobile Number")

    class Meta:
        model = User
        fields = ["username", "email", "mobile_number", "password1", "password2"]

    def clean_email(self):
        email = self.cleaned_data["email"].lower().strip()
        if User.objects.filter(email__iexact=email).exists():
            raise ValidationError("An account already exists with this email address.")
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"]
        user.mobile_number = self.cleaned_data["mobile_number"]
        user.role = User.Role.OWNER
        if commit:
            user.save()
            OwnerProfile.objects.create(user=user)
        return user


class CustomerProfileUpdateForm(forms.ModelForm):
    class Meta:
        model = CustomerProfile
        fields = ["address", "province", "pincode", "country"]
