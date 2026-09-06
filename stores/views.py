import logging
from django.http import JsonResponse
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Case, IntegerField, Q, Value, When
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods
from stores.models import Notification
from .forms import CategoryForm, ContactForm, FoodItemForm, OperatingHoursFormSet, StoreForm
from .models import Category, ContactMessage, FoodItem, OperatingHours, Store
from .utils import generate_store_qr_code, validate_and_process_image
from django.conf import settings
from .models import Category, FoodItem, Notification, OperatingHours, Store


logger = logging.getLogger("stores")

ITEMS_PER_CATEGORY_PREVIEW = 3  

def _require_owner_of(request, store):
    """
    RBAC guard used inside every owner view: confirms the logged-in user
    owns *this specific* store object, not just that they hold the OWNER
    role.
    """
    if store.owner_id != request.user.id:
        logger.warning(
            "Blocked cross-tenant access attempt: user=%s tried to access store=%s (owner=%s)",
            request.user.username, store.pk, store.owner_id,
        )
        raise PermissionDenied("You do not manage this store.")


# ---------------------------------------------------------------------------
# Public / customer-facing views
# ---------------------------------------------------------------------------

def store_list(request):
    """
    Public 'Browse Stalls' page.
    Supports filtering by:
      - name          (q)    — case-insensitive partial match on store name
      - store_category (scat) — dropdown: food, electronics, fashion, etc.
      - pincode       (pin)  — case-insensitive partial match on store pincode
    Any combination of the three filters can be used together (AND logic).
    If none are provided, all active stores are listed.
    """
    stores = Store.objects.filter(is_active=True).prefetch_related("operating_hours")

    query = request.GET.get("q", "").strip()
    store_category = request.GET.get("scat", "").strip()
    pincode = request.GET.get("pin", "").strip()

    if query:
        stores = stores.filter(name__icontains=query)

    if store_category:
        stores = stores.filter(store_category=store_category)

    if pincode:
        stores = stores.filter(pincode__icontains=pincode)

    # Build the store category dropdown from the StoreCategory choices
    all_store_categories = Store.StoreCategory.choices  # list of (value, label) tuples

    paginator = Paginator(stores, 12)
    page_obj = paginator.get_page(request.GET.get("page"))

    # Preserve filter params in pagination links
    filter_params = []
    if query:
        filter_params.append(f"q={query}")
    if store_category:
        filter_params.append(f"scat={store_category}")
    if pincode:
        filter_params.append(f"pin={pincode}")
    filter_query_string = "&".join(filter_params)

    # Resolve the human-readable label for the selected store category
    selected_category_label = ""
    for value, label in all_store_categories:
        if value == store_category:
            selected_category_label = label
            break

    return render(request, "stores/store_list.html", {
        "page_obj": page_obj,
        "query": query,
        "store_category": store_category,
        "selected_category_label": selected_category_label,
        "pincode": pincode,
        "all_store_categories": all_store_categories,
        "filter_query_string": filter_query_string,
    })


def store_detail(request, slug):
    """Public menu page with category menubar, 4-item preview, and item search."""
    store = get_object_or_404(Store, slug=slug, is_active=True)

    item_search = request.GET.get("item_q", "").strip()
    expand_category = request.GET.get("expand", "").strip()

    categories = store.categories.prefetch_related(
        "items"
    ).order_by("display_order", "name")

    # Build category_data with 4-item preview (or all items if searching/expanding)
    category_data = []
    for cat in categories:
        all_items = cat.items.filter(is_available=True).order_by("name")

        if item_search:
            # When searching, filter items by name across ALL categories
            all_items = all_items.filter(name__icontains=item_search)

        total_count = all_items.count()

        if item_search or expand_category == cat.name:
            # Show all items when searching or when this category is expanded
            shown_items = list(all_items)
            is_expanded = True
        else:
            # Show only first 3 items by default
            shown_items = list(all_items[:3])
            is_expanded = False

        hidden_count = total_count - len(shown_items)

        if total_count > 0 or item_search:
            category_data.append({
                "category": cat,
                "items": shown_items,
                "total_count": total_count,
                "hidden_count": hidden_count,
                "is_expanded": is_expanded,
            })

    cart = request.session.get(f"cart_{store.slug}", {})

    return render(request, "stores/store_detail.html", {
        "store": store,
        "category_data": category_data,
        "item_search": item_search,
        "store_is_open": store.is_open_now(),
        "cart_item_count": sum(cart.values()) if cart else 0,
    })


