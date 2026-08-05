from django import forms
from django.forms import inlineformset_factory

from .models import Category, FoodItem, OperatingHours, Store


class StoreForm(forms.ModelForm):
    class Meta:
        model = Store
        fields = [
            "name",
            "description",
            "store_picture",
            "pincode",
            "store_category",
            "currency_code",
            "custom_currency_symbol",
            "custom_currency_icon",
            "require_table_number",
            "require_phone_number",
            "require_email",
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 4}),
            "pincode": forms.TextInput(
                attrs={
                    "placeholder": "e.g. 201301",
                    "class": "w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-orange-500 focus:border-orange-500 outline-none",
                }
            ),
        }
        help_texts = {
            "currency_code": "Prices across your store will be shown with this symbol.",
            "pincode": "Required. Customers can search for your store by pincode.",
            "store_category": "Choose the type of store you are running.",
        }


class OperatingHoursForm(forms.ModelForm):
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


OperatingHoursFormSet = inlineformset_factory(
    Store,
    OperatingHours,
    form=OperatingHoursForm,
    fields=["day", "opening_time", "closing_time", "is_closed"],
    extra=0,
    max_num=7,
    can_delete=False,
)


class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ["name", "display_order"]


class FoodItemForm(forms.ModelForm):
    class Meta:
        model = FoodItem
        fields = [
            "category",
            "name",
            "description",
            "price",
            "stock_quantity",
            "image",
            "is_available",
        ]
        widgets = {"description": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, store=None, **kwargs):
        super().__init__(*args, **kwargs)
        if store is not None:
            self.fields["category"].queryset = Category.objects.filter(
                store=store
            )


class ContactForm(forms.Form):
    name = forms.CharField(
        max_length=150, required=False,
        widget=forms.TextInput(attrs={
            "placeholder": "Your name (optional)",
            "class": "w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-orange-500 focus:border-orange-500 outline-none",
        }),
    )
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={
            "placeholder": "your@email.com",
            "class": "w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-orange-500 focus:border-orange-500 outline-none",
        }),
    )
    phone_number = forms.CharField(
        max_length=16,
        widget=forms.TextInput(attrs={
            "placeholder": "e.g. +66 2 123 4567",
            "class": "w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-orange-500 focus:border-orange-500 outline-none",
        }),
    )
    message = forms.CharField(
        max_length=1000,
        widget=forms.Textarea(attrs={
            "rows": 6,
            "maxlength": 1000,
            "placeholder": "Describe your complaint or concern (max 1000 characters)...",
            "class": "w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-orange-500 focus:border-orange-500 outline-none",
        }),
    )

    def clean_message(self):
        msg = self.cleaned_data.get("message", "")
        if len(msg) > 1000:
            raise forms.ValidationError("Message must not exceed 1000 characters.")
        return msg
