import json
import logging
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_http_methods

from stores.models import FoodItem, Store

from .forms import CheckoutContactForm, OrderMergeForm, OrderTrackingForm
from .models import Order
from .services import OrderMergeError, create_order_with_items, generate_order_bill_pdf, merge_orders

logger = logging.getLogger("orders")


def _require_owner_of(request, store):
    if store.owner_id != request.user.id:
        logger.warning(
            "Blocked cross-tenant order access: user=%s store=%s", request.user.username, store.pk
        )
        raise PermissionDenied("You do not manage this store.")


# ---------------------------------------------------------------------------
# Customer-facing checkout
# ---------------------------------------------------------------------------

@require_http_methods(["GET", "POST"])
def checkout(request, slug):
    store = get_object_or_404(Store, slug=slug, is_active=True)

    if not store.is_open_now():
        messages.error(request, f"{store.name} is currently closed and cannot accept orders.")
        return redirect("stores:store_detail", slug=slug)

    cart_raw = request.session.get(f"cart_{store.slug}", {})
    if not cart_raw:
        messages.error(request, "Your cart is empty.")
        return redirect("stores:store_detail", slug=slug)

    # Build display-ready cart lines (image, price, line total). Any stale
    # entry pointing at an item that no longer exists is silently dropped
    # from the session cart rather than erroring the whole page out.
    cart_lines = []
    subtotal = Decimal("0")
    stale_ids = []
    for food_item_id_str, quantity in cart_raw.items():
        item = FoodItem.objects.filter(pk=food_item_id_str, store=store).first()
        if not item:
            stale_ids.append(food_item_id_str)
            continue
        line_total = item.price * quantity
        subtotal += line_total
        cart_lines.append({"item": item, "quantity": quantity, "line_total": line_total})

    if stale_ids:
        for sid in stale_ids:
            cart_raw.pop(sid, None)
        request.session[f"cart_{store.slug}"] = cart_raw
        request.session.modified = True

    if not cart_lines:
        messages.error(request, "Your cart is empty.")
        return redirect("stores:store_detail", slug=slug)

    tax_total = Decimal("0")
    for tax in store.tax_configurations.filter(is_active=True):
        tax_total += tax.apply(subtotal)
    estimated_total = subtotal + tax_total

    if request.method == "POST":
        form = CheckoutContactForm(request.POST, store=store)
        if form.is_valid():
            cart_rows = []
            try:
                for food_item_id_str, quantity in cart_raw.items():
                    # Every food item is re-fetched scoped to THIS store, so a
                    # tampered cart referencing another store's item id can
                    # never be checked out here (IDOR-safe).
                    item = get_object_or_404(FoodItem, pk=int(food_item_id_str), store=store)
                    cart_rows.append({"food_item": item, "quantity": int(quantity)})

                customer = request.user if request.user.is_authenticated else None
                order = create_order_with_items(
                    store=store,
                    cart_rows=cart_rows,
                    customer=customer,
                    contact_fields={
                        "table_number": form.cleaned_data.get("table_number", ""),
                        "contact_phone": form.cleaned_data.get("contact_phone", ""),
                        "contact_email": form.cleaned_data.get("contact_email", ""),
                    },
                )
            except OrderMergeError as exc:  # reused as generic "stock" error type
                messages.error(request, str(exc))
                return redirect("stores:store_detail", slug=slug)

            del request.session[f"cart_{store.slug}"]
            request.session.modified = True
            logger.info("Order placed: %s at store=%s", order.order_number, store.slug)
            messages.success(request, f"Order placed! Your order number is {order.order_number}.")
            return redirect("orders:order_confirmation", order_number=order.order_number)
    else:
        form = CheckoutContactForm(store=store)

    return render(request, "orders/checkout.html", {
        "store": store, "form": form, "cart_lines": cart_lines,
        "subtotal": subtotal, "tax_total": tax_total, "estimated_total": estimated_total,
    })


@require_http_methods(["POST"])
def remove_from_cart(request, slug):
    store = get_object_or_404(Store, slug=slug, is_active=True)
    food_item_id = request.POST.get("food_item_id", "")
    cart_key = f"cart_{store.slug}"
    cart = request.session.get(cart_key, {})
    if food_item_id in cart:
        del cart[food_item_id]
        request.session[cart_key] = cart
        request.session.modified = True
        messages.success(request, "Item removed from your cart.")
    if cart:
        return redirect("orders:checkout", slug=store.slug)
    return redirect("stores:store_detail", slug=store.slug)


@require_http_methods(["POST"])
def add_to_cart(request, slug):
    """Session-based cart -- no DB write until checkout is confirmed."""
    store = get_object_or_404(Store, slug=slug, is_active=True)
    item = get_object_or_404(FoodItem, pk=request.POST.get("food_item_id"), store=store)
    quantity = max(1, min(99, int(request.POST.get("quantity", 1))))

    if not item.in_stock:
        messages.error(request, f"'{item.name}' is currently unavailable.")
        return redirect("stores:store_detail", slug=slug)

    cart_key = f"cart_{store.slug}"
    cart = request.session.get(cart_key, {})
    cart[str(item.pk)] = cart.get(str(item.pk), 0) + quantity
    request.session[cart_key] = cart
    request.session.modified = True
    messages.success(request, f"Added {item.name} to your cart.")
    return redirect("stores:store_detail", slug=slug)


def order_confirmation(request, order_number):
    order = get_object_or_404(Order, order_number=order_number)
    return render(request, "orders/order_confirmation.html", {"order": order})


