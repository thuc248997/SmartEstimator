from rest_framework import serializers

from .models import PriceObservation


class PriceObservationSerializer(serializers.ModelSerializer):
    resource_code = serializers.CharField(source="resource.code", read_only=True)
    resource_name = serializers.CharField(source="resource.name", read_only=True)

    class Meta:
        model = PriceObservation
        fields = "__all__"
