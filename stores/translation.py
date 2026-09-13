from modeltranslation.translator import register, TranslationOptions
from .models import Store, Category, FoodItem, Notification

@register(Store)
class StoreTranslationOptions(TranslationOptions):
    fields = ('description',)  # Add 'name' if store names need translation

@register(Category)
class CategoryTranslationOptions(TranslationOptions):
    fields = ('name',)

@register(FoodItem)
class FoodItemTranslationOptions(TranslationOptions):
    fields = ('name', 'description')

@register(Notification)
class NotificationTranslationOptions(TranslationOptions):
    fields = ('title', 'message')