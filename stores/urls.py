from django.urls import path

from . import views

app_name = "stores"

urlpatterns = [
    # Public
    path("stores/", views.store_list, name="store_list"),
    path("store/<slug:slug>/", views.store_detail, name="store_detail"),
    path("contact-us/", views.contact_us, name="contact_us"),

    # Owner area
    path("owner/dashboard/", views.owner_dashboard, name="owner_dashboard"),
    path("owner/store/create/", views.create_store, name="create_store"),
    path("owner/store/<slug:slug>/edit/", views.edit_store, name="edit_store"),
    path("owner/store/<slug:slug>/hours/", views.edit_operating_hours, name="edit_operating_hours"),
    path("owner/store/<slug:slug>/toggle-active/", views.toggle_store_active, name="toggle_store_active"),

    path("owner/store/<slug:slug>/categories/", views.category_list, name="category_list"),
    path("owner/store/<slug:slug>/categories/<int:pk>/delete/", views.category_delete, name="category_delete"),
    path("owner/store/<slug:slug>/categories/<int:pk>/edit/", views.category_edit, name="category_edit"),

    
    path("owner/store/<slug:slug>/items/", views.item_list, name="item_list"),
    path("owner/store/<slug:slug>/items/create/", views.item_create, name="item_create"),
    path("owner/store/<slug:slug>/items/<int:pk>/edit/", views.item_edit, name="item_edit"),
    path("owner/store/<slug:slug>/items/<int:pk>/delete/", views.item_delete, name="item_delete"),
    path("notifications/", views.notifications, name="notifications"),
    path("notifications/<int:pk>/read/", views.mark_notification_read, name="mark_notification_read"),
    path("notifications/read-all/", views.mark_all_notifications_read, name="mark_all_notifications_read"),
    path("notifications/count/", views.notification_count_api, name="notification_count_api"),
]
