import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Case, IntegerField, Q, Value, When
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from .forms import CategoryForm, FoodItemForm, OperatingHoursFormSet, StoreForm
from .models import Category, FoodItem, OperatingHours, Store
from .utils import generate_store_qr_code, validate_and_process_image
from django.conf import settings

logger = logging.getLogger("stores")

ITEMS_PER_CATEGORY_PREVIEW = 4  # <-- number of items shown per category on store detail


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
      - name  (q)        — case-insensitive partial match on store name
      - location (loc)   — case-insensitive partial match on store address
      - category (cat)   — category name; returns stores that have at least
                           one category matching this name
    Any combination of the three filters can be used together (AND logic).
    If none are provided, all active stores are listed.
    """
    stores = Store.objects.filter(is_active=True).prefetch_related("operating_hours")

    query = request.GET.get("q", "").strip()
    location = request.GET.get("loc", "").strip()
    category_name = request.GET.get("cat", "").strip()

    if query:
        stores = stores.filter(name__icontains=query)

    if location:
        stores = stores.filter(address__icontains=location)

    if category_name:
        # Only return stores that have a category with this name
        stores = stores.filter(categories__name__icontains=category_name).distinct()

    # Build a list of all category names (across all active stores) for the
    # category dropdown so the customer can pick from real categories.
    all_categories = (
        Category.objects
        .filter(store__is_active=True)
        .values_list("name", flat=True)
        .distinct()
        .order_by("name")
    )

    paginator = Paginator(stores, 12)
    page_obj = paginator.get_page(request.GET.get("page"))

    # Preserve filter params in pagination links
    filter_params = []
    if query:
        filter_params.append(f"q={query}")
    if location:
        filter_params.append(f"loc={location}")
    if category_name:
        filter_params.append(f"cat={category_name}")
    filter_query_string = "&".join(filter_params)

    return render(request, "stores/store_list.html", {
        "page_obj": page_obj,
        "query": query,
        "location": location,
        "category_name": category_name,
        "all_categories": all_categories,
        "filter_query_string": filter_query_string,
    })


def store_detail(request, slug):
    """
    Public menu page (also where a scanned QR code lands).

    Features:
      1. Category menubar — horizontal nav bar listing all categories as
         anchor links so customers can jump to a category section.
      2. 4-item preview per category — each category shows only the first
         ITEMS_PER_CATEGORY_PREVIEW items.  A 'See all in <category>' link
         expands to show every item in that category.
      3. Item search — a search box lets customers filter items by name
         within this store.  When searching, the 4-item limit is removed
         and only matching items are shown.
    """
    store = get_object_or_404(Store, slug=slug, is_active=True)

    # All categories for this store (for the menubar + sections)
    categories = (
        store.categories
        .prefetch_related("items")
        .order_by("display_order", "name")
    )

    # --- Item search within the store ---
    item_search = request.GET.get("item_q", "").strip()

    # --- "See all" expansion for a single category ---
    expand_category = request.GET.get("expand", "").strip()

    # Build a list of dicts with category + its items (limited to 4 unless
    # expanded or searching)
    category_data = []
    for category in categories:
        items = category.items.all()

        # If item search is active, filter items by name
        if item_search:
            items = items.filter(name__icontains=item_search)

        # Only show available items on the public page
        items = [it for it in items if it.is_available]

        is_expanded = (expand_category == category.name) or bool(item_search)

        if not is_expanded:
            visible_items = items[:ITEMS_PER_CATEGORY_PREVIEW]
        else:
            visible_items = items

        total_count = len(items)

        category_data.append({
            "category": category,
            "items": visible_items,
            "total_count": total_count,
            "hidden_count": total_count - len(visible_items),
            "is_expanded": is_expanded,
        })

    cart = request.session.get(f"cart_{store.slug}", {})

    return render(request, "stores/store_detail.html", {
        "store": store,
        "category_data": category_data,
        "store_is_open": store.is_open_now(),
        "cart_item_count": sum(cart.values()) if cart else 0,
        "item_search": item_search,
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
            store.full_clean()  # runs Store.clean() uniqueness check
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


# --- Food item management ---

@login_required
def item_list(request, slug):
    store = get_object_or_404(Store, slug=slug)
    _require_owner_of(request, store)
    items = store.food_items.select_related("category")
    return render(request, "stores/item_list.html", {"store": store, "items": items})


@login_required
def item_create(request, slug):
    store = get_object_or_404(Store, slug=slug)
    _require_owner_of(request, store)
    if request.method == "POST":
        form = FoodItemForm(request.POST, request.FILES, store=store)
        if form.is_valid():
            item = form.save(commit=False)
            item.store = store
            if "image" in request.FILES:
                item.image = validate_and_process_image(
                    request.FILES["image"], settings.FOOD_ITEM_IMAGE_MAX_DIMENSION
                )
            item.save()
            messages.success(request, "Item added to menu.")
            return redirect("stores:item_list", slug=slug)
    else:
        form = FoodItemForm(store=store)
    return render(request, "stores/item_form.html", {"store": store, "form": form, "is_create": True})


@login_required
def item_edit(request, slug, pk):
    store = get_object_or_404(Store, slug=slug)
    _require_owner_of(request, store)
    item = get_object_or_404(FoodItem, pk=pk, store=store)

    if request.method == "POST":
        form = FoodItemForm(request.POST, request.FILES, instance=item, store=store)
        if form.is_valid():
            updated = form.save(commit=False)
            if "image" in request.FILES:
                updated.image = validate_and_process_image(
                    request.FILES["image"], settings.FOOD_ITEM_IMAGE_MAX_DIMENSION
                )
            updated.save()
            messages.success(request, "Item updated.")
            return redirect("stores:item_list", slug=slug)
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