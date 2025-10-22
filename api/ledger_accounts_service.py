"""
Ledger Accounts Service
Provides account data from the ledger system with real balances calculated from transactions
"""
from backend.ledger.models import Ledger, Account as LedgerAccount, Split
from django.db.models import Sum
from decimal import Decimal


class LedgerAccountsService:
    """Service to get accounts from ledger with calculated balances"""
    
    def __init__(self, user):
        self.user = user
        try:
            self.ledger = Ledger.objects.get(username=user.username)
        except Ledger.DoesNotExist:
            # Create ledger if it doesn't exist
            self.ledger = Ledger.objects.create(username=user.username)
    
    def get_accounts_with_balances(self):
        """Get all accounts for user's ledger with calculated balances"""
        accounts = LedgerAccount.objects.filter(
            ledger=self.ledger,
            is_active=True
        ).order_by('account_type', 'name')
        
        result = []
        for account in accounts:
            balance = self._calculate_account_balance(account)
            result.append({
                'id': account.accountID,
                'name': account.name,
                'account_type': account.account_type,
                'balance': float(balance),
                'is_active': account.is_active,
                'parent_id': account.parent.accountID if account.parent else None,
            })
        
        return result
    
    def get_accounts_grouped_by_type(self):
        """Get accounts grouped by type with summary statistics"""
        accounts = self.get_accounts_with_balances()
        
        grouped = {
            'ASSET': [],
            'LIABILITY': [],
            'INCOME': [],
            'EXPENSE': []
        }
        
        totals = {
            'ASSET': 0,
            'LIABILITY': 0,
            'INCOME': 0,
            'EXPENSE': 0
        }
        
        for account in accounts:
            acc_type = account['account_type']
            if acc_type in grouped:
                grouped[acc_type].append(account)
                totals[acc_type] += account['balance']
        
        return {
            'accounts': grouped,
            'totals': totals,
            'total_accounts': len(accounts),
            'active_accounts': len([a for a in accounts if a['balance'] != 0]),
            'account_types_count': {
                'ASSET': len(grouped['ASSET']),
                'LIABILITY': len(grouped['LIABILITY']),
                'INCOME': len(grouped['INCOME']),
                'EXPENSE': len(grouped['EXPENSE'])
            },
            'net_worth': totals['ASSET'] - totals['LIABILITY']
        }
    
    def _calculate_account_balance(self, account):
        """Calculate balance for an account from all its splits"""
        splits = Split.objects.filter(account=account)
        total = splits.aggregate(total=Sum('amount'))['total']
        return Decimal(str(total)) if total else Decimal('0.00')
    
    def get_account_detail(self, account_id):
        """Get detailed information for a specific account"""
        try:
            account = LedgerAccount.objects.get(
                accountID=account_id,
                ledger=self.ledger,
                is_active=True
            )
            
            balance = self._calculate_account_balance(account)
            
            # Get recent transactions for this account
            recent_splits = Split.objects.filter(
                account=account
            ).select_related('transaction').order_by('-transaction__date')[:10]
            
            transactions = []
            for split in recent_splits:
                transactions.append({
                    'transaction_id': split.transaction.transactionID,
                    'date': split.transaction.date.isoformat(),
                    'description': split.transaction.desc,
                    'amount': float(split.amount),
                    'necessary': split.transaction.necessary
                })
            
            return {
                'id': account.accountID,
                'name': account.name,
                'account_type': account.account_type,
                'balance': float(balance),
                'is_active': account.is_active,
                'parent_id': account.parent.accountID if account.parent else None,
                'recent_transactions': transactions,
                'transaction_count': Split.objects.filter(account=account).count()
            }
        except LedgerAccount.DoesNotExist:
            return None
