from rest_framework import viewsets

from .models import PriceObservation
from .serializers import PriceObservationSerializer


class PriceObservationViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = PriceObservation.objects.select_related("resource", "release").all()
    serializer_class = PriceObservationSerializer
    filterset_fields = {
        "resource": ["exact"],
        "resource__code": ["exact"],
        "region": ["exact"],
        "period": ["exact"],
        "release": ["exact"],
        "status": ["exact"],
    }
