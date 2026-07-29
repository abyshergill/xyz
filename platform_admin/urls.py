from django.urls import path

from . import views

app_name = "platform_admin"

urlpatterns = [
    path("dashboard/", views.dashboard, name="dashboard"),
]
