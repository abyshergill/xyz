import logging

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.views import LoginView
from django.shortcuts import redirect, render
from django.urls import reverse_lazy, reverse
from django.views import View
from django.views.generic import CreateView
from django.shortcuts import get_object_or_404, redirect
from django.contrib.auth import logout as auth_logout
from django.views.decorators.http import require_http_methods
from django.contrib.auth import update_session_auth_hash
from django.http import HttpResponseRedirect
from django.views.decorators.csrf import csrf_exempt

from .forms import (
    CustomerAddressForm,
    CustomerProfileForm,
    CustomerRegistrationForm,
    EmailOrUsernameAuthenticationForm,
    OwnerRegistrationForm,
    UsernameUpdateForm,
    ChangePasswordForm,
)

from .models import CustomerAddress, User
from .throttling import LOCKOUT_SECONDS, clear_attempts, get_client_ip, is_locked_out, register_failed_attempt

logger = logging.getLogger("accounts")


class RoleAwareLoginView(LoginView):
    """
    Standard Django authentication login with brute-force protection.

    Explicitly uses Django's ModelBackend for normal username/email + password
    authentication so Django knows which authentication backend to use when
    multiple backends (Django + django-allauth) are configured.
    """

    template_name = "accounts/login.html"
    redirect_authenticated_user = True
    authentication_form = EmailOrUsernameAuthenticationForm

    def dispatch(self, request, *args, **kwargs):
        """
        Brute-force lockout is currently disabled for development.

        Uncomment/restore the lockout block when deploying to production.
        """

        if request.method == "POST":
            username = request.POST.get("username", "")

            if is_locked_out(request, username):
                logger.warning(
                    "Blocked login attempt due to brute-force lockout: ip=%s username=%s",
                    get_client_ip(request),
                    username,
                )

                messages.error(
                    request,
                    f"Too many failed login attempts. Please wait "
                    f"{LOCKOUT_SECONDS // 60} minutes and try again.",
                )

                return render(
                    request,
                    self.template_name,
                    {
                        "form": EmailOrUsernameAuthenticationForm(
                            request=request
                        )
                    },
                    status=429,
                )

        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        """
        Successfully authenticate and log in the user.

        Explicitly specify Django's ModelBackend because the project
        has multiple authentication backends, including django-allauth.
        """

        user = form.get_user()

        # Explicitly set the authentication backend for normal login.
        login(
            self.request,
            user,
            backend="django.contrib.auth.backends.ModelBackend",
        )

        clear_attempts(self.request, user.username)

        logger.info(
            "Successful login: user=%s",
            user.username,
        )

        return HttpResponseRedirect(self.get_success_url())

    def form_invalid(self, form):
        username = self.request.POST.get("username", "")

        account_attempts, ip_attempts = register_failed_attempt(
            self.request,
            username,
        )

        logger.warning(
            "Failed login attempt: username=%s ip=%s account_attempts=%d ip_attempts=%d",
            username,
            get_client_ip(self.request),
            account_attempts,
            ip_attempts,
        )

        return super().form_invalid(form)


class CustomerRegisterView(CreateView):
    form_class = CustomerRegistrationForm
    template_name = "accounts/register_customer.html"
    success_url = reverse_lazy("accounts:login")

    def form_valid(self, form):
        response = super().form_valid(form)
        # Auto-login the customer after signup
        login(self.request, form.instance, backend="django.contrib.auth.backends.ModelBackend")
        messages.success(self.request, "Welcome! Your account has been created.")
        logger.info("New customer registered: %s", form.instance.username)
        return redirect("accounts:profile")


class OwnerRegisterView(CreateView):
    form_class = OwnerRegistrationForm
    template_name = "accounts/register_owner.html"
    success_url = reverse_lazy("stores:create_store")

    def form_valid(self, form):
        response = super().form_valid(form)
        login(self.request, form.instance,backend="django.contrib.auth.backends.ModelBackend" )
        messages.success(self.request, "Owner account created. Now set up your store.")
        logger.info("New store owner registered: %s", form.instance.username)
        return response


@login_required
def dashboard_redirect(request):
    """Sends a freshly logged-in user to the right dashboard for their role."""
    user = request.user
    if user.is_admin_role:
        return redirect("platform_admin:dashboard")
    if user.is_owner_role:
        return redirect("stores:owner_dashboard")
    return redirect("stores:store_list")

