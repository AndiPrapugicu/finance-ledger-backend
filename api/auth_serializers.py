from rest_framework import serializers
from django.contrib.auth.models import User
from django.contrib.auth import authenticate
from .temp_models import Account, Transaction

class UserRegistrationSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)
    password_confirm = serializers.CharField(write_only=True)
    
    class Meta:
        model = User
        fields = ['username', 'email', 'first_name', 'last_name', 'password', 'password_confirm']
    
    def validate(self, attrs):
        if attrs['password'] != attrs['password_confirm']:
            raise serializers.ValidationError("Passwords don't match")
        return attrs
    
    def create(self, validated_data):
        validated_data.pop('password_confirm')
        user = User.objects.create_user(**validated_data)
        
        # Create default accounts for new user
        default_accounts = [
            {'name': 'Checking Account', 'account_type': 'ASSET'},
            {'name': 'Savings Account', 'account_type': 'ASSET'},
            {'name': 'Credit Card', 'account_type': 'LIABILITY'},
            {'name': 'Salary', 'account_type': 'INCOME'},
            {'name': 'Food & Dining', 'account_type': 'EXPENSE'},
            {'name': 'Transportation', 'account_type': 'EXPENSE'},
            {'name': 'Housing', 'account_type': 'EXPENSE'},
        ]
        
        for account_data in default_accounts:
            Account.objects.create(user=user, **account_data)
        
        return user


class UserLoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True)
    
    def validate(self, attrs):
        username = attrs.get('username')
        password = attrs.get('password')
        
        if username and password:
            user = authenticate(username=username, password=password)
            if not user:
                raise serializers.ValidationError('Invalid credentials')
            if not user.is_active:
                raise serializers.ValidationError('User account is disabled')
            attrs['user'] = user
        else:
            raise serializers.ValidationError('Must include username and password')
        
        return attrs


class UserProfileSerializer(serializers.ModelSerializer):
    total_balance = serializers.SerializerMethodField()
    total_accounts = serializers.SerializerMethodField()
    total_transactions = serializers.SerializerMethodField()
    
    class Meta:
        model = User
        fields = [
            'id', 'username', 'email', 'first_name', 'last_name', 
            'date_joined', 'total_balance', 'total_accounts', 'total_transactions'
        ]
        read_only_fields = ['id', 'username', 'date_joined']
    
    def get_total_balance(self, obj):
        accounts = Account.objects.filter(user=obj, is_active=True)
        return sum(float(account.balance) for account in accounts)
    
    def get_total_accounts(self, obj):
        return Account.objects.filter(user=obj, is_active=True).count()
    
    def get_total_transactions(self, obj):
        return Transaction.objects.filter(user=obj).count()


class UserAccountSerializer(serializers.ModelSerializer):
    account_type_display = serializers.CharField(source='get_account_type_display', read_only=True)
    full_name = serializers.CharField(read_only=True)
    
    class Meta:
        model = Account
        fields = [
            'id', 'name', 'account_type', 'account_type_display', 'parent', 
            'balance', 'is_active', 'full_name', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def create(self, validated_data):
        user = self.context['request'].user
        return Account.objects.create(user=user, **validated_data)


class UserTransactionSerializer(serializers.ModelSerializer):
    account_name = serializers.CharField(source='account.name', read_only=True)
    
    class Meta:
        model = Transaction
        fields = [
            'id', 'account', 'account_name', 'date', 'description', 
            'amount', 'category', 'is_reconciled', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']
    
    def create(self, validated_data):
        validated_data['user'] = self.context['request'].user
        return super().create(validated_data)
    
    def validate_account(self, value):
        # Ensure user can only create transactions for their own accounts
        if value.user != self.context['request'].user:
            raise serializers.ValidationError("You can only create transactions for your own accounts")
        return value