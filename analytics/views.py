import json
from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.db.models import Count, DecimalField, F, Sum
from django.db.models.functions import TruncDate, TruncMonth, TruncWeek
from django.shortcuts import redirect, render
from django.utils import timezone

from orders.models import Order, OrderItem

PERIOD_TRUNC = {
    "daily": TruncDate,
    "weekly": TruncWeek,
    "monthly": TruncMonth,
}
PERIOD_LOOKBACK_DAYS = {"daily": 30, "weekly": 90, "monthly": 365}


@login_required
def owner_analytics_dashboard(request):
    """
    Renders the CRM/analytics page. Numerical summaries are computed with
    the Django ORM's aggregation functions (Sum, F expressions) rather than
    raw SQL, so the endpoint is inherently protected from SQL injection.
    Chart.js on the frontend consumes the JSON payloads embedded below.
    """
    store = request.user.stores.first()
    if not store:
        return redirect("stores:create_store")

    period = request.GET.get("period", "daily")
    if period not in PERIOD_TRUNC:
        period = "daily"

    trunc_fn = PERIOD_TRUNC[period]
    since = timezone.now() - timedelta(days=PERIOD_LOOKBACK_DAYS[period])

    completed_orders = Order.objects.filter(
        store=store, status=Order.Status.COMPLETED, created_at__gte=since,
    )

    # --- Sales over time ---
    sales_over_time = (
        completed_orders
        .annotate(period=trunc_fn("created_at"))
        .values("period")
        .annotate(total=Sum("grand_total"))
        .order_by("period")
    )

    # --- Item-wise sales ---
    item_sales = (
        OrderItem.objects
        .filter(order__store=store, order__status=Order.Status.COMPLETED, order__created_at__gte=since)
        .values("item_name_snapshot")
        .annotate(
            quantity_sold=Sum("quantity"),
            revenue=Sum(F("unit_price_snapshot") * F("quantity"), output_field=DecimalField()),
        )
        .order_by("-revenue")[:15]
    )

    # --- Category-wise sales ---
    category_sales = (
        OrderItem.objects
        .filter(order__store=store, order__status=Order.Status.COMPLETED, order__created_at__gte=since)
        .values("food_item__category__name")
        .annotate(
            revenue=Sum(F("unit_price_snapshot") * F("quantity"), output_field=DecimalField()),
        )
        .order_by("-revenue")
    )

    summary = completed_orders.aggregate(
        total_revenue=Sum("grand_total"),
        total_orders=Count("id"),
    )

    chart_data = {
        "sales_over_time": {
            "labels": [str(row["period"]) for row in sales_over_time],
            "data": [float(row["total"] or 0) for row in sales_over_time],
        },
        "item_sales": {
            "labels": [row["item_name_snapshot"] for row in item_sales],
            "data": [float(row["revenue"] or 0) for row in item_sales],
        },
        "category_sales": {
            "labels": [row["food_item__category__name"] or "Uncategorized" for row in category_sales],
            "data": [float(row["revenue"] or 0) for row in category_sales],
        },
    }

    return render(request, "analytics/dashboard.html", {
        "store": store,
        "period": period,
        "summary": summary,
        "item_sales": item_sales,
        "category_sales": category_sales,
        "chart_data_json": json.dumps(chart_data),
    })
