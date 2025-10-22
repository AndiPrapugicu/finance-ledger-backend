from django.db import models
from django.contrib.auth.models import User
import sqlite3
import time
from django.core.validators import MinValueValidator
from decimal import Decimal
import uuid

class Wallet(models.Model):
    """User's digital wallet for managing funds"""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='wallet')
    balance = models.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))]
    )
    currency = models.CharField(max_length=3, default='USD')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        db_table = 'api_wallet'
    
    def __str__(self):
        return f"{self.user.username}'s Wallet - {self.currency} {self.balance}"
    
    def add_funds(self, amount, description="Funds added"):
        """Add funds to wallet"""
        if amount <= 0:
            raise ValueError("Amount must be positive")
        
        self.balance += Decimal(str(amount))
        self.save()
        
        # Create transaction record
        WalletTransaction.objects.create(
            wallet=self,
            transaction_type='deposit',
            amount=amount,
            description=description,
            balance_after=self.balance
        )
        
        return self.balance
    
    def deduct_funds(self, amount, description="Funds deducted"):
        """Deduct funds from wallet"""
        if amount <= 0:
            raise ValueError("Amount must be positive")
        
        if self.balance < Decimal(str(amount)):
            raise ValueError("Insufficient funds")
        
        self.balance -= Decimal(str(amount))
        self.save()
        
        # Create transaction record
        WalletTransaction.objects.create(
            wallet=self,
            transaction_type='withdrawal',
            amount=amount,
            description=description,
            balance_after=self.balance
        )
        
        return self.balance


class PaymentMethod(models.Model):
    """
    User's payment methods (cards, bank accounts, etc.)
    
    IMPORTANT: This is a demo implementation for tracking payment methods.
    In production, integrate with Stripe, PayPal, or similar payment processors.
    
    For Stripe Integration:
    - Use Stripe Elements for secure card input
    - Store Stripe customer_id and payment_method_id instead of card details
    - Never store full card numbers or CVV in your database
    - Use Stripe's tokenization for PCI compliance
    
    Example production flow:
    1. Frontend: User enters card → Stripe Elements creates token
    2. Backend: Store stripe_customer_id, stripe_payment_method_id
    3. Payments: Use Stripe API with stored IDs
    
    This current implementation only stores last 4 digits for display purposes.
    """
    PAYMENT_TYPES = [
        ('card', 'Credit/Debit Card'),
        ('bank', 'Bank Account'),
        ('paypal', 'PayPal'),
        ('crypto', 'Cryptocurrency'),
        ('trasfer', 'Bank Transfer')
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='payment_methods')
    name = models.CharField(max_length=100)  # e.g., "Visa ending in 1234"
    payment_type = models.CharField(max_length=10, choices=PAYMENT_TYPES)
    last_four_digits = models.CharField(max_length=4, blank=True)
    is_default = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    # We won't store actual card numbers - this is just for display/tracking
    card_brand = models.CharField(max_length=50, blank=True)  # Visa, Mastercard, etc.
    expires_month = models.PositiveIntegerField(null=True, blank=True)
    expires_year = models.PositiveIntegerField(null=True, blank=True)
    
    class Meta:
        db_table = 'api_payment_method'
        ordering = ['-is_default', '-created_at']
    
    def __str__(self):
        return f"{self.name} ({self.get_payment_type_display()})"
    
    def save(self, *args, **kwargs):
        # Ensure only one default payment method per user
        if self.is_default:
            PaymentMethod.objects.filter(
                user=self.user, 
                is_default=True
            ).exclude(pk=self.pk).update(is_default=False)
        super().save(*args, **kwargs)


class WalletTransaction(models.Model):
    """Transaction history for wallet operations"""
    TRANSACTION_TYPES = [
        ('deposit', 'Deposit'),
        ('withdrawal', 'Withdrawal'),
        ('expense', 'Expense Payment'),
        ('income', 'Income Received'),
        ('refund', 'Refund'),
    ]
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    wallet = models.ForeignKey(Wallet, on_delete=models.CASCADE, related_name='transactions')
    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPES)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    description = models.CharField(max_length=255)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='completed')
    balance_after = models.DecimalField(max_digits=12, decimal_places=2)
    
    # Optional reference to payment method used
    payment_method = models.ForeignKey(
        PaymentMethod, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True
    )
    
    # Optional reference to related account transaction
    related_transaction_id = models.CharField(max_length=100, null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        db_table = 'api_wallet_transaction'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.get_transaction_type_display()} - {self.wallet.currency} {self.amount}"


# Signal to create wallet when user is created
from django.db.models.signals import post_save
from django.dispatch import receiver

