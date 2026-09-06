# accounts/decorators.py
from django.core.exceptions import PermissionDenied

def shop_owner_required(view_func):
    def _wrapped_view(request, *args, **kwargs):
        # Was checking against 'SHOP_OWNER', which never matches — the
        # actual stored value is User.Role.OWNER = "OWNER" (see models.py).
        # This bug blocked every real shop owner from any view wrapped
        # with this decorator, regardless of how they logged in.
        if request.user.is_authenticated and request.user.role == 'OWNER':
            return view_func(request, *args, **kwargs)
        raise PermissionDenied
    return _wrapped_view