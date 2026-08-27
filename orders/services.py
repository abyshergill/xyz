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
    Snapshots each item tax_percentage at order time for per-item tax billing.
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
            tax_percentage_snapshot=item.tax_percentage or 0,
            quantity=row["quantity"],
        )
    order.recalculate_totals()
    return order


def generate_order_bill_pdf(order) -> bytes:
    """
    Renders a printable receipt/bill PDF for an order (and, for a
    merged master ticket, includes every child order line items too).
    Shows per-item tax percentage and tax amount. Items with 0% tax
    show no tax line -- the price is the final price.
    Returns raw PDF bytes.
    """
    import io
    from xml.sax.saxutils import escape as xml_escape

    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet

    symbol = order.store.currency_symbol
    # Helvetica only supports WinAnsi/CP1252 characters.
    # Unicode symbols like ₹, ฿, د.إ won't render — fall back to currency code.
    try:
        symbol.encode("cp1252")
    except UnicodeEncodeError:
        symbol = order.store.currency_code + " "
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=20 * mm, bottomMargin=20 * mm)
    styles = getSampleStyleSheet()
    elements = []

    # --- Header ---
    elements.append(Paragraph(f"<b>{xml_escape(order.store.name)}</b>", styles["Title"]))
    store_address = getattr(order.store, "address", "")
    if store_address:
        elements.append(Paragraph(xml_escape(store_address), styles["Normal"]))
    elements.append(Spacer(1, 10))

    # --- Order meta ---
    elements.append(Paragraph(f"<b>Receipt for Order {xml_escape(order.order_number)}</b>", styles["Heading2"]))
    elements.append(Paragraph(f"Date: {order.created_at.strftime('%Y-%m-%d %H:%M')}", styles["Normal"]))
    elements.append(Paragraph(f"Status: {xml_escape(order.get_status_display())}", styles["Normal"]))
    if order.customer_name:
        elements.append(Paragraph(f"Customer: {xml_escape(order.customer_name)}", styles["Normal"]))
    if order.customer_address:
        elements.append(Paragraph(f"Address: {xml_escape(order.customer_address)}", styles["Normal"]))
    if order.table_number:
        elements.append(Paragraph(f"Table: {xml_escape(order.table_number)}", styles["Normal"]))
    if order.contact_phone:
        elements.append(Paragraph(f"Phone: {xml_escape(order.contact_phone)}", styles["Normal"]))
    if order.contact_email:
        elements.append(Paragraph(f"Email: {xml_escape(order.contact_email)}", styles["Normal"]))
    if order.remarks:
        elements.append(Paragraph(f"Remarks: {xml_escape(order.remarks)}", styles["Normal"]))
    elements.append(Spacer(1, 14))

    # --- Line items with per-item tax ---
    orders_to_include = [order]
    if order.is_master:
        orders_to_include += list(order.merged_orders.all())

    table_data = [["Item", "Qty", "Unit Price", "Tax %", "Tax Amt", "Line Total"]]
    for o in orders_to_include:
        for line in o.items.all():
            if line.tax_percentage_snapshot > 0:
                tax_pct_str = f"{line.tax_percentage_snapshot:.2f}%"
                tax_amt_str = f"{symbol}{line.tax_amount:,.2f}"
            else:
                tax_pct_str = "incl. tax"
                tax_amt_str = "--"
            line_total_with_tax = line.line_total + line.tax_amount    
            table_data.append([
            xml_escape(line.item_name_snapshot),
            str(line.quantity),
            f"{symbol}{line.unit_price_snapshot:,.2f}",
            tax_pct_str,
            tax_amt_str,
            f"{symbol}{line_total_with_tax:,.2f}",       # <-- Use the local variable
        ])

    table = Table(table_data, colWidths=[60 * mm, 15 * mm, 30 * mm, 20 * mm, 25 * mm, 30 * mm])
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

    # --- Totals ---
    totals_data = [
        ["Subtotal", f"{symbol}{order.subtotal:,.2f}"],
        ["Tax", f"{symbol}{order.tax_total:,.2f}"],
        ["Grand Total", f"{symbol}{order.grand_total:,.2f}"],
    ]
    totals_table = Table(totals_data, colWidths=[135 * mm, 45 * mm])
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