# ---------------------------------------------------------------------------
# Owner views (all under /owner/, guarded again by RoleBasedAccessMiddleware)
# ---------------------------------------------------------------------------

@login_required
def owner_dashboard(request):
    store = request.user.stores.first()
    if not store:
        return redirect("stores:create_store")
    recent_orders = store.orders.filter(merged_into__isnull=True).order_by("-created_at")[:10]
    low_stock_items = store.food_items.filter(stock_quantity__lte=5, is_available=True)
    return render(request, "stores/owner_dashboard.html", {
        "store": store,
        "recent_orders": recent_orders,
        "low_stock_items": low_stock_items,
        "store_is_open": store.is_open_now(),
    })


@login_required
def create_store(request):
    if request.user.stores.exists():
        messages.info(request, "You already have a store. You can edit it below.")
        return redirect("stores:edit_store", slug=request.user.stores.first().slug)

    if request.method == "POST":
        form = StoreForm(request.POST, request.FILES)
        if form.is_valid():
            store = form.save(commit=False)
            store.owner = request.user
            if "store_picture" in request.FILES:
                store.store_picture = validate_and_process_image(
                    request.FILES["store_picture"], settings.STORE_IMAGE_MAX_DIMENSION
                )
            if "custom_currency_icon" in request.FILES:
                store.custom_currency_icon = validate_and_process_image(
                    request.FILES["custom_currency_icon"], settings.CURRENCY_ICON_MAX_DIMENSION
                )
            store.full_clean()  # runs Store.clean() uniqueness + pincode check
            store.save()
            store.qr_code = generate_store_qr_code(store)
            store.save(update_fields=["qr_code"])
            logger.info("Store created: %s by %s", store.name, request.user.username)
            messages.success(request, "Store created! Now set your operating hours.")
            return redirect("stores:edit_operating_hours", slug=store.slug)
        messages.error(request, "Please correct the errors below.")
    else:
        form = StoreForm()
    return render(request, "stores/store_form.html", {"form": form, "is_create": True})


@login_required
def edit_store(request, slug):
    store = get_object_or_404(Store, slug=slug)
    _require_owner_of(request, store)

    if request.method == "POST":
        form = StoreForm(request.POST, request.FILES, instance=store)
        if form.is_valid():
            updated_store = form.save(commit=False)
            if "store_picture" in request.FILES:
                updated_store.store_picture = validate_and_process_image(
                    request.FILES["store_picture"], settings.STORE_IMAGE_MAX_DIMENSION
                )
            if "custom_currency_icon" in request.FILES:
                updated_store.custom_currency_icon = validate_and_process_image(
                    request.FILES["custom_currency_icon"], settings.CURRENCY_ICON_MAX_DIMENSION
                )
            updated_store.full_clean()
            updated_store.save()
            messages.success(request, "Store updated.")
            return redirect("stores:owner_dashboard")
    else:
        form = StoreForm(instance=store)
    return render(request, "stores/store_form.html", {"form": form, "is_create": False, "store": store})


