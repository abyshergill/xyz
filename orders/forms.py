from django import forms
from django.forms import formset_factory

from .models import Order


class CheckoutContactForm(forms.ModelForm):
    """
    Dynamically requires table_number / contact_phone / contact_email /
    customer_name / customer_address based on the store configured
    checkout requirements (see Store.require_*).
    Also includes a remarks field for customer notes.
    """

    class Meta:
        model = Order
        fields = ["customer_name", "customer_address", "table_number", "contact_phone", "contact_email", "remarks"]

    def __init__(self, *args, store=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.store = store
        if store:
            self.fields["customer_name"].required = store.require_customer_name
            self.fields["customer_address"].required = store.require_customer_address
            self.fields["table_number"].required = store.require_table_number
            self.fields["contact_phone"].required = store.require_phone_number
            self.fields["contact_email"].required = store.require_email

            if not store.require_customer_name:
                self.fields["customer_name"].widget = forms.HiddenInput()
            if not store.require_customer_address:
                self.fields["customer_address"].widget = forms.HiddenInput()
            if not store.require_table_number:
                self.fields["table_number"].widget = forms.HiddenInput()
            if not store.require_phone_number:
                self.fields["contact_phone"].widget = forms.HiddenInput()
            if not store.require_email:
                self.fields["contact_email"].widget = forms.HiddenInput()

        # Add Tailwind classes to all visible fields
        for field_name in self.fields:
            field = self.fields[field_name]
            if not isinstance(field.widget, forms.HiddenInput):
                existing = field.widget.attrs.get("class", "")
                field.widget.attrs["class"] = f"{existing} w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-orange-500 focus:border-orange-500 outline-none".strip()
                if field_name == "remarks":
                    field.widget.attrs["rows"] = "3"
                    field.widget.attrs["placeholder"] = "Any special requests or notes for this order..."
                if field_name == "customer_address":
                    field.widget.attrs["placeholder"] = "Delivery address..."
                if field_name == "customer_name":
                    field.widget.attrs["placeholder"] = "Your full name"

                    
class CartItemForm(forms.Form):
    """One row of a submitted cart: a food item id + desired quantity."""

    food_item_id = forms.IntegerField(min_value=1)
    quantity = forms.IntegerField(min_value=1, max_value=99)


CartFormSet = formset_factory(CartItemForm, extra=0, min_num=1, validate_min=True)


class OrderTrackingForm(forms.Form):
    """
    Public order lookup: requires the order number PLUS one piece of info
    the customer supplied at checkout (phone, email, OR table number --
    whichever that store required), so a random guess of an order number
    alone can't be used to snoop on someone else's order.
    """

    order_number = forms.CharField(max_length=20, label="Order Number")
    verification = forms.CharField(
        max_length=100, label="Phone, Email, or Table Number used at checkout",
        help_text="Enter whichever of these you provided when placing the order.",
    )


class OrderMergeForm(forms.Form):
    """Owner-facing form to pick which active orders to merge into one ticket."""

    orders_to_merge = forms.ModelMultipleChoiceField(
        queryset=Order.objects.none(),
        widget=forms.CheckboxSelectMultiple,
        label="Select 2 or more active orders to merge",
    )

    def __init__(self, *args, store=None, **kwargs):
        super().__init__(*args, **kwargs)
        if store:
            # Strictly scoped to this store's own non-merged, active orders --
            # prevents merging another store's orders even via crafted POST data.
            self.fields["orders_to_merge"].queryset = Order.objects.filter(
                store=store, merged_into__isnull=True,
            ).exclude(status__in=[Order.Status.COMPLETED, Order.Status.CANCELLED])

    def clean_orders_to_merge(self):
        orders = self.cleaned_data["orders_to_merge"]
        if orders.count() < 2:
            raise forms.ValidationError("Select at least two orders to merge.")
        return orders

class ManualOrderForm(forms.Form):
    """Owner manually creates an order with customer info."""
    customer_name = forms.CharField(max_length=150, required=False, widget=forms.TextInput(attrs={"placeholder": "Customer name", "class": "w-full px-3 py-2 border border-gray-300 rounded-lg outline-none"}))
    customer_address = forms.CharField(max_length=255, required=False, widget=forms.TextInput(attrs={"placeholder": "Address", "class": "w-full px-3 py-2 border border-gray-300 rounded-lg outline-none"}))
    table_number = forms.CharField(max_length=20, required=False, widget=forms.TextInput(attrs={"placeholder": "Table number", "class": "w-full px-3 py-2 border border-gray-300 rounded-lg outline-none"}))
    contact_phone = forms.CharField(max_length=16, required=False, widget=forms.TextInput(attrs={"placeholder": "Phone", "class": "w-full px-3 py-2 border border-gray-300 rounded-lg outline-none"}))
    contact_email = forms.EmailField(required=False, widget=forms.EmailInput(attrs={"placeholder": "Email", "class": "w-full px-3 py-2 border border-gray-300 rounded-lg outline-none"}))
    remarks = forms.CharField(max_length=500, required=False, widget=forms.Textarea(attrs={"rows": 2, "placeholder": "Remarks", "class": "w-full px-3 py-2 border border-gray-300 rounded-lg outline-none"}))
    status = forms.ChoiceField(choices=Order.Status.choices, initial=Order.Status.PENDING, widget=forms.Select(attrs={"class": "px-3 py-2 border border-gray-300 rounded-lg outline-none"}))


class OrderEditForm(forms.Form):
    """Owner edits existing order customer info."""
    customer_name = forms.CharField(max_length=150, required=False, widget=forms.TextInput(attrs={"class": "w-full px-3 py-2 border border-gray-300 rounded-lg outline-none"}))
    customer_address = forms.CharField(max_length=255, required=False, widget=forms.TextInput(attrs={"class": "w-full px-3 py-2 border border-gray-300 rounded-lg outline-none"}))
    table_number = forms.CharField(max_length=20, required=False, widget=forms.TextInput(attrs={"class": "w-full px-3 py-2 border border-gray-300 rounded-lg outline-none"}))
    contact_phone = forms.CharField(max_length=16, required=False, widget=forms.TextInput(attrs={"class": "w-full px-3 py-2 border border-gray-300 rounded-lg outline-none"}))
    contact_email = forms.EmailField(required=False, widget=forms.EmailInput(attrs={"class": "w-full px-3 py-2 border border-gray-300 rounded-lg outline-none"}))
    remarks = forms.CharField(max_length=500, required=False, widget=forms.Textarea(attrs={"rows": 2, "class": "w-full px-3 py-2 border border-gray-300 rounded-lg outline-none"}))
    status = forms.ChoiceField(choices=Order.Status.choices, widget=forms.Select(attrs={"class": "px-3 py-2 border border-gray-300 rounded-lg outline-none"}))


class ManualOrderItemForm(forms.Form):
    """One row for selecting an item + quantity in manual order creation."""
    food_item = forms.ChoiceField(choices=[], widget=forms.Select(attrs={"class": "w-full px-3 py-2 border border-gray-300 rounded-lg outline-none"}))
    quantity = forms.IntegerField(min_value=1, max_value=99, initial=1, widget=forms.NumberInput(attrs={"class": "w-20 px-3 py-2 border border-gray-300 rounded-lg outline-none"}))