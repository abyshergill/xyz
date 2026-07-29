from django.urls import path

from . import views

app_name = "analytics"

urlpatterns = [
    path("owner/analytics/", views.owner_analytics_dashboard, name="owner_dashboard"),
]
