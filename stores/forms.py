from django import forms
from django.forms import inlineformset_factory

from .models import Category, FoodItem, OperatingHours, Store


class StoreForm(forms.ModelForm):
    class Meta:
        model = Store
        fields = [
            "name", "description", "store_picture", "address", "phone_number",
            "currency_code", "custom_currency_symbol", "custom_currency_icon",
            "require_table_number", "require_phone_number", "require_email",
        ]
        widgets = {"description": forms.Textarea(attrs={"rows": 4})}
        help_texts = {
            "currency_code": "Prices across your store will be shown with this symbol.",
        }


class OperatingHoursForm(forms.ModelForm):
    """
    The 'day' field is locked (disabled) on this form. The view guarantees
    exactly one OperatingHours row per day of the week already exists
    before this formset is ever built (see edit_operating_hours), so the
    day is always correctly pre-set from the instance -- there's no blank
    dropdown for an owner to accidentally leave unset or set to the wrong
    day, which previously caused hours to save against the wrong day (or
    fail to save at all) and made the store appear permanently closed.
    """

    class Meta:
        model = OperatingHours
        fields = ["day", "opening_time", "closing_time", "is_closed"]
        widgets = {
            "opening_time": forms.TimeInput(attrs={"type": "time"}, format="%H:%M"),
            "closing_time": forms.TimeInput(attrs={"type": "time"}, format="%H:%M"),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["day"].disabled = True


# extra=0 because the view always ensures all 7 day-rows already exist as
# real instances before this formset is instantiated -- there should never
# be blank "extra" rows with an ambiguous/unset day.
OperatingHoursFormSet = inlineformset_factory(
    Store, OperatingHours,
    form=OperatingHoursForm,
    fields=["day", "opening_time", "closing_time", "is_closed"],
    extra=0, max_num=7, can_delete=False,
)


class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ["name", "display_order"]


class FoodItemForm(forms.ModelForm):
    class Meta:
        model = FoodItem
        fields = ["category", "name", "description", "price", "stock_quantity", "image", "is_available"]
        widgets = {"description": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, store=None, **kwargs):
        super().__init__(*args, **kwargs)
        if store is not None:
            # Restrict the category dropdown to this store's own categories --
            # prevents an owner from ever assigning another store's category
            # (an IDOR-style vector) even via a crafted POST.
            self.fields["category"].queryset = Category.objects.filter(store=store)
