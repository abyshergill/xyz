"""
Root URL configuration.
"""
from django.conf import settings
from django.contrib import admin
from django.contrib.staticfiles.storage import staticfiles_storage
from django.urls import include, path, re_path
from django.views.generic import RedirectView
from django.views.static import serve as serve_static_file
from stores import views as stores_views

admin.site.site_header = "YourTrolley Admin"
admin.site.site_title = "YourTrolley Admin"
admin.site.index_title = "Platform Administration"

urlpatterns = [
    # Language switcher endpoint
    path('i18n/', include('django.conf.urls.i18n')),

    # Django's built-in admin
    path("django-admin/", admin.site.urls),

    # App URLs
    path("", include("stores.urls")),
    path("", include("orders.urls")),
    path("", include("analytics.urls")),
    path("platform-admin/", include("platform_admin.urls")),
    
    # Accounts & Allauth
    path("accounts/", include("accounts.urls")),
    path("accounts/", include("allauth.urls")),

    # Favicon
    path(
        'favicon.ico',
        RedirectView.as_view(
            url=staticfiles_storage.url('images/favicon.ico'),
            permanent=True
        )
    ),
]

# Media and Static fallbacks
urlpatterns += [
    re_path(r"^media/(?P<path>.*)$", serve_static_file, {"document_root": settings.MEDIA_ROOT}),
    re_path(r"^static/(?P<path>.*)$", serve_static_file, {"document_root": settings.STATICFILES_DIRS[0]}),
]