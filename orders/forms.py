from django import forms
from django.forms import formset_factory

from .models import Order


class CheckoutContactForm(forms.ModelForm):
    """
    Dynamically requires table_number / contact_phone / contact_email based
    on the store's configured checkout requirements (see Store.require_*).
    """

    class Meta:
        model = Order
        fields = ["table_number", "contact_phone", "contact_email"]

    def __init__(self, *args, store=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.store = store
        if store:
            self.fields["table_number"].required = store.require_table_number
            self.fields["contact_phone"].required = store.require_phone_number
            self.fields["contact_email"].required = store.require_email
            if not store.require_table_number:
                self.fields["table_number"].widget = forms.HiddenInput()
            if not store.require_phone_number:
                self.fields["contact_phone"].widget = forms.HiddenInput()
            if not store.require_email:
                self.fields["contact_email"].widget = forms.HiddenInput()


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