@require_http_methods(["GET", "POST"])
def custom_logout(request):
    """
    Handles both GET and POST logout requests.
    Django 6.x LogoutView only accepts POST, which causes 405 errors
    if a user navigates to the logout URL directly (bookmark, back button).
    This view accepts both methods for a smoother experience.
    """
    auth_logout(request)
    messages.success(request, "You have been logged out successfully.")
    return redirect("accounts:login")


# ---------------------------------------------------------------------------
# Customer profile and address management
# ---------------------------------------------------------------------------

@login_required
def customer_profile(request):
    """Customer edits their name, phone, and manages saved addresses."""
    if not request.user.is_customer_role:
        return redirect("accounts:dashboard_redirect")

    if request.method == "POST":
        profile_form = CustomerProfileForm(request.POST, instance=request.user)
        if profile_form.is_valid():
            profile_form.save()
            messages.success(request, "Profile updated.")
            return redirect("accounts:profile")
    else:
        profile_form = CustomerProfileForm(instance=request.user)

    addresses = request.user.addresses.all()
    address_form = CustomerAddressForm()

    return render(request, "accounts/profile.html", {
        "profile_form": profile_form,
        "addresses": addresses,
        "address_form": address_form,
    })


@login_required
def add_address(request):
    """Add a new saved address."""
    if not request.user.is_customer_role:
        return redirect("accounts:dashboard_redirect")

    if request.method == "POST":
        form = CustomerAddressForm(request.POST)
        if form.is_valid():
            address = form.save(commit=False)
            address.user = request.user
            address.save()
            # If marked as default, unset others
            if address.is_default:
                #request.user.addresss.exclude(pk=address.pk).update(is_default=False)
                request.user.addresses.exclude(pk=address.pk).update(is_default=False)
            messages.success(request, "Address added.")
    return redirect("accounts:profile")


@login_required
def edit_address(request, pk):
    """Edit an existing saved address."""
    if not request.user.is_customer_role:
        return redirect("accounts:dashboard_redirect")

    address = get_object_or_404(CustomerAddress, pk=pk, user=request.user)
    if request.method == "POST":
        form = CustomerAddressForm(request.POST, instance=address)
        if form.is_valid():
            updated = form.save(commit=False)
            updated.user = request.user
            updated.save()
            if updated.is_default:
                request.user.addresses.exclude(pk=updated.pk).update(is_default=False)
            messages.success(request, "Address updated.")
            return redirect("accounts:profile")
    else:
        form = CustomerAddressForm(instance=address)

    return render(request, "accounts/edit_address.html", {
        "form": form, "address": address,
    })


@login_required
def delete_address(request, pk):
    """Delete a saved address."""
    if not request.user.is_customer_role:
        return redirect("accounts:dashboard_redirect")

    address = get_object_or_404(CustomerAddress, pk=pk, user=request.user)
    address.delete()
    messages.success(request, "Address deleted.")
    return redirect("accounts:profile")

# ---------------------------------------------------------------------------
# Username and password management
# ---------------------------------------------------------------------------

@login_required
def change_username(request):
    """Let a customer or owner set or change their username."""
    if request.method == "POST":
        form = UsernameUpdateForm(request.POST, user=request.user)
        if form.is_valid():
            request.user.username = form.cleaned_data["username"]
            request.user.save(update_fields=["username"])
            messages.success(request, "Username updated. You can now login with this username or your email.")
            return redirect("accounts:profile")
    else:
        form = UsernameUpdateForm(user=request.user)

    return render(request, "accounts/change_username.html", {
        "form": form,
        "current_username": request.user.username,
    })

@login_required
def change_password(request):
    if request.method == "POST":
        form = ChangePasswordForm(request.POST, user=request.user)
        if form.is_valid():
            form.save()
            update_session_auth_hash(request, request.user)
            messages.success(request, "Your password has been changed successfully.")
            return redirect("accounts:profile")
    else:
        form = ChangePasswordForm(user=request.user)

    return render(request, "accounts/change_password.html", {"form": form})

@csrf_exempt
@require_http_methods(["POST"])
def google_login_as_customer(request):
    """
    Start Google OAuth while remembering that this user selected
    the Customer role.
    """
    request.session["user_role"] = User.Role.CUSTOMER

    return redirect("/accounts/google/login/")

@csrf_exempt
@require_http_methods(["POST"])
def google_login_as_shop_owner(request):
    """
    Start Google OAuth while remembering that this user selected
    the Shop Owner role.
    """
    request.session["user_role"] = User.Role.OWNER

    return redirect("/accounts/google/login/")
