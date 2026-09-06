from django.urls import path
from . import views

app_name = "accounts"

urlpatterns = [
    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------
    path("login/", views.RoleAwareLoginView.as_view(), name="login"),
    path("logout/", views.custom_logout, name="logout"),

    # Google login with role selection
    path(
        "login/customer/",
        views.google_login_as_customer,
        name="login_customer",
    ),
    path(
        "login/shop-owner/",
        views.google_login_as_shop_owner,
        name="login_shop_owner",
    ),

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------
    path(
        "register/customer/",
        views.CustomerRegisterView.as_view(),
        name="register_customer",
    ),
    path(
        "register/owner/",
        views.OwnerRegisterView.as_view(),
        name="register_owner",
    ),

    # ------------------------------------------------------------------
    # Role-aware dashboard
    # ------------------------------------------------------------------
    path(
        "dashboard/",
        views.dashboard_redirect,
        name="dashboard_redirect",
    ),

    # ------------------------------------------------------------------
    # Customer profile
    # ------------------------------------------------------------------
    path(
        "profile/",
        views.customer_profile,
        name="profile",
    ),

    path(
        "profile/address/add/",
        views.add_address,
        name="add_address",
    ),

    path(
        "profile/address/<int:pk>/edit/",
        views.edit_address,
        name="edit_address",
    ),

    path(
        "profile/address/<int:pk>/delete/",
        views.delete_address,
        name="delete_address",
    ),

    # ------------------------------------------------------------------
    # Account settings
    # ------------------------------------------------------------------
    path(
        "profile/username/",
        views.change_username,
        name="change_username",
    ),

    path(
        "profile/password/",
        views.change_password,
        name="change_password",
    ),
]