@receiver(post_save, sender=User)
def create_user_wallet(sender, instance, created, **kwargs):
    """Automatically create a wallet when a new user is created"""
    if created:
        # Create wallet
        Wallet.objects.create(user=instance)
        
        # Create ledger for the user and ensure a "Digital Wallet" Account exists
        from backend.ledger.models import Ledger, Account

        # Create or get ledger (basic, tolerate normal exceptions)
        ledger, _ = Ledger.objects.get_or_create(username=instance.username)

        # Ensure Digital Wallet account exists; retry on transient sqlite locks
        max_attempts = 5
        attempt = 0
        while True:
            try:
                Account.objects.get_or_create(
                    ledger=ledger,
                    name='Digital Wallet',
                    defaults={
                        'account_type': 'ASSET',
                        'is_active': True
                    }
                )
                break
            except sqlite3.OperationalError as oe:
                attempt += 1
                if attempt >= max_attempts:
                    print(f"[ERROR] Failed to create Digital Wallet account for user {instance.username} after {attempt} attempts: {oe}")
                    break
                sleep_time = 0.05 * attempt
                print(f"[WARN] SQLite lock when creating Digital Wallet for {instance.username}: {oe}. Retrying in {sleep_time}s (attempt {attempt}/{max_attempts})")
                time.sleep(sleep_time)
            except Exception as ex:
                print(f"[ERROR] Unexpected error while creating Digital Wallet account for {instance.username}: {ex}")
                break

@receiver(post_save, sender=User)
def save_user_wallet(sender, instance, **kwargs):
    """Save the wallet when user is saved"""
    if hasattr(instance, 'wallet'):
        instance.wallet.save()


# Transaction-Wallet integration
from .temp_models import Account, Transaction

@receiver(post_save, sender=Transaction)
def sync_transaction_to_wallet(sender, instance, created, **kwargs):
    """Sync Transaction with Wallet when transaction is created or updated"""
    if created:
        try:
            wallet = Wallet.objects.get(user=instance.user)
            
            # Determine transaction type based on account type and amount
            if instance.account.account_type == 'INCOME' or instance.amount > 0:
                # Income transaction - add to wallet
                wallet.add_funds(
                    amount=abs(instance.amount),
                    description=f"Income: {instance.description}",
                    transaction_type='income'
                )
            elif instance.account.account_type == 'EXPENSE' or instance.amount < 0:
                # Expense transaction - deduct from wallet
                wallet.deduct_funds(
                    amount=abs(instance.amount),
                    description=f"Expense: {instance.description}",
                    transaction_type='expense'
                )
                
        except Wallet.DoesNotExist:
            # Create wallet if it doesn't exist
            wallet = Wallet.objects.create(user=instance.user)
            # Retry the transaction
            sync_transaction_to_wallet(sender, instance, created, **kwargs)
def transfer_funds(self, destination_account: Account, amount, description="Wallet transfer", payment_method=None):
    from django.db import transaction as db_transaction
    import uuid
    from decimal import Decimal
    from .wallet_models import WalletTransfer, WalletTransaction

    if amount <= 0:
        raise ValueError("Amount must be positive")
    if self.balance < Decimal(str(amount)):
        raise ValueError("Insufficient funds for transfer")

    with db_transaction.atomic():
        # Deduct from wallet
        self.balance -= Decimal(str(amount))
        self.save()
        WalletTransaction.objects.create(
            wallet=self,
            transaction_type='withdrawal',
            amount=Decimal(str(amount)),
            description=description,
            balance_after=self.balance,
            payment_method=payment_method,
            related_transaction_id=str(uuid.uuid4())
        )

        # Add to account
        destination_account.balance += Decimal(str(amount))
        destination_account.save()
        WalletTransfer.objects.create(
            account=destination_account,
            transaction_type='deposit',
            amount=Decimal(str(amount)),
            description=description,
            balance_after=destination_account.balance,
            payment_method=payment_method,
            related_transaction_id=str(uuid.uuid4())
        )

    return True
class WalletTransfer(models.Model):
    """Model to log transfers between wallet and accountss"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    account = models.ForeignKey(Account, on_delete=models.CASCADE, related_name='wallet_transfers')
    transaction_type = models.CharField(max_length=20, choices=WalletTransaction.TRANSACTION_TYPES)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    description = models.CharField(max_length=255)
    balance_after = models.DecimalField(max_digits=12, decimal_places=2)
    payment_method = models.ForeignKey(
        PaymentMethod, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True
    )
    related_transaction_id = models.CharField(max_length=100, null=True, blank=True)