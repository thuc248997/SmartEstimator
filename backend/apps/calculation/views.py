from django.shortcuts import get_object_or_404
from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view
from rest_framework.response import Response

from apps.audit.services import record
from apps.projects.models import EstimateRevision

from .models import CalculationRun
from .serializers import CalculationRunDetailSerializer, CalculationRunSerializer
from .services import explain_line, start_calculation


@api_view(["POST"])
def calculate(request, pk):
    revision = get_object_or_404(EstimateRevision, pk=pk)
    run_obj = start_calculation(revision)
    record(request.user, "revision.calculate", revision, {"run": run_obj.id, "status": run_obj.status})
    code = status.HTTP_200_OK if run_obj.status == CalculationRun.Status.DONE else status.HTTP_202_ACCEPTED
    return Response(CalculationRunSerializer(run_obj).data, status=code)


class CalculationRunViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = CalculationRun.objects.all()
    filterset_fields = ["revision", "status"]

    def get_serializer_class(self):
        return CalculationRunDetailSerializer if self.action == "retrieve" else CalculationRunSerializer

    @action(detail=True, methods=["get"])
    def explain(self, request, pk=None):
        run_obj = self.get_object()
        line_id = request.query_params.get("line_id")
        if not line_id:
            return Response({"detail": "line_id là bắt buộc"}, status=status.HTTP_400_BAD_REQUEST)
        return Response(explain_line(run_obj, int(line_id)))
