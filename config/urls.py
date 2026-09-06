"""
Root URL configuration.
"""
from django.conf import settings
from django.contrib import admin
from django.urls import include, path, re_path
from django.views.generic import RedirectView
from django.views.static import serve as serve_static_file

admin.site.site_header = "YourTrolley Admin"
admin.site.site_title = "YourTrolley Admin"
admin.site.index_title = "Platform Administration"

urlpatterns = [
    path("django-admin/", admin.site.urls),  # Django's built-in admin, kept at a non-obvious path
    # accounts.urls FIRST: it defines its own 'login/' and 'logout/' paths
    # (RoleAwareLoginView, custom_logout). Django matches URL patterns in
    # list order, so listing this before allauth.urls means our views win
    # for any path both define, instead of allauth's account_login/
    # account_logout silently shadowing them.
    
    # allauth.urls (not allauth.socialaccount.urls!) — in current
    # django-allauth (65.x), the per-provider login/callback routes (e.g.
    # 'google_login', the name accounts/views.py reverses to start the
    # Google OAuth flow) are only registered via allauth.urls's internal
    # provider-urlpatterns builder. allauth.socialaccount.urls alone only
    # has 4 generic stub routes (login/cancelled, login/error, signup,
    # connections) and does NOT include Google's actual login/callback URLs
    # — using it alone silently drops Google auth entirely.
    # Mounted here at root (no app_name in scope) so 'google_login' stays a
    # bare/global name, matching accounts/views.py's reverse('google_login').
    # Any allauth account_* routes that collide with accounts.urls (login/,
    # logout/) are unreachable dead code thanks to the ordering above —
    # that's fine, we don't want users hitting allauth's own login page.
    
    path("", include("stores.urls")),
    path("", include("orders.urls")),
    path("", include("analytics.urls")),
    path("platform-admin/", include("platform_admin.urls")),
    path("", RedirectView.as_view(pattern_name="stores:store_list", permanent=False)),

    # django-allauth
    path("accounts/", include("accounts.urls")),
    path("accounts/", include("allauth.urls")),
]

# Serve uploaded media (store pictures, menu item photos, QR codes, receipts)
# directly from Django regardless of DEBUG. In a real production deployment
# behind Caddy (see Caddyfile), Caddy's own handle_path blocks intercept
# /static/* and /media/* before the request ever reaches Django -- this is
# just a working fallback so things don't quietly break if you flip
# DEBUG=False locally (e.g. to test the custom 404/500 pages) without Caddy
# running in front. Not intended for high-traffic production use on its own.
urlpatterns += [
    re_path(r"^media/(?P<path>.*)$", serve_static_file, {"document_root": settings.MEDIA_ROOT}),
    re_path(r"^static/(?P<path>.*)$", serve_static_file, {"document_root": settings.STATICFILES_DIRS[0]}),
]