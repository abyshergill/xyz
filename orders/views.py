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
from django.http import HttpResponse, JsonResponse

from stores.models import FoodItem, Store

from .forms import CheckoutContactForm, ManualOrderForm, ManualOrderItemForm, OrderEditForm, OrderMergeForm, OrderTrackingForm
from .models import Order, OrderItem
from stores.models import Notification
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

    if not store.is_open_now() and not store.accept_orders_when_closed:
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
    tax_total = Decimal("0")
    stale_ids = []
    for food_item_id_str, quantity in cart_raw.items():
        item = FoodItem.objects.filter(pk=food_item_id_str, store=store).first()
        if not item:
            stale_ids.append(food_item_id_str)
            continue
        line_base = item.price * quantity
        tax_rate = getattr(item, 'tax_percentage', 0) or 0
        line_tax = (line_base * tax_rate) / 100
       # line_tax = (line_base * (item.tax_percentage or 0)) / 100
        line_total_with_tax = line_base + line_tax
        subtotal += line_base
        tax_total += line_tax
        cart_lines.append({
            "item": item,
            "quantity": quantity,
            "line_total": line_base,
            "line_tax": line_tax,
            "line_total_with_tax": line_total_with_tax,
        })
    if stale_ids:
        for sid in stale_ids:
            cart_raw.pop(sid, None)
        request.session[f"cart_{store.slug}"] = cart_raw
        request.session.modified = True

    if not cart_lines:
        messages.error(request, "Your cart is empty.")
        return redirect("stores:store_detail", slug=slug)

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
                    "customer_name": form.cleaned_data.get("customer_name", ""),
                    "customer_address": form.cleaned_data.get("customer_address", ""),
                    "table_number": form.cleaned_data.get("table_number", ""),
                    "contact_phone": form.cleaned_data.get("contact_phone", ""),
                    "contact_email": form.cleaned_data.get("contact_email", ""),
                    "remarks": form.cleaned_data.get("remarks", ""),
                },
                )
            except OrderMergeError as exc:  # reused as generic "stock" error type
                messages.error(request, str(exc))
                return redirect("stores:store_detail", slug=slug)

            del request.session[f"cart_{store.slug}"]
            request.session.modified = True

            # Notify the store owner about the new order
            Notification.objects.create(
                user=store.owner,
                notification_type=Notification.Type.NEW_ORDER,
                title=f"New order: {order.order_number}",
                message=f"Order {order.order_number} has been placed with {order.items.count()} items. Total: {order.grand_total}",
                order=order,
            )

            logger.info("Order placed: %s at store=%s", order.order_number, store.slug)
            messages.success(request, f"Order placed! Your order number is {order.order_number}.")
            return redirect("orders:order_confirmation", order_number=order.order_number)

    else:
        # Pre-fill form for logged-in customers
        initial_data = {}
        if request.user.is_authenticated and request.user.is_customer_role:
            initial_data = {
                "customer_name": request.user.full_name or request.user.username,
                "contact_phone": request.user.mobile_number or "",
                "contact_email": request.user.email or "",
            }
        form = CheckoutContactForm(store=store, initial=initial_data)

    # Pass saved addresses for logged-in customers
    saved_addresses = []
    if request.user.is_authenticated and request.user.is_customer_role:
        saved_addresses = request.user.addresses.all()

    return render(request, "orders/checkout.html", {
        "store": store, "form": form, "cart_lines": cart_lines,
        "subtotal": subtotal, "tax_total": tax_total, "estimated_total": estimated_total,
        "saved_addresses": saved_addresses,
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
    """Session-based cart -- no DB write until checkout is confirmed.
    Returns JSON for AJAX requests, falls back to redirect for non-JS."""
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

    # Return JSON for AJAX, redirect for non-JS fallback
    if request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.content_type == "application/json":
        return JsonResponse({
            "success": True,
            "item_name": item.name,
            "cart_count": sum(cart.values()),
        })

    # Only show Django message for non-AJAX (traditional form submit)
    messages.success(request, f"Added {item.name} to your cart.")
    return redirect("stores:store_detail", slug=slug)





def order_confirmation(request, order_number):
    order = get_object_or_404(Order, order_number=order_number)
    return render(request, "orders/order_confirmation.html", {"order": order})


@require_http_methods(["GET"])
def order_bill(request, order_number):
    """
    Downloadable PDF receipt.
    Publicly accessible by order_number (matching
    order_confirmation's access model) since checkout supports guest
    customers with no account to log into.
    Order numbers are generated from
    a random UUID and are not sequential/guessable.
    """
    order = get_object_or_404(Order, order_number=order_number)

    try:
        pdf_bytes = generate_order_bill_pdf(order)
    except Exception:
        logger.exception("Failed to generate PDF bill for order %s", order_number)
        messages.error(
            request,
            "Sorry, we couldn't generate your bill. Please try again or contact the store.",
        )
        return redirect("orders:order_confirmation", order_number=order_number)

    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="receipt_{order.order_number}.pdf"'
    response["Content-Length"] = len(pdf_bytes)
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

    # Existing filters
    status_filter = request.GET.get("status", "")
    date_from = request.GET.get("date_from", "")
    date_to = request.GET.get("date_to", "")
    min_total = request.GET.get("min_total", "")
    max_total = request.GET.get("max_total", "")
    sort = request.GET.get("sort", "-created_at")

    # New filters
    order_number_filter = request.GET.get("order_number", "").strip()
    customer_name_filter = request.GET.get("customer_name", "").strip()
    customer_phone_filter = request.GET.get("customer_phone", "").strip()

    orders = store.orders.filter(merged_into__isnull=True).select_related("customer").prefetch_related("items")

    # Apply new filters
    if order_number_filter:
        orders = orders.filter(order_number__icontains=order_number_filter)
    if customer_name_filter:
        orders = orders.filter(customer_name__icontains=customer_name_filter)
    if customer_phone_filter:
        orders = orders.filter(contact_phone__icontains=customer_phone_filter)

    # Apply existing filters
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

    allowed_sorts = {
        "-created_at": "Newest first", "created_at": "Oldest first",
        "-grand_total": "Total: high to low", "grand_total": "Total: low to high",
    }
    if sort not in allowed_sorts:
        sort = "-created_at"
    orders = orders.order_by(sort)

    return render(request, "orders/order_list.html", {
        "store": store, "orders": orders, "status_choices": Order.Status.choices,
        "status_filter": status_filter,
        "date_from": date_from, "date_to": date_to,
        "min_total": min_total, "max_total": max_total,
        "sort": sort, "sort_choices": allowed_sorts,
        "order_number_filter": order_number_filter,
        "customer_name_filter": customer_name_filter,
        "customer_phone_filter": customer_phone_filter,
    })



@login_required
def order_detail(request, order_number):
    order = get_object_or_404(Order, order_number=order_number)
    _require_owner_of(request, order.store)
    child_orders = order.merged_orders.all() if order.is_master else []
    available_items = order.store.food_items.filter(is_available=True).select_related("category").values(
        "pk", "name", "price", "category__name", "category__pk"
    )
    import json
    items_json = json.dumps([
        {"pk": i["pk"], "name": i["name"], "price": str(i["price"]),
         "category_pk": i["category__pk"] or 0,
         "category_name": i["category__name"] or "Uncategorized"}
        for i in available_items
    ])
    return render(request, "orders/order_detail.html", {
        "order": order,
        "child_orders": child_orders,
        "available_items": available_items,
        "items_json": items_json,
    })


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
    # Notify the customer if they have an account
    if order.customer:
        Notification.objects.create(
            user=order.customer,
            notification_type=Notification.Type.STATUS_CHANGED,
            title=f"Order {order.order_number} updated",
            message=f"Your order status is now: {order.get_status_display()}",
            order=order,
        )
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


# ---------------------------------------------------------------------------
# Owner manual order creation + editing
# ---------------------------------------------------------------------------

@login_required
def order_create_manual(request):
    """Owner creates an order manually — adds items and customer info."""
    store = request.user.stores.first()
    if not store:
        return redirect("stores:create_store")

    # Pass items with category info for the dependent dropdown
    food_items = store.food_items.filter(is_available=True).select_related("category").values(
        "pk", "name", "price", "category__name", "category__pk"
    )

    if request.method == "POST":
        order_form = ManualOrderForm(request.POST)

        item_pks = request.POST.getlist("food_item_pk[]")
        quantities = request.POST.getlist("quantity[]")

        cart_rows = []
        for pk, qty in zip(item_pks, quantities):
            try:
                item = store.food_items.get(pk=int(pk))
                cart_rows.append({"food_item": item, "quantity": max(1, int(qty))})
            except (ValueError, Exception):
                messages.error(request, "Invalid item selected.")
                return redirect("orders:order_create_manual")

        if not cart_rows:
            messages.error(request, "Please add at least one item to the order.")
            return redirect("orders:order_create_manual")

        if order_form.is_valid():
            try:
                order = create_order_with_items(
                    store=store,
                    cart_rows=cart_rows,
                    customer=None,
                    contact_fields={
                        "customer_name": order_form.cleaned_data.get("customer_name", ""),
                        "customer_address": order_form.cleaned_data.get("customer_address", ""),
                        "table_number": order_form.cleaned_data.get("table_number", ""),
                        "contact_phone": order_form.cleaned_data.get("contact_phone", ""),
                        "contact_email": order_form.cleaned_data.get("contact_email", ""),
                        "remarks": order_form.cleaned_data.get("remarks", ""),
},
                )
            except OrderMergeError as exc:
                messages.error(request, str(exc))
                return redirect("orders:order_create_manual")

            order.status = order_form.cleaned_data.get("status", Order.Status.PENDING)
            order.save(update_fields=["status", "updated_at"])

            logger.info("Manual order created: %s by %s", order.order_number, request.user.username)
            messages.success(request, f"Order {order.order_number} created successfully.")
            return redirect("orders:order_detail", order_number=order.order_number)
    else:
        order_form = ManualOrderForm()

    # Build a JSON-serializable structure for the JavaScript
    import json
    items_json = json.dumps([
        {"pk": item["pk"], "name": item["name"], "price": str(item["price"]),
         "category_pk": item["category__pk"] or 0,
         "category_name": item["category__name"] or "Uncategorized"}
        for item in food_items
    ])

    return render(request, "orders/order_create_manual.html", {
        "store": store,
        "form": order_form,
        "items_json": items_json,
    })



@login_required
def order_edit(request, order_number):
    """Owner edits order customer info and status."""
    order = get_object_or_404(Order, order_number=order_number)
    _require_owner_of(request, order.store)

    if request.method == "POST":
        form = OrderEditForm(request.POST)
        if form.is_valid():
            order.customer_name = form.cleaned_data.get("customer_name", "")
            order.customer_address = form.cleaned_data.get("customer_address", "")
            order.table_number = form.cleaned_data.get("table_number", "")
            order.contact_phone = form.cleaned_data.get("contact_phone", "")
            order.contact_email = form.cleaned_data.get("contact_email", "")
            order.remarks = form.cleaned_data.get("remarks", "")
            order.status = form.cleaned_data.get("status", order.status)
            order.save()
            messages.success(request, "Order updated.")
            return redirect("orders:order_detail", order_number=order.order_number)
    else:
        form = OrderEditForm(initial={
            "customer_name": order.customer_name,
            "customer_address": order.customer_address,
            "table_number": order.table_number,
            "contact_phone": order.contact_phone,
            "contact_email": order.contact_email,
            "remarks": order.remarks,
            "status": order.status,
        })

    return render(request, "orders/order_edit.html", {
        "order": order,
        "form": form,
    })



@login_required
@require_http_methods(["POST"])
def order_item_add(request, order_number):
    """Owner adds an item to an existing order."""
    order = get_object_or_404(Order, order_number=order_number)
    _require_owner_of(request, order.store)

    food_item_id = request.POST.get("food_item_id")
    quantity = max(1, min(99, int(request.POST.get("quantity", 1))))

    item = get_object_or_404(request.user.stores.first().food_items, pk=food_item_id)

    # Check if this item already exists in the order — if so, increase quantity
    existing = order.items.filter(food_item=item).first()
    if existing:
        existing.quantity += quantity
        existing.save(update_fields=["quantity"])
    else:
        OrderItem.objects.create(
            order=order,
            food_item=item,
            item_name_snapshot=item.name,
            unit_price_snapshot=item.price,
            tax_percentage_snapshot=getattr(item, "tax_percentage", 0) or 0,
            quantity=quantity,
        )

    order.recalculate_totals()
    messages.success(request, f"Added {quantity} x {item.name} to order.")
    return redirect("orders:order_detail", order_number=order.order_number)


@login_required
@require_http_methods(["POST"])
def order_item_edit(request, order_number, item_pk):
    """Owner edits quantity of an order item."""
    order = get_object_or_404(Order, order_number=order_number)
    _require_owner_of(request, order.store)

    order_item = get_object_or_404(OrderItem, pk=item_pk, order=order)
    quantity = max(1, min(99, int(request.POST.get("quantity", order_item.quantity))))

    order_item.quantity = quantity
    order_item.save(update_fields=["quantity"])
    order.recalculate_totals()

    messages.success(request, "Item quantity updated.")
    return redirect("orders:order_detail", order_number=order.order_number)


@login_required
@require_http_methods(["POST"])
def order_item_delete(request, order_number, item_pk):
    """Owner removes an item from an order."""
    order = get_object_or_404(Order, order_number=order_number)
    _require_owner_of(request, order.store)

    order_item = get_object_or_404(OrderItem, pk=item_pk, order=order)
    order_item.delete()
    order.recalculate_totals()

    messages.success(request, "Item removed from order.")
    return redirect("orders:order_detail", order_number=order.order_number)