@login_required
def edit_operating_hours(request, slug):
    store = get_object_or_404(Store, slug=slug)
    _require_owner_of(request, store)

    existing_days = set(store.operating_hours.values_list("day", flat=True))
    for day_code, _ in OperatingHours.Day.choices:
        if day_code not in existing_days:
            OperatingHours.objects.create(store=store, day=day_code, is_closed=True)

    day_order = Case(*[
        When(day=code, then=Value(i)) for i, (code, _) in enumerate(OperatingHours.Day.choices)
    ], output_field=IntegerField())
    ordered_hours = store.operating_hours.annotate(_day_order=day_order).order_by("_day_order")

    if request.method == "POST":
        formset = OperatingHoursFormSet(request.POST, instance=store, queryset=ordered_hours)
        if formset.is_valid():
            formset.save()
            messages.success(request, "Operating hours updated.")
            return redirect("stores:owner_dashboard")
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        formset = OperatingHoursFormSet(instance=store, queryset=ordered_hours)
    return render(request, "stores/operating_hours_form.html", {"formset": formset, "store": store})


@login_required
def toggle_store_active(request, slug):
    store = get_object_or_404(Store, slug=slug)
    _require_owner_of(request, store)
    store.is_active = not store.is_active
    store.save(update_fields=["is_active"])
    messages.success(request, f"Store is now {'active' if store.is_active else 'inactive'}.")
    return redirect("stores:owner_dashboard")


# --- Category management ---

@login_required
def category_list(request, slug):
    store = get_object_or_404(Store, slug=slug)
    _require_owner_of(request, store)
    categories = store.categories.all()
    if request.method == "POST":
        form = CategoryForm(request.POST)
        if form.is_valid():
            category = form.save(commit=False)
            category.store = store
            category.save()
            messages.success(request, "Category added.")
            return redirect("stores:category_list", slug=slug)
    else:
        form = CategoryForm()
    return render(request, "stores/category_list.html", {"store": store, "categories": categories, "form": form})


@login_required
@require_http_methods(["POST"])
def category_delete(request, slug, pk):
    store = get_object_or_404(Store, slug=slug)
    _require_owner_of(request, store)
    category = get_object_or_404(Category, pk=pk, store=store)
    category.delete()
    messages.success(request, "Category deleted.")
    return redirect("stores:category_list", slug=slug)

@login_required
@require_http_methods(["GET", "POST"])
def category_edit(request, slug, pk):
    store = get_object_or_404(Store, slug=slug)
    _require_owner_of(request, store)
    category = get_object_or_404(Category, pk=pk, store=store)
    if request.method == "POST":
        form = CategoryForm(request.POST, instance=category)
        if form.is_valid():
            form.save()
            messages.success(request, "Category updated.")
            return redirect("stores:category_list", slug=slug)
    else:
        form = CategoryForm(instance=category)
    return render(request, "stores/category_edit.html", {
        "store": store, "form": form, "category": category,
    })


# --- Food item management ---

@login_required
def item_list(request, slug):
    store = get_object_or_404(Store, slug=slug)
    _require_owner_of(request, store)
    items = store.food_items.select_related("category")

    # Filter by category
    category_filter = request.GET.get("category", "").strip()
    if category_filter:
        items = items.filter(category__name=category_filter)

    # Search by item name
    item_search = request.GET.get("item_q", "").strip()
    if item_search:
        items = items.filter(name__icontains=item_search)

    # Search by unique code
    code_search = request.GET.get("code_q", "").strip()
    if code_search:
        items = items.filter(item_code__icontains=code_search)

    # Pagination — 20 items per page
    paginator = Paginator(items, 20)
    page_obj = paginator.get_page(request.GET.get("page"))

    # All categories for the filter dropdown
    all_categories = store.categories.all().order_by("display_order", "name")

    # Preserve filter params in pagination links
    filter_params = []
    if category_filter:
        filter_params.append(f"category={category_filter}")
    if item_search:
        filter_params.append(f"item_q={item_search}")
    if code_search:
        filter_params.append(f"code_q={code_search}")
    filter_query_string = "&".join(filter_params)

    return render(request, "stores/item_list.html", {
        "store": store,
        "page_obj": page_obj,
        "items": page_obj,
        "all_categories": all_categories,
        "category_filter": category_filter,
        "item_search": item_search,
        "code_search": code_search,
        "filter_query_string": filter_query_string,
    })


