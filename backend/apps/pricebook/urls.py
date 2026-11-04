from rest_framework.routers import DefaultRouter

from .views import PriceObservationViewSet

router = DefaultRouter(trailing_slash=False)
router.register("prices", PriceObservationViewSet, basename="price")
urlpatterns = router.urls
