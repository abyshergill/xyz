import logging

from django.contrib import messages
from django.shortcuts import redirect
from django.urls import reverse

logger = logging.getLogger("accounts")

# URL name prefixes that require a specific role. Checked in dispatch order;
# first match wins. This is a defence-in-depth layer -- every view/queryset
# MUST also independently filter by request.user (see stores/orders views),
# so a bug here can never by itself leak cross-tenant data.
ROLE_PROTECTED_NAMESPACES = {
    "owner": "OWNER",
    "platform_admin": "ADMIN",
}


class RoleBasedAccessMiddleware:
    """
    Blocks access to owner-only or admin-only URL namespaces before the view
    even runs, redirecting unauthorized users with a clear message and
    logging the attempt for audit purposes.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        resolver_match = getattr(request, "resolver_match", None)
        # resolver_match isn't populated until URL resolution happens inside
        # get_response for old-style middleware, so we check post-resolution
        # by wrapping process_view instead is cleaner -- but for simplicity
        # and clarity we use path-prefix checks here.
        path = request.path

        if path.startswith("/owner/"):
            if not request.user.is_authenticated or (
                not getattr(request.user, "is_owner_role", False) and not request.user.is_superuser
            ):
                logger.warning(
                    "Blocked unauthorized access to owner area: user=%s path=%s",
                    getattr(request.user, "username", "anonymous"),
                    path,
                )
                messages.error(request, "You must be logged in as a store owner to view that page.")
                return redirect(reverse("accounts:login"))

        if path.startswith("/platform-admin/"):
            if not request.user.is_authenticated or (
                not getattr(request.user, "is_admin_role", False) and not request.user.is_superuser
            ):
                logger.warning(
                    "Blocked unauthorized access to admin area: user=%s path=%s",
                    getattr(request.user, "username", "anonymous"),
                    path,
                )
                messages.error(request, "Administrator access required.")
                return redirect(reverse("accounts:login"))

        return self.get_response(request)
