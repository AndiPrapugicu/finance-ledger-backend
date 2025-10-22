from django.db import models
from django.contrib.auth.models import User
from decimal import Decimal

class UserProfile(models.Model):
    """Extended user profile for financial goals and preferences"""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='financial_profile')
    
    # Financial Goals
    monthly_income_goal = models.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        default=Decimal('3000.00'),
        help_text="User's target monthly income"
    )
    monthly_expense_budget = models.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        default=Decimal('2500.00'),
        help_text="User's planned monthly expense budget"
    )
    
    # Preferences
    currency = models.CharField(max_length=3, default='USD')
    timezone = models.CharField(max_length=50, default='UTC')
    
    # Goal tracking settings
    income_goal_enabled = models.BooleanField(default=True)
    budget_alerts_enabled = models.BooleanField(default=True)
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'api_user_profile'
    
    def __str__(self):
        return f"{self.user.username}'s Financial Profile"
    
    @property
    def income_goal_monthly(self):
        """Get monthly income goal"""
        return self.monthly_income_goal
    
    @property  
    def expense_budget_monthly(self):
        """Get monthly expense budget"""
        return self.monthly_expense_budget


# Signal to create profile when user is created
from django.db.models.signals import post_save
from django.dispatch import receiver

@receiver(post_save, sender=User)
def create_user_financial_profile(sender, instance, created, **kwargs):
    """Automatically create a financial profile when a new user is created"""
    if created:
        UserProfile.objects.create(user=instance)

@receiver(post_save, sender=User)
def save_user_financial_profile(sender, instance, **kwargs):
    """Save the financial profile when user is saved"""
    if hasattr(instance, 'financial_profile'):
        instance.financial_profile.save()