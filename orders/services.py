"""
Business logic kept out of views: order merging and stock-safe order
creation. Isolating this here makes it independently unit-testable and
keeps views thin (defence against logic bugs creeping into request handling).
"""

from django.db import transaction

from .models import Order, OrderItem


class OrderMergeError(Exception):
    pass


@transaction.atomic
def merge_orders(orders, initiating_owner) -> Order:
    """
    Consolidates multiple active orders belonging to the SAME store into a
    single master billing ticket.

    Individual item tracking is preserved: child orders and their OrderItem
    rows are left untouched -- only Order.merged_into is set, pointing them
    at a newly created master Order. Reporting/billing code aggregates
    across `master.merged_orders` + itself.
    """
    orders = list(orders)
    if len(orders) < 2:
        raise OrderMergeError("At least two orders are required to merge.")

    store_ids = {o.store_id for o in orders}
    if len(store_ids) > 1:
        raise OrderMergeError("Cannot merge orders from different stores.")

    store = orders[0].store
    if store.owner_id != initiating_owner.id:
        raise OrderMergeError("You do not have permission to merge orders for this store.")

    for o in orders:
        if o.merged_into_id is not None:
            raise OrderMergeError(f"Order {o.order_number} is already part of a merged ticket.")
        if o.status in (Order.Status.COMPLETED, Order.Status.CANCELLED):
            raise OrderMergeError(f"Order {o.order_number} is no longer active and cannot be merged.")

    master = Order.objects.create(
        store=store,
        customer=orders[0].customer,
        table_number=orders[0].table_number,
        contact_phone=orders[0].contact_phone,
        contact_email=orders[0].contact_email,
        status=Order.Status.PREPARING,
    )

    for o in orders:
        o.merged_into = master
        o.save(update_fields=["merged_into", "updated_at"])

    master.recalculate_totals()
    return master


@transaction.atomic
def create_order_with_items(store, cart_rows, customer=None, contact_fields=None):
    """
    cart_rows: iterable of {"food_item": FoodItem, "quantity": int}
    Validates stock availability atomically (select_for_update) to avoid a
    race condition where two customers oversell the last unit at once.
    """
    from stores.models import FoodItem

    contact_fields = contact_fields or {}
    order = Order.objects.create(store=store, customer=customer, **contact_fields)

    for row in cart_rows:
        item = FoodItem.objects.select_for_update().get(pk=row["food_item"].pk, store=store)
        if not item.in_stock or item.stock_quantity < row["quantity"]:
            raise OrderMergeError(f"'{item.name}' does not have enough stock available.")
        item.stock_quantity -= row["quantity"]
        item.save(update_fields=["stock_quantity"])

        OrderItem.objects.create(
            order=order,
            food_item=item,
            item_name_snapshot=item.name,
            unit_price_snapshot=item.price,
            quantity=row["quantity"],
        )

    order.recalculate_totals()
    return order


def generate_order_bill_pdf(order) -> bytes:
    """
    Renders a simple printable receipt/bill PDF for an order (and, for a
    merged master ticket, includes every child order's line items too).
    Returns raw PDF bytes -- the view wraps this in an HttpResponse with
    the appropriate Content-Disposition header to trigger a download.
    """
    import io

    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet

    symbol = order.store.currency_symbol

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=20 * mm, bottomMargin=20 * mm)
    styles = getSampleStyleSheet()
    elements = []

    elements.append(Paragraph(f"<b>{order.store.name}</b>", styles["Title"]))
    if order.store.address:
        elements.append(Paragraph(order.store.address, styles["Normal"]))
    elements.append(Spacer(1, 10))
    elements.append(Paragraph(f"<b>Receipt for Order {order.order_number}</b>", styles["Heading2"]))
    elements.append(Paragraph(f"Date: {order.created_at.strftime('%Y-%m-%d %H:%M')}", styles["Normal"]))
    elements.append(Paragraph(f"Status: {order.get_status_display()}", styles["Normal"]))
    if order.table_number:
        elements.append(Paragraph(f"Table: {order.table_number}", styles["Normal"]))
    elements.append(Spacer(1, 14))

    orders_to_include = [order]
    if order.is_master:
        orders_to_include += list(order.merged_orders.all())

    table_data = [["Item", "Qty", "Unit Price", "Line Total"]]
    for o in orders_to_include:
        for line in o.items.all():
            table_data.append([
                line.item_name_snapshot, str(line.quantity),
                f"{symbol}{line.unit_price_snapshot}", f"{symbol}{line.line_total}",
            ])

    table = Table(table_data, colWidths=[80 * mm, 20 * mm, 35 * mm, 35 * mm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#ea580c")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e5e7eb")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f9fafb")]),
    ]))
    elements.append(table)
    elements.append(Spacer(1, 14))

    totals_data = [
        ["Subtotal", f"{symbol}{order.subtotal}"],
        ["Tax", f"{symbol}{order.tax_total}"],
        ["Grand Total", f"{symbol}{order.grand_total}"],
    ]
    totals_table = Table(totals_data, colWidths=[135 * mm, 35 * mm])
    totals_table.setStyle(TableStyle([
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("LINEABOVE", (0, -1), (-1, -1), 1, colors.black),
    ]))
    elements.append(totals_table)
    elements.append(Spacer(1, 20))
    elements.append(Paragraph("Thank you for your order!", styles["Italic"]))

    doc.build(elements)
    return buffer.getvalue()
