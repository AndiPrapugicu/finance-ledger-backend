# User Profile and Authentication Models
from django.contrib.auth.models import AbstractUser
from django.db import models
from decimal import Decimal

class User(AbstractUser):
    """Extended User model with financial profile"""
    
    # Profile fields
    avatar = models.ImageField(upload_to='avatars/', null=True, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    
    # Financial preferences
    currency = models.CharField(max_length=3, default='USD', help_text='Preferred currency code')
    default_balance_display = models.CharField(
        max_length=20, 
        choices=[
            ('total', 'Total Balance'),
            ('available', 'Available Balance'),
            ('liquid', 'Liquid Assets Only'),
        ], 
        default='available'
    )
    
    # App preferences
    theme = models.CharField(
        max_length=10, 
        choices=[('dark', 'Dark'), ('light', 'Light')], 
        default='dark'
    )
    notifications_enabled = models.BooleanField(default=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'auth_user_profile'
    
    def __str__(self):
        return f"{self.username} ({self.email})"
    
    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip() or self.username
    
    def get_total_balance(self):
        """Calculate total balance across all user accounts"""
        from .temp_models import Account
        user_accounts = Account.objects.filter(user=self, is_active=True)
        return sum(account.balance for account in user_accounts)
    
    def get_available_balance(self):
        """Calculate available balance (liquid assets)"""
        from .temp_models import Account
        liquid_accounts = Account.objects.filter(
            user=self, 
            is_active=True, 
            account_type__in=['ASSET', 'INCOME']
        )
        return sum(account.balance for account in liquid_accounts)


class UserSession(models.Model):
    """Track user sessions for enhanced security"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sessions')
    session_key = models.CharField(max_length=40, unique=True)
    ip_address = models.GenericIPAddressField()
    user_agent = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    last_activity = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        db_table = 'user_sessions'
        ordering = ['-last_activity']
    
    def __str__(self):
        return f"{self.user.username} - {self.ip_address}"