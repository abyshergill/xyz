from django.contrib.auth import get_user_model

def notifications(request):
    """Makes unread_notification_count available in all templates."""
    if request.user.is_authenticated:
        count = request.user.notifications.filter(is_read=False).count()
        return {"unread_notification_count": count}
    return {"unread_notification_count": 0}
