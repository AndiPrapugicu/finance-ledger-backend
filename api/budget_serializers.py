from rest_framework import serializers
from backend.ledger.models import Budget

class BudgetSerializer(serializers.ModelSerializer):
    class Meta:
        model = Budget
        fields = ['budgetID', 'category', 'amount', 'period']
        read_only_fields = ['budgetID']

class BudgetCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Budget
        fields = ['category', 'amount', 'period']