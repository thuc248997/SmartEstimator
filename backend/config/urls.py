from django.contrib import admin
from django.urls import include, path

from .views import healthz, index

urlpatterns = [
    path("", index, name="index"),
    path("healthz", healthz, name="healthz"),
    path("admin/", admin.site.urls),
    path("api/v1/", include("config.api_urls")),
]
