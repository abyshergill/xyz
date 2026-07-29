from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from accounts.models import User
from orders.models import Order
from stores.models import Store


@login_required
def dashboard(request):
    """
    Platform Admin overview. Access is additionally enforced by
    RoleBasedAccessMiddleware for any /platform-admin/ path.
    """
    context = {
        "total_stores": Store.objects.count(),
        "active_stores": Store.objects.filter(is_active=True).count(),
        "total_customers": User.objects.filter(role=User.Role.CUSTOMER).count(),
        "total_owners": User.objects.filter(role=User.Role.OWNER).count(),
        "total_orders": Order.objects.count(),
        "recent_stores": Store.objects.order_by("-created_at")[:10],
    }
    return render(request, "platform_admin/dashboard.html", context)
