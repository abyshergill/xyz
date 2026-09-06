from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import get_user_model
from django.contrib.auth import password_validation
from django.contrib.auth.forms import AuthenticationForm as DjangoAuthForm
from django.core.exceptions import ValidationError

from .models import CustomerProfile, OwnerProfile, User, CustomerAddress


class EmailOrUsernameAuthenticationForm(DjangoAuthForm):
    """
    Allows login with either username OR email address.
    Django's default AuthenticationForm only checks the username field.
    """

    def clean(self):
        username = self.cleaned_data.get("username", "").strip()
        password = self.cleaned_data["password"]

        UserModel = get_user_model()

        # Try by username first
        user = UserModel.objects.filter(username=username).first()

        # If not found, try by email
        if not user:
            user = UserModel.objects.filter(email__iexact=username).first()

        if user and user.check_password(password):
            self.user_cache = user
            self.confirm_login_allowed(user)
            return self.cleaned_data
        elif user:
            # User found but password wrong
            pass

        # Fall back to Django's default behavior (will show error)
        return super().clean()

class CustomerRegistrationForm(UserCreationForm):
    """
    Simplified customer signup: Name, Email, Password, Confirm Password, Phone.
    No address required at signup — customers add addresses later from their profile.
    """
    email = forms.EmailField(required=True, widget=forms.EmailInput(attrs={
        "placeholder": "your@email.com",
        "class": "w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-orange-500 focus:border-orange-500 outline-none",
    }))
    full_name = forms.CharField(max_length=150, required=True, label="Full Name", widget=forms.TextInput(attrs={
        "placeholder": "John Doe",
        "class": "w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-orange-500 focus:border-orange-500 outline-none",
    }))
    mobile_number = forms.CharField(max_length=16, required=True, label="Phone Number", widget=forms.TextInput(attrs={
        "placeholder": "+66 2 123 4567",
        "class": "w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-orange-500 focus:border-orange-500 outline-none",
    }))

    class Meta:
        model = User
        fields = ["full_name", "email", "mobile_number", "password1", "password2"]

    def clean_email(self):
        email = self.cleaned_data["email"].lower().strip()
        if User.objects.filter(email__iexact=email).exists():
            raise ValidationError("An account already exists with this email address.")
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"]
        user.full_name = self.cleaned_data["full_name"]
        user.mobile_number = self.cleaned_data["mobile_number"]
        user.role = User.Role.CUSTOMER
        # Use email as initial username (customer can change later)
        # Check for existing username to avoid collision
        base_username = self.cleaned_data["email"]
        username = base_username
        counter = 1
        while User.objects.filter(username__iexact=username).exclude(pk=user.pk).exists():
            username = f"{base_username}_{counter}"
            counter += 1
        user.username = username
        if commit:
            user.save()
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

class CustomerProfileForm(forms.ModelForm):
    """Edit customer name and phone."""
    class Meta:
        model = User
        fields = ["full_name", "mobile_number"]
        widgets = {
            "full_name": forms.TextInput(attrs={
                "class": "w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-orange-500 focus:border-orange-500 outline-none",
            }),
            "mobile_number": forms.TextInput(attrs={
                "class": "w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-orange-500 focus:border-orange-500 outline-none",
            }),
        }


class CustomerAddressForm(forms.ModelForm):
    """Add or edit a saved customer address."""
    class Meta:
        model = CustomerAddress
        fields = ["alias", "full_name", "address", "pincode", "phone_number", "is_default"]
        widgets = {
            "alias": forms.Select(attrs={
                "class": "w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-orange-500 focus:border-orange-500 outline-none",
            }),
            "full_name": forms.TextInput(attrs={
                "placeholder": "Recipient name (optional)",
                "class": "w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-orange-500 focus:border-orange-500 outline-none",
            }),
            "address": forms.TextInput(attrs={
                "placeholder": "Full street address",
                "class": "w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-orange-500 focus:border-orange-500 outline-none",
            }),
            "pincode": forms.TextInput(attrs={
                "placeholder": "Pincode / Postal code",
                "class": "w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-orange-500 focus:border-orange-500 outline-none",
            }),
            "phone_number": forms.TextInput(attrs={
                "placeholder": "Phone for this address",
                "class": "w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-orange-500 focus:border-orange-500 outline-none",
            }),
        }

