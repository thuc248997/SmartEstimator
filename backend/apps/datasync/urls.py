from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import DataUpdateViewSet, PriceCatalogViewSet, data_status

router = DefaultRouter(trailing_slash=False)
router.register("data-updates", DataUpdateViewSet, basename="data-update")
router.register("catalog/price-items", PriceCatalogViewSet, basename="price-item")
urlpatterns = [path("data-status", data_status), *router.urls]
