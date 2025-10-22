"""
Wallet Service that integrates with Ledger System
Replaces old wallet models with ledger-based transactions
"""
from datetime import datetime
from django.contrib.auth.models import User
from backend.ledger.models import Ledger, Account, Transaction as LedgerTransaction, Split, Tag
from .wallet_models import PaymentMethod, WalletTransaction  # Keep payment methods separate
from decimal import Decimal
from django.core.exceptions import MultipleObjectsReturned
from django.db import transaction
from django.db.utils import IntegrityError
import sqlite3
import time


class WalletLedgerService:
    """Service class to handle wallet operations using ledger system"""
    
    def __init__(self, user: User):
        self.user = user
        # Be resilient to transient DB locks (SQLite) by retrying a few times
        max_attempts = 5
        attempt = 0
        while True:
            try:
                self.ledger, _ = Ledger.objects.get_or_create(
                    username=user.username,
                    defaults={'username': user.username}
                )
                break
            except sqlite3.OperationalError as oe:
                attempt += 1
                if attempt >= max_attempts:
                    print(f"[ERROR] Failed to create ledger for user {user.username} after {attempt} attempts: {oe}")
                    raise ValueError(f"Failed to initialize wallet ledger: {str(oe)}")
                sleep_time = 0.05 * attempt
                print(f"[WARN] SQLite OperationalError when creating ledger for user {user.username}: {oe}. Retrying in {sleep_time}s (attempt {attempt}/{max_attempts})")
                time.sleep(sleep_time)
            except Exception as e:
                print(f"[ERROR] Failed to create ledger for user {user.username}: {e}")
                raise ValueError(f"Failed to initialize wallet ledger: {str(e)}")

        # Create or fetch wallet account with retry on transient DB locks as well
        attempt = 0
        while True:
            try:
                self.wallet_account = self._get_or_create_wallet_account()
                break
            except sqlite3.OperationalError as oe:
                attempt += 1
                if attempt >= max_attempts:
                    print(f"[ERROR] Failed to create wallet account for user {user.username} after {attempt} attempts: {oe}")
                    raise ValueError(f"Failed to initialize wallet account: {str(oe)}")
                sleep_time = 0.05 * attempt
                print(f"[WARN] SQLite OperationalError when creating wallet account for user {user.username}: {oe}. Retrying in {sleep_time}s (attempt {attempt}/{max_attempts})")
                time.sleep(sleep_time)
            except Exception as e:
                print(f"[ERROR] Failed to create wallet account for user {user.username}: {e}")
                raise ValueError(f"Failed to initialize wallet account: {str(e)}")
        
    def _get_or_create_wallet_account(self):
        """Get or create Digital Wallet account in ledger"""
        try:
            # Use an atomic block and handle IntegrityError to be resilient to race conditions
            try:
                with transaction.atomic():
                    account, created = Account.objects.get_or_create(
                        ledger=self.ledger,
                        name="Digital Wallet",
                        defaults={
                            'account_type': "ASSET",
                            'is_active': True
                        }
                    )
                    if created:
                        print(f"[INFO] Created Digital Wallet account for user {self.user.username}")
                    return account
            except IntegrityError:
                # Race: another thread/process created the account concurrently. Fetch the existing one.
                account = Account.objects.filter(ledger=self.ledger, name="Digital Wallet").order_by('accountID').first()
                if account:
                    print(f"[INFO] Resolved Digital Wallet account after IntegrityError for user {self.user.username}: accountID={getattr(account,'accountID',None)}")
                    return account
                # If no account found, re-raise to let outer exception handling deal with it
                raise
        except MultipleObjectsReturned:
            # Defensive: if duplicates exist, pick the earliest one and deactivate others
            try:
                accounts = Account.objects.filter(ledger=self.ledger, name="Digital Wallet").order_by('accountID')
                account = accounts.first()
                print(f"[WARN] Multiple Digital Wallet accounts found for user {self.user.username} (ledger={getattr(self.ledger,'ledgerID',None)}). Keeping account accountID={getattr(account,'accountID',None)} and deactivating {accounts.count()-1} duplicates.")
                for a in accounts[1:]:
                    try:
                        a.is_active = False
                        a.save()
                    except Exception as ex:
                        print(f"[ERROR] Failed to deactivate duplicate account accountID={getattr(a,'accountID',None)}: {ex}")
                return account
            except Exception as ex:
                print(f"[ERROR] While resolving multiple Digital Wallet accounts: {ex}")
                raise
        except Exception as e:
            print(f"[ERROR] Error creating Digital Wallet account: {e}")
            raise
        
    def get_balance(self):
        """Get current wallet balance from ledger transactions"""
        try:
            # Calculate balance from LedgerTransaction system for this user's ledger
            from backend.ledger.models import Transaction as LedgerTransaction, Split, Account as LedgerAccount
            
            # Get all transactions for this user's ledger
            ledger_transactions = LedgerTransaction.objects.filter(ledger=self.ledger)
            
            # Calculate total balance from all ASSET account splits
            total_balance = 0
            for transaction in ledger_transactions:
                asset_splits = transaction.splits.filter(account__account_type='ASSET')
                for split in asset_splits:
                    total_balance += float(split.amount)
            
            return round(total_balance, 2)
        except Exception as e:
            print(f"[DEBUG] Error calculating balance: {e}")
            return 0.0
        
    def add_funds(self, amount: float, description: str = "Funds added", payment_method_id=None):
        """Add funds to wallet using ledger transaction"""
        # Get or create Income account for wallet funding
        income_account, _ = Account.objects.get_or_create(
            ledger=self.ledger,
            name="Wallet Funding",
            defaults={
                'account_type': "INCOME",
                'is_active': True
            }
        )
        
        # Create ledger transaction
        transaction = LedgerTransaction.objects.create(
            ledger=self.ledger,
            date=datetime.now().date(),
            desc=f"Wallet: {description}",
            necessary=False
        )
        
        # Create splits (double-entry)
        # Digital Wallet account gets money (debit)
        Split.objects.create(
            transaction=transaction,
            account=self.wallet_account,
            amount=amount
        )
        
        # Income account gives money (credit - negative)
        Split.objects.create(
            transaction=transaction,
            account=income_account,
            amount=-amount
        )
        
        # Create old-style transaction record for compatibility
        new_balance = self.get_balance()
        wallet_transaction = WalletTransaction.objects.create(
            wallet_id=self._get_legacy_wallet_id(),
            amount=Decimal(str(amount)),
            transaction_type='deposit',
            description=description,
            status='completed',
            balance_after=Decimal(str(new_balance)),
            payment_method_id=payment_method_id
        )
        
        return {
            'ledger_transaction': transaction,
            'wallet_transaction': wallet_transaction,
            'new_balance': self.get_balance()
        }
        
    def spend_funds(self, amount: float, description: str = "Payment", category: str = "General"):
        """Spend funds from wallet using ledger transaction"""
        current_balance = self.get_balance()
        if current_balance < amount:
            raise ValueError(f"Insufficient funds. Available: ${current_balance}, Required: ${amount}")
            
        # Get or create Expense account for wallet spending
        expense_account, _ = Account.objects.get_or_create(
            ledger=self.ledger,
            name=f"Wallet - {category}",
            defaults={
                'account_type': "EXPENSE",
                'is_active': True
            }
        )
        
        # Create ledger transaction
        transaction = LedgerTransaction.objects.create(
            ledger=self.ledger,
            date=datetime.now().date(),
            desc=f"Wallet: {description}",
            necessary=False
        )
        
        # Create splits (double-entry)
        # Expense account gets money (debit)
        Split.objects.create(
            transaction=transaction,
            account=expense_account,
            amount=amount
        )
        
        # Digital Wallet account loses money (credit - negative)
        Split.objects.create(
            transaction=transaction,
            account=self.wallet_account,
            amount=-amount
        )
        
        # Create old-style transaction record for compatibility
        new_balance = self.get_balance()
        wallet_transaction = WalletTransaction.objects.create(
            wallet_id=self._get_legacy_wallet_id(),
            amount=Decimal(str(amount)),
            transaction_type='withdrawal',
            description=description,
            status='completed',
            balance_after=Decimal(str(new_balance))
        )
        
        return {
            'ledger_transaction': transaction,
            'wallet_transaction': wallet_transaction,
            'new_balance': self.get_balance()
        }
        
    def get_transactions(self, limit=10):
        """Get wallet transactions from ledger (all user transactions)"""
        # Get all transactions for this user's ledger instead of just wallet account
        try:
            from backend.ledger.models import Transaction as LedgerTransaction, Split, Account as LedgerAccount
            
            # Get all transactions for this user's ledger
            ledger_transactions = LedgerTransaction.objects.filter(ledger=self.ledger).order_by('-date')
            
            transactions = []
            for transaction in ledger_transactions[:limit]:
                splits = transaction.splits.all()
                
                # Calculate transaction amount (use absolute value of largest split)
                transaction_amount = max(abs(float(split.amount)) for split in splits) if splits else 0
                
                # Determine transaction type by looking at account types and amounts
                expense_income_splits = splits.filter(account__account_type__in=['EXPENSE', 'INCOME'])
                if expense_income_splits.exists():
                    # For EXPENSE/INCOME transactions, check the ASSET split to determine direction
                    asset_splits = splits.filter(account__account_type='ASSET')
                    if asset_splits.exists():
                        asset_amount = sum(float(split.amount) for split in asset_splits)
                        # If assets increased, it's income; if decreased, it's expense
                        if asset_amount > 0:
                            transaction_type = 'income'  # Money came into assets (salary, etc.)
                        else:
                            transaction_type = 'expense'  # Money left assets (grocery, etc.)
                    else:
                        # Fallback: check the expense/income split direction
                        first_split = expense_income_splits.first()
                        if first_split.account.account_type == 'EXPENSE' and first_split.amount > 0:
                            transaction_type = 'expense'
                        elif first_split.account.account_type == 'INCOME' and first_split.amount < 0:
                            transaction_type = 'income'
                        else:
                            transaction_type = 'expense'  # Default for expense/income transactions
                else:
                    # For transfers, check if assets increased or decreased
                    asset_splits = splits.filter(account__account_type='ASSET')
                    if asset_splits.exists():
                        total_asset_change = sum(float(split.amount) for split in asset_splits)
                        transaction_type = 'deposit' if total_asset_change > 0 else 'withdrawal'
                    else:
                        transaction_type = 'expense'  # Default fallback
                
                transactions.append({
                    'id': transaction.transactionID,
                    'transaction_type': transaction_type,
                    'amount': transaction_amount,
                    'description': transaction.desc,
                    'date': transaction.date.isoformat(),
                    'status': 'completed',
                    'created_at': transaction.date.isoformat(),
                    'metadata': {
                        'transaction_id': transaction.transactionID,
                        'necessary': transaction.necessary,
                        'tags': [tag.name for tag in transaction.tags.all()],
                        'splits_count': splits.count()
                    }
                })
            
            return transactions
        except Exception as e:
            print(f"[DEBUG] Error getting transactions: {e}")
            return []
        
    def get_summary(self):
        """Get wallet summary from ledger"""
        balance = self.get_balance()
        
        # Get month-to-date transactions
        from django.utils import timezone
        current_month_start = timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        
        month_splits = Split.objects.filter(
            account=self.wallet_account,
            transaction__date__gte=current_month_start.date()
        )
        
        monthly_income = sum(split.amount for split in month_splits if split.amount > 0)
        monthly_expenses = abs(sum(split.amount for split in month_splits if split.amount < 0))
        
        return {
            'balance': balance,
            'available_balance': balance,
            'currency': 'USD',
            'monthly_income': monthly_income,
            'monthly_expenses': monthly_expenses,
            'monthly_net': monthly_income - monthly_expenses
        }
        
    def _get_legacy_wallet_id(self):
        """Get or create legacy wallet ID for compatibility"""
        from .wallet_models import Wallet
        wallet, _ = Wallet.objects.get_or_create(user=self.user)
        return wallet.id
        
    def sync_legacy_wallet_balance(self):
        """Sync old wallet balance with ledger balance"""
        from .wallet_models import Wallet
        try:
            old_wallet = Wallet.objects.get(user=self.user)
            ledger_balance = self.get_balance()
            old_balance = float(old_wallet.balance)
            
            # Update old wallet to match ledger
            old_wallet.balance = Decimal(str(ledger_balance))
            old_wallet.save()
            
            return {
                'old_balance': old_balance,
                'new_balance': ledger_balance,
                'synced': True
            }
        except Wallet.DoesNotExist:
            return {'synced': False, 'error': 'No legacy wallet found'}
    
    def transfer_funds(self, amount: float, description: str, target_account_id: int):
        """Transfer funds between accounts using ledger system"""
        from backend.ledger.models import Account as LedgerAccount
        
        try:
            # Get source account (user's main wallet account)
            source_account = self.wallet_account
            
            # Get target account by ID
            target_account = LedgerAccount.objects.get(accountID=target_account_id, is_active=True)
            
            # Validate sufficient balance
            current_balance = self.get_balance()
            if current_balance < amount:
                raise ValueError(f"Insufficient funds. Available: ${current_balance}, Required: ${amount}")
            
            # Create ledger transaction for transfer
            transaction = LedgerTransaction.objects.create(
                ledger=self.ledger,
                date=datetime.now().date(),
                desc=f"Transfer: {description}",
                necessary=False
            )
            
            # Create splits for transfer (double-entry)
            # Source account loses money (negative)
            Split.objects.create(
                transaction=transaction,
                account=source_account,
                amount=-amount
            )
            
            # Target account receives money (positive)
            Split.objects.create(
                transaction=transaction,
                account=target_account,
                amount=amount
            )
            
            # Update legacy wallet balance
            self.sync_legacy_wallet_balance()
            
            return {
                'ledger_transaction': transaction,
                'source_account': source_account,
                'target_account': target_account,
                'amount': amount,
                'new_balance': self.get_balance()
            }
            
        except LedgerAccount.DoesNotExist:
            raise ValueError(f"Target account with ID {target_account_id} not found")
        except Exception as e:
            raise ValueError(f"Transfer failed: {str(e)}")