from rest_framework import serializers
from .wallet_models import Wallet, PaymentMethod, WalletTransaction
from decimal import Decimal

class PaymentMethodSerializer(serializers.ModelSerializer):
    """Serializer for payment methods"""
    class Meta:
        model = PaymentMethod
        fields = [
            'id', 'name', 'payment_type', 'last_four_digits', 
            'is_default', 'is_active', 'card_brand', 
            'expires_month', 'expires_year', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']
    
    def validate(self, data):
        """Validate payment method data"""
        if data.get('payment_type') == 'card':
            if not data.get('last_four_digits'):
                raise serializers.ValidationError("Last four digits required for cards")
            if len(data['last_four_digits']) != 4:
                raise serializers.ValidationError("Last four digits must be exactly 4 characters")
        
        return data


class WalletTransactionSerializer(serializers.ModelSerializer):
    """Serializer for wallet transactions"""
    payment_method_name = serializers.CharField(source='payment_method.name', read_only=True)
    
    class Meta:
        model = WalletTransaction
        fields = [
            'id', 'transaction_type', 'amount', 'description', 
            'status', 'balance_after', 'payment_method', 
            'payment_method_name', 'related_transaction_id',
            'created_at', 'processed_at'
        ]
        read_only_fields = ['id', 'balance_after', 'created_at', 'processed_at']


class WalletSerializer(serializers.ModelSerializer):
    """Serializer for user wallet"""
    recent_transactions = WalletTransactionSerializer(
        source='transactions', 
        many=True, 
        read_only=True
    )
    payment_methods = PaymentMethodSerializer(
        source='user.payment_methods', 
        many=True, 
        read_only=True
    )
    
    class Meta:
        model = Wallet
        fields = [
            'id', 'balance', 'currency', 'created_at', 
            'updated_at', 'is_active', 'recent_transactions', 
            'payment_methods'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class AddFundsSerializer(serializers.Serializer):
    """Serializer for adding funds to wallet"""
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal('0.01'))
    description = serializers.CharField(max_length=255, required=False, default="Funds added")
    payment_method_id = serializers.IntegerField(required=False, allow_null=True)
    
    def validate_amount(self, value):
        """Validate amount"""
        if value <= 0:
            raise serializers.ValidationError("Amount must be positive")
        if value > Decimal('10000.00'):
            raise serializers.ValidationError("Maximum amount is $10,000 per transaction")
        return value


class CreatePaymentMethodSerializer(serializers.ModelSerializer):
    """Serializer for creating payment methods"""
    class Meta:
        model = PaymentMethod
        fields = [
            'name', 'payment_type', 'last_four_digits', 
            'is_default', 'card_brand', 'expires_month', 'expires_year'
        ]
    
    def validate(self, data):
        """Validate payment method creation"""
        if data.get('payment_type') == 'card':
            required_fields = ['last_four_digits', 'card_brand']
            for field in required_fields:
                if not data.get(field):
                    raise serializers.ValidationError(f"{field} is required for cards")
            
            # Validate expiry date
            if data.get('expires_month') and data.get('expires_year'):
                month = data['expires_month']
                year = data['expires_year']
                
                if not (1 <= month <= 12):
                    raise serializers.ValidationError("Invalid expiry month")
                
                from datetime import datetime
                current_year = datetime.now().year
                if year < current_year or year > current_year + 20:
                    raise serializers.ValidationError("Invalid expiry year")
        
        return data
    
    def create(self, validated_data):
        """Create payment method with user"""
        user = self.context['request'].user
        validated_data['user'] = user
        return super().create(validated_data)
class WalletTransferSerializer(serializers.Serializer):
    walletId = serializers.IntegerField()
    destinationAccount = serializers.IntegerField()
    amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    description = serializers.CharField(required=False, allow_blank=True)
    paymentMethod = serializers.IntegerField(required=False)