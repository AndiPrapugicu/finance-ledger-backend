# TEMPORARY - Account model pentru API endpoints (Persoana C)
# Persoana A va implementa schema completă în backend/ledger/models.py

from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator
from decimal import Decimal

class Account(models.Model):
    ACCOUNT_TYPES = [
        ('ASSET', 'Asset'),
        ('LIABILITY', 'Liability'),
        ('EQUITY', 'Equity'),
        ('INCOME', 'Income'),
        ('EXPENSE', 'Expense'),
    ]
    
    # User relationship - cada conta pertence a um usuário
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='accounts')
    
    name = models.CharField(max_length=100)
    account_type = models.CharField(max_length=10, choices=ACCOUNT_TYPES)
    parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True)
    balance = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['name']
        # Ensure account names are unique per user
        unique_together = ['user', 'name']
    
    def __str__(self):
        return f"{self.user.username} - {self.name} ({self.get_account_type_display()})"
    
    @property
    def full_name(self):
        """Return full hierarchical account name"""
        if self.parent:
            return f"{self.parent.full_name}:{self.name}"
        return self.name


class Transaction(models.Model):
    """Temporary transaction model for API endpoints"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='transactions')
    account = models.ForeignKey(Account, on_delete=models.CASCADE, related_name='transactions')
    
    date = models.DateField()
    description = models.CharField(max_length=200)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    category = models.CharField(max_length=100, blank=True)
    is_reconciled = models.BooleanField(default=False)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-date', '-created_at']
    
    def __str__(self):
        return f"{self.user.username} - {self.date} - {self.description} - ${self.amount}"