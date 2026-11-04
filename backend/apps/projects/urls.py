from rest_framework.routers import DefaultRouter

from .views import EstimateRevisionViewSet, ProjectViewSet

router = DefaultRouter(trailing_slash=False)
router.register("projects", ProjectViewSet, basename="project")
router.register("revisions", EstimateRevisionViewSet, basename="revision")
urlpatterns = router.urls
