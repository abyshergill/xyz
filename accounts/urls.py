from django.contrib.auth.views import LogoutView
from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("login/", views.RoleAwareLoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("register/customer/", views.CustomerRegisterView.as_view(), name="register_customer"),
    path("register/owner/", views.OwnerRegisterView.as_view(), name="register_owner"),
    path("dashboard/", views.dashboard_redirect, name="dashboard_redirect"),
]
