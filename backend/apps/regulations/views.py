from rest_framework import viewsets

from .models import CostRulePack
from .serializers import CostRulePackSerializer


class CostRulePackViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = CostRulePack.objects.all()
    serializer_class = CostRulePackSerializer
    filterset_fields = ["code", "is_approved"]
