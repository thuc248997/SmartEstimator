from rest_framework.routers import DefaultRouter

from .views import CostRulePackViewSet

router = DefaultRouter(trailing_slash=False)
router.register("rule-packs", CostRulePackViewSet, basename="rule-pack")
urlpatterns = router.urls