class UsernameUpdateForm(forms.Form):
    """Lets a customer set or change their username after first login."""
    username = forms.CharField(
        max_length=150, required=True, label="New Username",
        widget=forms.TextInput(attrs={
            "placeholder": "Choose a username (e.g. john_doe)",
            "class": "w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-orange-500 focus:border-orange-500 outline-none",
        }),
        help_text="You can use this username or your email to log in.",
    )

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

    def clean_username(self):
        username = self.cleaned_data["username"].strip()
        # Check if username is taken by another user
        if User.objects.filter(username__iexact=username).exclude(pk=self.user.pk if self.user else None).exists():
            raise ValidationError("This username is already taken. Please choose another.")
        return username


# class CustomPasswordChangeForm(forms.Form):
#     """
#     Change password: old password → new password → confirm new password.
#     Works for both customers and owners.
#     """
#     old_password = forms.CharField(
#         label="Current Password",
#         widget=forms.PasswordInput(attrs={
#             "class": "w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-orange-500 focus:border-orange-500 outline-none",
#         }),
#     )
#     new_password1 = forms.CharField(
#         label="New Password",
#         widget=forms.PasswordInput(attrs={
#             "class": "w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-orange-500 focus:border-orange-500 outline-none",
#         }),
#     )
#     new_password2 = forms.CharField(
#         label="Confirm New Password",
#         widget=forms.PasswordInput(attrs={
#             "class": "w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-orange-500 focus:border-orange-500 outline-none",
#         }),
#     )

#     def __init__(self, *args, user=None, **kwargs):
#         super().__init__(*args, **kwargs)
#         self.user = user

#     def clean_old_password(self):
#         old_password = self.cleaned_data.get("old_password", "")
#         if not self.user or not self.user.check_password(old_password):
#             raise ValidationError("Your current password is incorrect.")
#         return old_password

#     def clean_new_password2(self):
#         pw1 = self.cleaned_data.get("new_password1", "")
#         pw2 = self.cleaned_data.get("new_password2", "")
#         if pw1 and pw2 and pw1 != pw2:
#             raise ValidationError("The new passwords do not match.")
#         return pw2

#     def save(self):
#         self.user.set_password(self.cleaned_data["new_password1"])
#         self.user.save()
#         return self.user



class ChangePasswordForm(forms.Form):
    """Password change form that enforces the same rules as registration."""
    old_password = forms.CharField(
        label="Current Password",
        widget=forms.PasswordInput(attrs={
            "class": "w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-orange-500 focus:border-orange-500 outline-none",
            "autocomplete": "current-password",
        }),
    )
    new_password1 = forms.CharField(
        label="New Password",
        widget=forms.PasswordInput(attrs={
            "class": "w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-orange-500 focus:border-orange-500 outline-none",
            "autocomplete": "new-password",
        }),
    )
    new_password2 = forms.CharField(
        label="Confirm New Password",
        widget=forms.PasswordInput(attrs={
            "class": "w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-orange-500 focus:border-orange-500 outline-none",
            "autocomplete": "new-password",
        }),
    )

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

    def clean_old_password(self):
        """Verify the current password is correct."""
        old_password = self.cleaned_data.get("old_password", "")
        if not self.user or not self.user.check_password(old_password):
            raise ValidationError("Your current password is incorrect.")
        return old_password

    def clean_new_password1(self):
        """Enforce all Django password validators (same as registration)."""
        new_password = self.cleaned_data.get("new_password1", "")
        # This runs ALL validators from AUTH_PASSWORD_VALIDATORS in settings.py:
        # - UserAttributeSimilarityValidator: not too similar to name/email
        # - MinimumLengthValidator: at least 9 characters
        # - CommonPasswordValidator: not a commonly used password
        # - NumericPasswordValidator: not entirely numeric
        password_validation.validate_password(new_password, user=self.user)
        return new_password

    def clean_new_password2(self):
        """Verify both new passwords match."""
        password1 = self.cleaned_data.get("new_password1", "")
        password2 = self.cleaned_data.get("new_password2", "")
        if password1 and password2 and password1 != password2:
            raise ValidationError("The two password fields didn't match.")
        return password2

    def save(self):
        """Change the password and keep the user logged in."""
        new_password = self.cleaned_data["new_password1"]
        self.user.set_password(new_password)
        self.user.save()
        return self.user
