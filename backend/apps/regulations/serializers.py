from rest_framework import serializers

from .models import CostRulePack


class CostRulePackSerializer(serializers.ModelSerializer):
    class Meta:
        model = CostRulePack
        fields = "__all__"