@login_required
def item_create(request, slug):
    store = get_object_or_404(Store, slug=slug)
    _require_owner_of(request, store)
    if request.method == "POST":
        form = FoodItemForm(request.POST, request.FILES, store=store)
        if form.is_valid():
            item = form.save(commit=False)
            item.store = store
            # Auto-generate item code if left blank
            if not item.item_code:
                item.item_code = f"ITEM-{item.pk or FoodItem.objects.count() + 1:04d}"
            if "image" in request.FILES:
                item.image = validate_and_process_image(
                    request.FILES["image"], settings.FOOD_ITEM_IMAGE_MAX_DIMENSION
                )
            item.save()
            # Check low stock and notify owner
            if item.is_low_stock:
                Notification.objects.create(
                    user=store.owner,
                    notification_type=Notification.Type.LOW_STOCK,
                    title=f"Low stock: {item.name}",
                    message=f"'{item.name}' is at {item.stock_quantity} units (minimum: {item.min_stock_quantity}).",
                )
            messages.success(request, "Item added to menu.")
            return redirect("stores:item_list", slug=slug)
        messages.error(request, "Please correct the errors below.")
    else:
        form = FoodItemForm(store=store)
    return render(request, "stores/item_form.html", {"store": store, "form": form, "is_create": True})

@login_required
def item_edit(request, slug, pk):
    store = get_object_or_404(Store, slug=slug)
    _require_owner_of(request, store)
    item = get_object_or_404(FoodItem, pk=pk, store=store)
    old_stock = item.stock_quantity
    if request.method == "POST":
        form = FoodItemForm(request.POST, request.FILES, instance=item, store=store)
        if form.is_valid():
            updated = form.save(commit=False)
            if not updated.item_code:
                updated.item_code = f"ITEM-{updated.pk:04d}"
            if "image" in request.FILES:
                updated.image = validate_and_process_image(
                    request.FILES["image"], settings.FOOD_ITEM_IMAGE_MAX_DIMENSION
                )
            updated.save()
            # Check if stock dropped below minimum and notify owner
            if updated.is_low_stock and updated.stock_quantity < old_stock:
                Notification.objects.create(
                    user=store.owner,
                    notification_type=Notification.Type.LOW_STOCK,
                    title=f"Low stock: {updated.name}",
                    message=f"'{updated.name}' dropped to {updated.stock_quantity} units (minimum: {updated.min_stock_quantity}).",
                )
            messages.success(request, "Item updated.")
            return redirect("stores:item_list", slug=slug)
        messages.error(request, "Please correct the errors below.")
    else:
        form = FoodItemForm(instance=item, store=store)
    return render(request, "stores/item_form.html", {"store": store, "form": form, "is_create": False, "item": item})


@login_required
@require_http_methods(["POST"])
def item_delete(request, slug, pk):
    store = get_object_or_404(Store, slug=slug)
    _require_owner_of(request, store)
    item = get_object_or_404(FoodItem, pk=pk, store=store)
    item.delete()
    messages.success(request, "Item removed.")
    return redirect("stores:item_list", slug=slug)


# ---------------------------------------------------------------------------
# Contact Us page
# ---------------------------------------------------------------------------

def contact_us(request):
    """
    Public Contact Us page.
    Visitors can submit a complaint or concern with their email,
    phone number, and a message (max 1000 characters).
    Also displays platform contact information.
    """
    if request.method == "POST":
        form = ContactForm(request.POST)
        if form.is_valid():
            ContactMessage.objects.create(
                name=form.cleaned_data["name"],
                email=form.cleaned_data["email"],
                phone_number=form.cleaned_data["phone_number"],
                message=form.cleaned_data["message"],
            )
            messages.success(request, "Your message has been submitted. We will get back to you soon.")
            return redirect("stores:contact_us")
    else:
        form = ContactForm()

    # Platform contact information — change these to your real details
    platform_info = {
        "contact_email": "abyshergill@gmail.com",
        "contact_phone": "+66 2 123 4567",
        "contact_address": "Laem Chabang, Chonburi, Thailand",
    }

    return render(request, "stores/contact_us.html", {
        "form": form,
        "platform_info": platform_info,
    })


