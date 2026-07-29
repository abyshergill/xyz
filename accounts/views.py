import logging

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.views import LoginView
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import CreateView

from .forms import CustomerRegistrationForm, OwnerRegistrationForm
from .models import User
from .throttling import LOCKOUT_SECONDS, clear_attempts, get_client_ip, is_locked_out, register_failed_attempt

logger = logging.getLogger("accounts")


class RoleAwareLoginView(LoginView):
    """
    Standard Django auth login, hardened against brute-force / credential-
    stuffing attacks (see accounts/throttling.py). Django's
    AuthenticationForm already protects against username enumeration
    timing differences and applies password hashing verification via
    check_password (constant-time comparison); the lockout below adds
    protection against repeated automated guessing.
    """

    template_name = "accounts/login.html"
    redirect_authenticated_user = True

    def dispatch(self, request, *args, **kwargs):
        if request.method == "POST":
            username = request.POST.get("username", "")
            if is_locked_out(request, username):
                logger.warning(
                    "Blocked login attempt due to brute-force lockout: ip=%s username=%s",
                    get_client_ip(request), username,
                )
                messages.error(
                    request,
                    f"Too many failed login attempts. Please wait {LOCKOUT_SECONDS // 60} minutes and try again.",
                )
                return render(request, self.template_name, {"form": AuthenticationForm(request)}, status=429)
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        response = super().form_valid(form)
        clear_attempts(self.request, form.get_user().username)
        logger.info("Successful login: user=%s", form.get_user().username)
        return response

    def form_invalid(self, form):
        username = self.request.POST.get("username", "")
        account_attempts, ip_attempts = register_failed_attempt(self.request, username)
        logger.warning(
            "Failed login attempt: username=%s ip=%s account_attempts=%d ip_attempts=%d",
            username, get_client_ip(self.request), account_attempts, ip_attempts,
        )
        return super().form_invalid(form)


class CustomerRegisterView(CreateView):
    form_class = CustomerRegistrationForm
    template_name = "accounts/register_customer.html"
    success_url = reverse_lazy("accounts:login")

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, "Account created. You can now log in.")
        logger.info("New customer registered: %s", form.instance.username)
        return response


class OwnerRegisterView(CreateView):
    form_class = OwnerRegistrationForm
    template_name = "accounts/register_owner.html"
    success_url = reverse_lazy("stores:create_store")

    def form_valid(self, form):
        response = super().form_valid(form)
        login(self.request, form.instance)
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
