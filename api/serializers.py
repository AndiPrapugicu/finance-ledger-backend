from rest_framework import serializers
from .models import Account
from backend.ledger.models import Budget

class AccountSerializer(serializers.ModelSerializer):
    full_name = serializers.ReadOnlyField()
    account_type_display = serializers.CharField(source='get_account_type_display', read_only=True)
    balance = serializers.SerializerMethodField()
    
    def get_balance(self, obj):
        """Calculate real balance from LedgerTransaction system"""
        try:
            from backend.ledger.models import Transaction as LedgerTransaction, Split, Account as LedgerAccount
            from backend.ledger.models import Ledger
            
            # Get user's ledger
            user = self.context['request'].user
            try:
                ledger = Ledger.objects.get(username=user.username)
            except Ledger.DoesNotExist:
                return "0.00"
            
            # Find corresponding LedgerAccount by name and type
            try:
                ledger_account = LedgerAccount.objects.get(
                    name=obj.name,
                    account_type=obj.account_type,
                    is_active=True
                )
            except LedgerAccount.DoesNotExist:
                return "0.00"
            
            # Calculate balance from splits in user's ledger transactions
            total_balance = 0
            ledger_transactions = LedgerTransaction.objects.filter(ledger=ledger)
            for transaction in ledger_transactions:
                splits = transaction.splits.filter(account=ledger_account)
                total_balance += sum(float(split.amount) for split in splits)
            
            return f"{total_balance:.2f}"
        except Exception as e:
            print(f"[DEBUG] Error calculating account balance for {obj.name}: {e}")
            return "0.00"
    
    class Meta:
        model = Account
        fields = [
            'id', 'name', 'account_type', 'account_type_display', 
            'parent', 'balance', 'is_active', 'full_name',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['balance', 'created_at', 'updated_at']

class AccountCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Account
        fields = ['name', 'account_type', 'parent', 'is_active']
        
    def validate_parent(self, value):
        """Ensure parent account exists and prevent circular references"""
        if value and value.parent == self.instance:
            raise serializers.ValidationError("Cannot create circular reference")
        return value
    def create(self, validated_data):
        user = self.context['request'].user  # ia utilizatorul autentificat
        return Account.objects.create(user=user, **validated_data)

class BudgetSerializer(serializers.ModelSerializer):
    class Meta:
        model = Budget
        fields = ['budgetID', 'category', 'amount', 'period']
        read_only_fields = ['budgetID']

class BudgetCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Budget
        fields = ['category', 'amount', 'period']