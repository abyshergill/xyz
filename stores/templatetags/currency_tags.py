"""
Renders a price using a store's configured currency -- either a text
symbol (built-in or custom) or an uploaded custom currency icon image.
"""

from django import template
from django.utils.html import format_html

register = template.Library()


@register.simple_tag
def currency(store, amount):
    """Usage: {% currency store item.price %}"""
    if store is None:
        return format_html("{}", amount)

    if getattr(store, "has_custom_currency_icon", False):
        return format_html(
            '<span class="inline-flex items-center gap-1">'
            '<img src="{}" alt="{}" class="w-4 h-4 inline-block object-contain">{}</span>',
            store.custom_currency_icon.url, store.currency_symbol, amount,
        )
    return format_html("{}{}", store.currency_symbol, amount)


@register.simple_tag
def currency_symbol_only(store):
    """Usage: {% currency_symbol_only store %} -- for labels/placeholders."""
    if store is None:
        return "$"
    if getattr(store, "has_custom_currency_icon", False):
        return format_html('<img src="{}" alt="{}" class="w-4 h-4 inline-block object-contain">',
                            store.custom_currency_icon.url, store.currency_symbol)
    return store.currency_symbol