def order_bill(request, order_number):
    """
    Downloadable PDF receipt. Publicly accessible by order_number (matching
    order_confirmation's access model) since checkout supports guest
    customers with no account to log into. Order numbers are generated from
    a random UUID and are not sequential/guessable.
    """
    order = get_object_or_404(Order, order_number=order_number)
    pdf_bytes = generate_order_bill_pdf(order)
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="receipt_{order.order_number}.pdf"'
    return response


def track_order(request):
    """
    Public order-status lookup for customers (guest or logged-in): order
    number plus one piece of checkout-time verification info (phone, email,
    or table number), so a stranger can't browse arbitrary order numbers.
    """
    order = None
    if request.method == "POST":
        form = OrderTrackingForm(request.POST)
        if form.is_valid():
            order_number = form.cleaned_data["order_number"].strip().upper()
            verification = form.cleaned_data["verification"].strip().lower()
            candidate = Order.objects.filter(order_number=order_number).first()
            if candidate and verification in {
                (candidate.contact_phone or "").strip().lower(),
                (candidate.contact_email or "").strip().lower(),
                (candidate.table_number or "").strip().lower(),
            } and verification:
                order = candidate
            else:
                messages.error(request, "We couldn't find a matching order. Double-check the order number and the phone/email/table number you used at checkout.")
    else:
        form = OrderTrackingForm()

    return render(request, "orders/track_order.html", {"form": form, "order": order})


@login_required
def my_orders(request):
    """A logged-in customer's own order history, across all stores."""
    orders = Order.objects.filter(customer=request.user, merged_into__isnull=True).select_related("store").order_by("-created_at")
    return render(request, "orders/my_orders.html", {"orders": orders})


# ---------------------------------------------------------------------------
# Owner order management
# ---------------------------------------------------------------------------

@login_required
def order_list(request):
    store = request.user.stores.first()
    if not store:
        return redirect("stores:create_store")

    status_filter = request.GET.get("status", "")
    date_from = request.GET.get("date_from", "")
    date_to = request.GET.get("date_to", "")
    min_total = request.GET.get("min_total", "")
    max_total = request.GET.get("max_total", "")
    sort = request.GET.get("sort", "-created_at")

    orders = store.orders.filter(merged_into__isnull=True).select_related("customer").prefetch_related("items")

    if status_filter:
        orders = orders.filter(status=status_filter)

    if date_from:
        parsed_from = parse_date(date_from)
        if parsed_from:
            orders = orders.filter(created_at__date__gte=parsed_from)
        else:
            messages.error(request, "'From' date was not understood and was ignored.")

    if date_to:
        parsed_to = parse_date(date_to)
        if parsed_to:
            orders = orders.filter(created_at__date__lte=parsed_to)
        else:
            messages.error(request, "'To' date was not understood and was ignored.")

    if min_total:
        try:
            orders = orders.filter(grand_total__gte=Decimal(min_total))
        except (InvalidOperation, ValueError):
            messages.error(request, "Minimum total was not a valid number and was ignored.")

    if max_total:
        try:
            orders = orders.filter(grand_total__lte=Decimal(max_total))
        except (InvalidOperation, ValueError):
            messages.error(request, "Maximum total was not a valid number and was ignored.")

    # Whitelist sort options to prevent arbitrary field ordering via query params.
    allowed_sorts = {
        "-created_at": "Newest first", "created_at": "Oldest first",
        "-grand_total": "Total: high to low", "grand_total": "Total: low to high",
    }
    if sort not in allowed_sorts:
        sort = "-created_at"
    orders = orders.order_by(sort)

    return render(request, "orders/order_list.html", {
        "store": store, "orders": orders, "status_choices": Order.Status.choices, "status_filter": status_filter,
        "date_from": date_from, "date_to": date_to, "min_total": min_total, "max_total": max_total,
        "sort": sort, "sort_choices": allowed_sorts,
    })


@login_required
def order_detail(request, order_number):
    order = get_object_or_404(Order, order_number=order_number)
    _require_owner_of(request, order.store)
    child_orders = order.merged_orders.all() if order.is_master else []
    return render(request, "orders/order_detail.html", {"order": order, "child_orders": child_orders})


@login_required
@require_http_methods(["POST"])
def order_update_status(request, order_number):
    order = get_object_or_404(Order, order_number=order_number)
    _require_owner_of(request, order.store)

    new_status = request.POST.get("status")
    valid_statuses = dict(Order.Status.choices)
    if new_status not in valid_statuses:
        messages.error(request, "Invalid status.")
        return redirect("orders:order_detail", order_number=order_number)

    order.status = new_status
    order.save(update_fields=["status", "updated_at"])
    logger.info("Order %s status -> %s by %s", order.order_number, new_status, request.user.username)
    messages.success(request, f"Order marked as {valid_statuses[new_status]}.")
    return redirect("orders:order_detail", order_number=order_number)


@login_required
@require_http_methods(["POST"])
def order_delete(request, order_number):
    order = get_object_or_404(Order, order_number=order_number)
    _require_owner_of(request, order.store)
    order.delete()
    messages.success(request, "Order deleted.")
    return redirect("orders:order_list")


@login_required
def order_merge(request):
    store = request.user.stores.first()
    if not store:
        return redirect("stores:create_store")

    if request.method == "POST":
        form = OrderMergeForm(request.POST, store=store)
        if form.is_valid():
            try:
                master = merge_orders(form.cleaned_data["orders_to_merge"], initiating_owner=request.user)
            except OrderMergeError as exc:
                messages.error(request, str(exc))
                return redirect("orders:order_merge")
            logger.info("Orders merged into master %s by %s", master.order_number, request.user.username)
            messages.success(request, f"Orders merged into master ticket {master.order_number}.")
            return redirect("orders:order_detail", order_number=master.order_number)
    else:
        form = OrderMergeForm(store=store)

    return render(request, "orders/order_merge.html", {"store": store, "form": form})
