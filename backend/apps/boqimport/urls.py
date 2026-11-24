from django.urls import path

from .views import auto_prices, commit_view, preview

urlpatterns = [
    path("revisions/<int:pk>/boq-import/preview", preview, name="boq-import-preview"),
    path("revisions/<int:pk>/boq-import/commit", commit_view, name="boq-import-commit"),
    path("revisions/<int:pk>/auto-prices", auto_prices, name="auto-prices"),
]
