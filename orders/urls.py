from django.urls import path

from . import views

app_name = "orders"

urlpatterns = [
    path("store/<slug:slug>/cart/add/", views.add_to_cart, name="add_to_cart"),
    path("store/<slug:slug>/cart/remove/", views.remove_from_cart, name="remove_from_cart"),
    path("store/<slug:slug>/checkout/", views.checkout, name="checkout"),
    path("order/<str:order_number>/confirmation/", views.order_confirmation, name="order_confirmation"),
    path("order/<str:order_number>/bill/", views.order_bill, name="order_bill"),
    path("track-order/", views.track_order, name="track_order"),
    path("my-orders/", views.my_orders, name="my_orders"),

    path("owner/orders/", views.order_list, name="order_list"),
    path("owner/orders/merge/", views.order_merge, name="order_merge"),
    path("owner/orders/<str:order_number>/", views.order_detail, name="order_detail"),
    path("owner/orders/<str:order_number>/status/", views.order_update_status, name="order_update_status"),
    path("owner/orders/<str:order_number>/delete/", views.order_delete, name="order_delete"),
]