def store_list(request):
    """
    Public 'Browse Stalls' page.
    Supports filtering by:
      - name          (q)      — case-insensitive partial match on store name
      - store_category(scat)   — dropdown: food, electronics, fashion, etc.
      - pincode       (pin)    — case-insensitive partial match on store pincode
      - item          (item_q) — case-insensitive partial match on item name
    """
    stores = Store.objects.filter(is_active=True).prefetch_related("operating_hours")

    query = request.GET.get("q", "").strip()
    store_category = request.GET.get("scat", "").strip()
    pincode = request.GET.get("pin", "").strip()
    item_q = request.GET.get("item_q", "").strip()

    if query:
        stores = stores.filter(name__icontains=query)
    if store_category:
        stores = stores.filter(store_category=store_category)
    if pincode:
        stores = stores.filter(pincode__icontains=pincode)

    # --- Item Search Logic ---
    items_page_obj = None
    if item_q:
        items = FoodItem.objects.filter(
            name__icontains=item_q,
            store__is_active=True,
            is_available=True
        ).select_related("store")
        
        # Apply the store filters to the item results as well so they match
        if query:
            items = items.filter(store__name__icontains=query)
        if store_category:
            items = items.filter(store__store_category=store_category)
        if pincode:
            items = items.filter(store__pincode__icontains=pincode)
            
        items_paginator = Paginator(items, 12)
        items_page_obj = items_paginator.get_page(request.GET.get("item_page"))

    # Build the store category dropdown from the StoreCategory choices
    all_store_categories = Store.StoreCategory.choices

    paginator = Paginator(stores, 12)
    page_obj = paginator.get_page(request.GET.get("page"))

    # Preserve filter params in pagination links
    filter_params = []
    if query:
        filter_params.append(f"q={query}")
    if store_category:
        filter_params.append(f"scat={store_category}")
    if pincode:
        filter_params.append(f"pin={pincode}")
    if item_q:
        filter_params.append(f"item_q={item_q}")
    filter_query_string = "&".join(filter_params)

    # Resolve the human-readable label for the selected store category
    selected_category_label = ""
    for value, label in all_store_categories:
        if value == store_category:
            selected_category_label = label
            break

    return render(request, "stores/store_list.html", {
        "page_obj": page_obj,
        "items_page_obj": items_page_obj,
        "query": query,
        "store_category": store_category,
        "selected_category_label": selected_category_label,
        "pincode": pincode,
        "item_q": item_q,
        "all_store_categories": all_store_categories,
        "filter_query_string": filter_query_string,
    })


@login_required
def notifications(request):
    """Show all notifications for the logged-in user."""
    notifications = request.user.notifications.all()[:50]
    unread_count = request.user.notifications.filter(is_read=False).count()
    return render(request, "stores/notifications.html", {
        "notifications": notifications,
        "unread_count": unread_count,
    })


@login_required
@require_http_methods(["POST"])
def mark_notification_read(request, pk):
    """Mark a single notification as read."""
    notif = get_object_or_404(Notification, pk=pk, user=request.user)
    notif.is_read = True
    notif.save(update_fields=["is_read"])
    return redirect("stores:notifications")


@login_required
@require_http_methods(["POST"])
def mark_all_notifications_read(request):
    """Mark all notifications as read."""
    request.user.notifications.filter(is_read=False).update(is_read=True)
    return redirect("stores:notifications")

@login_required
def notification_count_api(request):
    """Returns unread notification count as JSON for AJAX polling."""
    count = request.user.notifications.filter(is_read=False).count()
    return JsonResponse({"unread_count": count})
