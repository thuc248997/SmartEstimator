from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import CalculationRunViewSet, calculate

router = DefaultRouter(trailing_slash=False)
router.register("calculation-runs", CalculationRunViewSet, basename="calculation-run")
urlpatterns = [path("revisions/<int:pk>/calculate", calculate, name="revision-calculate")] + router.urls
