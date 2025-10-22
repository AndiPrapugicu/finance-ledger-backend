"""
Reports endpoints for D7-D9 - Template Method Pattern + Export functionality

Persoana C - D7-D9 Implementation
GET /reports/{type} endpoint + export endpoints GET /reports/{id}/export?format=csv|md
"""

from django.http import JsonResponse, HttpResponse, StreamingHttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.core.cache import cache
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status, permissions
from rest_framework.decorators import permission_classes
from .temp_models import Account, Transaction as TempTransaction
from backend.ledger.models import Transaction as LedgerTransaction, Split, Account as LedgerAccount
from datetime import datetime, date
from decimal import Decimal
import json
import csv
import io
from abc import ABC, abstractmethod
from backend.services.export_service import ReportExporter


# Template Method Pattern for Reports
class ReportTemplate(ABC):
    """Template Method Pattern for different report types"""
    
    def generate_report(self, filters=None, user=None):
        """Template method - defines the algorithm structure"""
        self.user = user  # Store user for use in subclasses
        data = self.fetch_data(filters)
        processed = self.process_data(data)
        formatted = self.format_data(processed)
        return self.finalize_report(formatted)
    
    @abstractmethod
    def fetch_data(self, filters):
        """Fetch raw data for the report"""
        pass
    
    @abstractmethod
    def process_data(self, data):
        """Process and calculate report-specific metrics"""
        pass
    
    def format_data(self, data):
        """Common formatting (can be overridden)"""
        return data
    
    def finalize_report(self, data):
        """Final report structure"""
        return {
            'report_type': self.__class__.__name__.replace('Report', '').lower(),
            'generated_at': datetime.now().isoformat(),
            'data': data
        }


class CashflowReport(ReportTemplate):
    """Cashflow report implementation"""
    
    def fetch_data(self, filters):
        """Fetch transactions and account data from LedgerTransaction system"""
        # Get user's ledger
        user = getattr(self, 'user', None)
        if not user:
            return []
            
        try:
            from backend.ledger.models import Ledger
            ledger = Ledger.objects.get(username=user.username)
        except Ledger.DoesNotExist:
            return []
        
        # Get transactions from LedgerTransaction system  
        transactions_queryset = LedgerTransaction.objects.filter(ledger=ledger)
        
        # Apply filters
        if filters:
            if 'start_date' in filters:
                start_date = datetime.fromisoformat(filters['start_date']).date()
                transactions_queryset = transactions_queryset.filter(date__gte=start_date)
            
            if 'end_date' in filters:
                end_date = datetime.fromisoformat(filters['end_date']).date()
                transactions_queryset = transactions_queryset.filter(date__lte=end_date)
        
        # Convert to expected format
        transactions = []
        for tx in transactions_queryset:
            # Calculate meaningful amount from splits (fix calculation logic)
            splits = tx.splits.all()
            
            # For each transaction, find the expense/income split
            expense_amount = Decimal('0')
            income_amount = Decimal('0')
            main_account_name = 'Unknown'
            
            for split in splits:
                if split.account.account_type in ['EXPENSE']:
                    expense_amount += abs(Decimal(str(split.amount)))
                    main_account_name = split.account.name
                elif split.account.account_type in ['INCOME']:
                    income_amount += abs(Decimal(str(split.amount)))
                    main_account_name = split.account.name
            
            # Determine if it's an inflow or outflow
            if income_amount > 0:
                total_amount = income_amount
                account_id = splits.filter(account__account_type='INCOME').first().account.accountID if splits.filter(account__account_type='INCOME').exists() else None
            elif expense_amount > 0:
                total_amount = -expense_amount  # Negative for expenses
                account_id = splits.filter(account__account_type='EXPENSE').first().account.accountID if splits.filter(account__account_type='EXPENSE').exists() else None
            else:
                # Fallback: use the first non-asset account or largest amount
                non_asset_splits = [s for s in splits if s.account.account_type != 'ASSET']
                if non_asset_splits:
                    primary_split = max(non_asset_splits, key=lambda s: abs(s.amount))
                    total_amount = Decimal(str(primary_split.amount))
                    account_id = primary_split.account.accountID
                    main_account_name = primary_split.account.name
                else:
                    # Pure asset transfer - show as transfer with positive amount
                    asset_splits = list(splits)
                    if len(asset_splits) >= 2:
                        # Find the "from" account (negative) and "to" account (positive)
                        from_split = min(asset_splits, key=lambda s: s.amount)
                        to_split = max(asset_splits, key=lambda s: s.amount)
                        total_amount = abs(Decimal(str(from_split.amount)))
                        account_id = from_split.account.accountID
                        main_account_name = f"Transfer: {from_split.account.name} → {to_split.account.name}"
                    else:
                        total_amount = Decimal('0')
                        account_id = splits[0].account.accountID if splits else None
                        main_account_name = 'Unknown Transfer'
            
            transactions.append({
                'transaction_id': str(tx.transactionID),
                'account_id': account_id,
                'amount': float(total_amount),
                'description': tx.desc,
                'date': tx.date.isoformat(),
                'is_reconciled': True,  # LedgerTransaction are considered reconciled
                'created_at': tx.date.isoformat(),  # Use transaction date
                'account_name': main_account_name
            })
        
        return {
            'transactions': transactions,
            'accounts': [{'id': acc.id, 'name': acc.name, 'account_type': acc.account_type} 
                        for acc in Account.objects.filter(user=user, is_active=True)]
        }
    
    def process_data(self, data):
        """Calculate cashflow metrics"""
        transactions = data['transactions']
        accounts = {acc['id']: acc for acc in data['accounts']}
        
        # Calculate inflows and outflows
        inflows = []
        outflows = []
        net_flow = Decimal('0')
        
        # Group by account type
        account_summaries = {}
        
        for transaction in transactions:
            account_id = transaction['account_id']
            amount = Decimal(str(transaction['amount']))
            account_name = transaction.get('account_name', f'Account {account_id}')
            
            # Track net flow
            net_flow += amount
            
            # Categorize flows
            if amount > 0:
                inflows.append({
                    'date': transaction['date'],
                    'account': account_name,
                    'amount': float(amount),
                    'description': transaction['description']
                })
            else:
                outflows.append({
                    'date': transaction['date'],
                    'account': account_name,
                    'amount': float(abs(amount)),
                    'description': transaction['description']
                })
            
            # Account summaries - simplify since we don't have account_type easily available
            # For now, just track all transactions
            account_type = 'INFLOW' if amount > 0 else 'OUTFLOW'
            if account_type not in account_summaries:
                account_summaries[account_type] = {'total': Decimal('0'), 'count': 0}
            
            account_summaries[account_type]['total'] += amount
            account_summaries[account_type]['count'] += 1
        
        return {
            'summary': {
                'total_inflows': sum(flow['amount'] for flow in inflows),
                'total_outflows': sum(flow['amount'] for flow in outflows),
                'net_flow': float(net_flow),
                'transaction_count': len(transactions)
            },
            'inflows': sorted(inflows, key=lambda x: x['date'], reverse=True),
            'outflows': sorted(outflows, key=lambda x: x['date'], reverse=True),
            'account_summaries': {
                k: {'total': float(v['total']), 'count': v['count']} 
                for k, v in account_summaries.items()
            }
        }


class BalanceSheetReport(ReportTemplate):
    """Balance sheet report implementation"""
    
    def fetch_data(self, filters):
        """Fetch accounts and their balances from LedgerTransaction system"""
        # Get user's ledger
        user = getattr(self, 'user', None)
        if not user:
            return {'accounts': [], 'transactions': []}
            
        try:
            from backend.ledger.models import Ledger
            ledger = Ledger.objects.get(username=user.username)
        except Ledger.DoesNotExist:
            return {'accounts': [], 'transactions': []}
        
        # Get all user-specific accounts (using temp_models.Account which has user association)
        accounts = Account.objects.filter(user=user, is_active=True)
        
        # Get transactions from LedgerTransaction system
        transactions_queryset = LedgerTransaction.objects.filter(ledger=ledger)
        
        # Filter by date if specified
        if filters and 'as_of_date' in filters:
            as_of_date = datetime.fromisoformat(filters['as_of_date']).date()
            transactions_queryset = transactions_queryset.filter(date__lte=as_of_date)
        
        # Calculate balances per account from splits
        print(f"[DEBUG BalanceSheet] Found {accounts.count()} accounts")
        print(f"[DEBUG BalanceSheet] Found {transactions_queryset.count()} transactions")
        
        account_balances = {}
        for account in accounts:
            # Sum all splits for this account from LedgerAccount system
            # Since temp_models.Account doesn't have direct relationship with LedgerAccount,
            # we need to find corresponding LedgerAccount by name
            ledger_account = LedgerAccount.objects.filter(name=account.name).first()
            if not ledger_account:
                account_balances[account.id] = Decimal('0')
                print(f"[DEBUG BalanceSheet] Account {account.name} not found in LedgerAccount system")
                continue
                
            total_balance = Decimal('0')
            splits_count = 0
            for tx in transactions_queryset:
                for split in tx.splits.filter(account=ledger_account):
                    total_balance += Decimal(str(split.amount))
                    splits_count += 1
            account_balances[account.id] = total_balance
            print(f"[DEBUG BalanceSheet] Account {account.name} ({account.account_type}): {splits_count} splits, balance: {total_balance}")
        
        return {
            'accounts': [{'id': acc.id, 'name': acc.name, 'account_type': acc.account_type, 'balance': float(account_balances.get(acc.id, 0))} 
                        for acc in accounts],
            'account_balances': account_balances
        }
    
    def process_data(self, data):
        """Calculate account balances from pre-calculated balances"""
        accounts = {acc['id']: acc for acc in data['accounts']}
        
        # Group by account type
        balance_sheet = {
            'ASSET': [],
            'LIABILITY': [],
            'EQUITY': []
        }
        
        totals = {
            'ASSET': Decimal('0'),
            'LIABILITY': Decimal('0'),
            'EQUITY': Decimal('0')
        }
        
        for account in data['accounts']:
            account_id = account['id']
            balance = Decimal(str(account['balance']))
            account_type = account['account_type']
            
            if account_type in balance_sheet:
                balance_sheet[account_type].append({
                    'id': account_id,
                    'name': account['name'],
                    'balance': float(balance),
                    'parent_id': account.get('parent_id')
                })
                totals[account_type] += balance
        
        return {
            'balance_sheet': balance_sheet,
            'totals': {k: float(v) for k, v in totals.items()},
            'balanced': abs(totals['ASSET'] - totals['LIABILITY'] - totals['EQUITY']) < 0.01
        }


class TrialBalanceReport(ReportTemplate):
    """Trial Balance report implementation"""
    
    def fetch_data(self, filters):
        """Fetch all accounts and transactions"""
        accounts = Account.objects.all()
        transactions_queryset = TempTransaction.objects.all()
        
        # Filter by date if specified
        if filters and 'as_of_date' in filters:
            as_of_date = datetime.fromisoformat(filters['as_of_date']).date()
            transactions_queryset = transactions_queryset.filter(date__lte=as_of_date)
        
        transactions = []
        for tx in transactions_queryset:
            transactions.append({
                'account_id': tx.account.id,
                'amount': float(tx.amount),
                'date': tx.date.isoformat()
            })
        
        return {
            'accounts': list(accounts.values()),
            'transactions': transactions
        }
    
    def process_data(self, data):
        """Calculate trial balance"""
        accounts = {acc['id']: acc for acc in data['accounts']}
        balances = {}
        
        # Initialize balances
        for account in data['accounts']:
            balances[account['id']] = {
                'name': account['name'],
                'account_type': account['account_type'],
                'debit': Decimal('0'),
                'credit': Decimal('0'),
                'balance': Decimal('0')
            }
        
        # Calculate debits and credits
        for transaction in data['transactions']:
            account_id = transaction['account_id']
            amount = Decimal(str(transaction['amount']))
            
            if account_id in balances:
                if amount >= 0:
                    balances[account_id]['debit'] += amount
                else:
                    balances[account_id]['credit'] += abs(amount)
                
                balances[account_id]['balance'] += amount
        
        # Convert to list and calculate totals
        trial_balance = []
        total_debits = Decimal('0')
        total_credits = Decimal('0')
        
        for account_id, balance_data in balances.items():
            trial_balance.append({
                'account_name': balance_data['name'],
                'account_type': balance_data['account_type'],
                'debit': float(balance_data['debit']),
                'credit': float(balance_data['credit']),
                'balance': float(balance_data['balance'])
            })
            total_debits += balance_data['debit']
            total_credits += balance_data['credit']
        
        return {
            'trial_balance': sorted(trial_balance, key=lambda x: x['account_name']),
            'totals': {
                'total_debits': float(total_debits),
                'total_credits': float(total_credits),
                'balanced': abs(total_debits - total_credits) < 0.01
            }
        }


class IncomeStatementReport(ReportTemplate):
    """Income Statement report implementation"""
    
    def fetch_data(self, filters):
        """Fetch income and expense transactions"""
        # Get the user from request context
        user = getattr(self.request, 'user', None) if hasattr(self, 'request') else None
        if not user or not user.is_authenticated:
            return {'accounts': [], 'transactions': []}
            
        accounts = Account.objects.filter(user=user, account_type__in=['INCOME', 'EXPENSE'], is_active=True)
        transactions_queryset = TempTransaction.objects.filter(user=user, account__account_type__in=['INCOME', 'EXPENSE'])
        
        # Apply date filters
        if filters:
            if 'start_date' in filters:
                start_date = datetime.fromisoformat(filters['start_date']).date()
                transactions_queryset = transactions_queryset.filter(date__gte=start_date)
            if 'end_date' in filters:
                end_date = datetime.fromisoformat(filters['end_date']).date()
                transactions_queryset = transactions_queryset.filter(date__lte=end_date)
        
        transactions = []
        for tx in transactions_queryset:
            transactions.append({
                'account_id': tx.account.id,
                'amount': float(tx.amount),
                'date': tx.date.isoformat(),
                'description': tx.description
            })
        
        return {
            'accounts': list(accounts.values()),
            'transactions': transactions
        }
    
    def process_data(self, data):
        """Calculate income statement"""
        accounts = {acc['id']: acc for acc in data['accounts']}
        
        income_accounts = {}
        expense_accounts = {}
        
        # Group by account type
        for transaction in data['transactions']:
            account_id = transaction['account_id']
            amount = Decimal(str(transaction['amount']))
            account = accounts.get(account_id, {})
            account_type = account.get('account_type')
            account_name = account.get('name', f'Account {account_id}')
            
            if account_type == 'INCOME':
                if account_name not in income_accounts:
                    income_accounts[account_name] = Decimal('0')
                income_accounts[account_name] += amount
            elif account_type == 'EXPENSE':
                if account_name not in expense_accounts:
                    expense_accounts[account_name] = Decimal('0')
                expense_accounts[account_name] += abs(amount)  # Expenses as positive
        
        # Calculate totals
        total_income = sum(income_accounts.values())
        total_expenses = sum(expense_accounts.values())
        net_income = total_income - total_expenses
        
        return {
            'income': {k: float(v) for k, v in income_accounts.items()},
            'expenses': {k: float(v) for k, v in expense_accounts.items()},
            'totals': {
                'total_income': float(total_income),
                'total_expenses': float(total_expenses),
                'net_income': float(net_income)
            }
        }


class UnnecessarySpendReport(ReportTemplate):
    """Unnecessary Spend report by category/month"""
    
    def fetch_data(self, filters):
        """Fetch expense transactions with necessity flag"""
        # Get the user from request context
        user = getattr(self.request, 'user', None) if hasattr(self, 'request') else None
        if not user or not user.is_authenticated:
            return {'transactions': []}
            
        # For now, we'll simulate necessity data since it's not in current model
        transactions_queryset = TempTransaction.objects.filter(user=user, amount__lt=0)  # Only expenses
        
        # Apply date filters
        if filters:
            if 'start_date' in filters:
                start_date = datetime.fromisoformat(filters['start_date']).date()
                transactions_queryset = transactions_queryset.filter(date__gte=start_date)
            if 'end_date' in filters:
                end_date = datetime.fromisoformat(filters['end_date']).date()
                transactions_queryset = transactions_queryset.filter(date__lte=end_date)
            if 'month' in filters:
                # Parse month format 2025-09
                year, month = filters['month'].split('-')
                transactions_queryset = transactions_queryset.filter(
                    date__year=int(year), 
                    date__month=int(month)
                )
        
        transactions = []
        accounts = {}
        
        for tx in transactions_queryset:
            # Simulate necessity - spending on "Entertainment", "Dining", "Shopping" is unnecessary
            account_name = tx.account.name.lower()
            is_unnecessary = any(keyword in account_name for keyword in 
                               ['entertainment', 'dining', 'shopping', 'luxury', 'hobby'])
            
            transactions.append({
                'account_id': tx.account.id,
                'account_name': tx.account.name,
                'amount': float(abs(tx.amount)),  # Positive for expenses
                'date': tx.date.isoformat(),
                'description': tx.description,
                'is_unnecessary': is_unnecessary
            })
            
            accounts[tx.account.id] = {
                'name': tx.account.name,
                'account_type': tx.account.account_type
            }
        
        return {
            'transactions': transactions,
            'accounts': accounts
        }
    
    def process_data(self, data):
        """Calculate unnecessary spending by category and month"""
        unnecessary_by_category = {}
        unnecessary_by_month = {}
        total_unnecessary = Decimal('0')
        total_expenses = Decimal('0')
        
        for transaction in data['transactions']:
            amount = Decimal(str(transaction['amount']))
            category = transaction['account_name']
            date_str = transaction['date']
            month_key = date_str[:7]  # YYYY-MM
            
            total_expenses += amount
            
            if transaction['is_unnecessary']:
                total_unnecessary += amount
                
                # By category
                if category not in unnecessary_by_category:
                    unnecessary_by_category[category] = Decimal('0')
                unnecessary_by_category[category] += amount
                
                # By month
                if month_key not in unnecessary_by_month:
                    unnecessary_by_month[month_key] = Decimal('0')
                unnecessary_by_month[month_key] += amount
        
        # Sort and format
        top_categories = sorted(
            unnecessary_by_category.items(), 
            key=lambda x: x[1], 
            reverse=True
        )[:10]
        
        return {
            'by_category': {k: float(v) for k, v in top_categories},
            'by_month': {k: float(v) for k, v in unnecessary_by_month.items()},
            'summary': {
                'total_unnecessary': float(total_unnecessary),
                'total_expenses': float(total_expenses),
                'unnecessary_percentage': float((total_unnecessary / total_expenses * 100) if total_expenses > 0 else 0)
            }
        }


class BudgetVarianceReport(ReportTemplate):
    """Budget Variance report comparing actual vs budgeted amounts"""
    
    def fetch_data(self, filters):
        """Fetch budget data and actual spending"""
        from backend.ledger.models import Budget
        
        # Get budget data - for now we'll work with the models we have
        # Since Budget model uses different structure, we'll adapt
        try:
            budget_queryset = Budget.objects.all()
            
            # Apply period filter if provided
            if filters and 'period' in filters:
                budget_queryset = budget_queryset.filter(period=filters['period'])
            
            budgets = []
            for budget in budget_queryset:
                budgets.append({
                    'category': budget.category,
                    'budgeted_amount': float(budget.amount),
                    'period': budget.period
                })
        except:
            # If Budget model not accessible, create sample data
            budgets = [
                {'category': 'Food', 'budgeted_amount': 500.0, 'period': 'monthly'},
                {'category': 'Transport', 'budgeted_amount': 200.0, 'period': 'monthly'},
                {'category': 'Entertainment', 'budgeted_amount': 150.0, 'period': 'monthly'},
                {'category': 'Shopping', 'budgeted_amount': 300.0, 'period': 'monthly'},
            ]
        
        # Get actual spending data
        # Get the user from request context
        user = getattr(self.request, 'user', None) if hasattr(self, 'request') else None
        if not user or not user.is_authenticated:
            return {'budgets': budgets, 'transactions': []}
            
        transactions_queryset = TempTransaction.objects.filter(user=user, amount__lt=0)  # Only expenses
        
        # Apply date filters for actual spending
        if filters:
            if 'start_date' in filters:
                start_date = datetime.fromisoformat(filters['start_date']).date()
                transactions_queryset = transactions_queryset.filter(date__gte=start_date)
            if 'end_date' in filters:
                end_date = datetime.fromisoformat(filters['end_date']).date()
                transactions_queryset = transactions_queryset.filter(date__lte=end_date)
            if 'month' in filters:
                # Parse month format 2025-09
                year, month = filters['month'].split('-')
                transactions_queryset = transactions_queryset.filter(
                    date__year=int(year), 
                    date__month=int(month)
                )
        
        actual_spending = {}
        for tx in transactions_queryset:
            # Map account names to budget categories
            account_name = tx.account.name.lower()
            category = self._map_account_to_category(account_name)
            
            if category not in actual_spending:
                actual_spending[category] = 0.0
            actual_spending[category] += float(abs(tx.amount))
        
        return {
            'budgets': budgets,
            'actual_spending': actual_spending
        }
    
    def _map_account_to_category(self, account_name):
        """Map account names to budget categories"""
        mapping = {
            'food': 'Food',
            'groceries': 'Food',
            'restaurant': 'Food',
            'dining': 'Food',
            'transport': 'Transport',
            'gas': 'Transport',
            'fuel': 'Transport',
            'uber': 'Transport',
            'taxi': 'Transport',
            'entertainment': 'Entertainment',
            'movie': 'Entertainment',
            'game': 'Entertainment',
            'shopping': 'Shopping',
            'clothes': 'Shopping',
            'amazon': 'Shopping',
        }
        
        for keyword, category in mapping.items():
            if keyword in account_name:
                return category
        
        return 'Other'
    
    def process_data(self, data):
        """Calculate budget variances"""
        variances = []
        total_budgeted = Decimal('0')
        total_actual = Decimal('0')
        total_variance = Decimal('0')
        
        # Create a dictionary of actual spending by category
        actual_by_category = data['actual_spending']
        
        for budget in data['budgets']:
            category = budget['category']
            budgeted = Decimal(str(budget['budgeted_amount']))
            actual = Decimal(str(actual_by_category.get(category, 0.0)))
            variance = actual - budgeted
            variance_percentage = float((variance / budgeted * 100) if budgeted > 0 else 0)
            
            variances.append({
                'category': category,
                'budgeted_amount': float(budgeted),
                'actual_amount': float(actual),
                'variance': float(variance),
                'variance_percentage': variance_percentage,
                'period': budget['period'],
                'status': 'over' if variance > 0 else 'under' if variance < 0 else 'on_target'
            })
            
            total_budgeted += budgeted
            total_actual += actual
            total_variance += variance
        
        # Check for spending in categories without budgets
        for category, amount in actual_by_category.items():
            if not any(b['category'] == category for b in data['budgets']):
                variances.append({
                    'category': category,
                    'budgeted_amount': 0.0,
                    'actual_amount': float(amount),
                    'variance': float(amount),
                    'variance_percentage': 0.0,
                    'period': 'monthly',
                    'status': 'no_budget'
                })
                total_actual += Decimal(str(amount))
                total_variance += Decimal(str(amount))
        
        # Sort by variance (highest over-budget first)
        variances.sort(key=lambda x: x['variance'], reverse=True)
        
        return {
            'variances': variances,
            'summary': {
                'total_budgeted': float(total_budgeted),
                'total_actual': float(total_actual),
                'total_variance': float(total_variance),
                'overall_variance_percentage': float((total_variance / total_budgeted * 100) if total_budgeted > 0 else 0)
            }
        }


# Report instances
REPORT_TYPES = {
    'cashflow': CashflowReport(),
    'balance_sheet': BalanceSheetReport(),
    'trial_balance': TrialBalanceReport(),
    'income_statement': IncomeStatementReport(),
    'unnecessary_spend': UnnecessarySpendReport(),
    'budget_variance': BudgetVarianceReport()
}

# User-specific report storage using cache with user prefix
GENERATED_REPORTS = {}

def get_user_report_key(user, report_id):
    """Generate user-specific cache key for reports"""
    return f"user_{user.id}_{report_id}" if user else report_id

def get_generated_reports(user=None):
    """Get reports for specific user"""
    if user:
        user_prefix = f"user_{user.id}_"
        return {key.replace(user_prefix, ''): value 
                for key, value in GENERATED_REPORTS.items() 
                if key.startswith(user_prefix)}
    return GENERATED_REPORTS

def set_generated_report(report_id, report_data, user=None):
    """Store report with user-specific key"""
    cache_key = get_user_report_key(user, report_id)
    print(f"[DEBUG set_generated_report] Storing report: {cache_key}")
    print(f"[DEBUG set_generated_report] Data keys: {list(report_data.keys()) if isinstance(report_data, dict) else 'Not dict'}")
    GENERATED_REPORTS[cache_key] = report_data
    print(f"[DEBUG set_generated_report] Total reports now: {len(GENERATED_REPORTS)}")


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def export_report_direct(request, format_type):
    """
    GET /api/reports/export/{format}/
    Generate and export report directly based on CLI-style parameters
    """
    try:
        # Parse CLI-style parameters
        report_type = request.GET.get('report', request.GET.get('report_type', 'cashflow'))
        start_date = request.GET.get('from')
        end_date = request.GET.get('to')
        account_filter = request.GET.get('account')
        tag_filter = request.GET.get('tag')
        
        # Validate format
        if format_type not in ['csv', 'markdown', 'md']:
            return Response({
                'error': f'Unsupported format: {format_type}. Supported: csv, markdown'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Build filters
        filters = {}
        if start_date:
            filters['start_date'] = start_date
        if end_date:
            filters['end_date'] = end_date
        if tag_filter:
            filters['tag'] = tag_filter
        
        # Get the report type (default to cashflow if not specified)
        if report_type not in REPORT_TYPES:
            report_type = 'cashflow'
            
        # Generate report
        report_generator = REPORT_TYPES[report_type]
        print(f"[DEBUG export_report_direct] Generating report for type: {report_type}")
        print(f"[DEBUG export_report_direct] User: {request.user}")
        print(f"[DEBUG export_report_direct] Filters: {filters}")
        
        # Handle anonymous user - require authentication
        user = request.user if hasattr(request, 'user') and request.user.is_authenticated else None
        if not user:
            return Response({
                'error': 'Authentication required'
            }, status=status.HTTP_401_UNAUTHORIZED)
        
        report_data = report_generator.generate_report(filters, user=user)
        print(f"[DEBUG export_report_direct] Generated report_data type: {type(report_data)}")
        print(f"[DEBUG export_report_direct] Generated report_data keys: {report_data.keys() if isinstance(report_data, dict) else 'Not a dict'}")
        
        # Export directly based on format
        if format_type == 'csv':
            return export_report_as_csv_direct(report_data, report_type)
        else:  # markdown
            return export_report_as_markdown_direct(report_data, report_type)
            
    except Exception as e:
        return Response({
            'error': f'Export failed: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


def export_report_as_csv_direct(report_data, report_type):
    """Export report directly as CSV"""
    print(f"[DEBUG] Exporting report type: {report_type}")
    print(f"[DEBUG] Report data keys: {report_data.keys() if isinstance(report_data, dict) else 'Not a dict'}")
    print(f"[DEBUG] Report data type: {type(report_data)}")
    if isinstance(report_data, dict) and 'data' in report_data:
        print(f"[DEBUG] report_data['data'] keys: {report_data['data'].keys() if isinstance(report_data['data'], dict) else 'Not a dict'}")
        print(f"[DEBUG] report_data['data'] type: {type(report_data['data'])}")
    print(f"[DEBUG] Report data (truncated): {str(report_data)[:500]}...")
    output = io.StringIO()
    writer = csv.writer(output)
    
    if report_type == 'cashflow':
        # Write headers
        writer.writerow(['Type', 'Date', 'Account', 'Amount', 'Description'])
        
        # Write data - handle multiple data formats
        if 'data' in report_data and isinstance(report_data['data'], dict):
            # Format from generate_report() or nested format
            if 'data' in report_data['data']:
                data = report_data['data']['data']  # Double nested
            else:
                data = report_data['data']  # Single nested
        elif 'inflows' in report_data or 'outflows' in report_data:
            data = report_data  # Direct format
        else:
            data = {}
            
        # Write inflows
        if 'inflows' in data:
            for flow in data['inflows']:
                writer.writerow(['Inflow', flow.get('date', ''), flow.get('account', ''),
                               flow.get('amount', 0), flow.get('description', '')])
        
        # Write outflows  
        if 'outflows' in data:
            for flow in data['outflows']:
                writer.writerow(['Outflow', flow.get('date', ''), flow.get('account', ''),
                               flow.get('amount', 0), flow.get('description', '')])
        
        # Write summary
        if 'summary' in data:
            writer.writerow([])
            writer.writerow(['Summary', '', '', '', ''])
            summary = data['summary']
            writer.writerow(['Total Inflows', '', '', summary.get('total_inflows', 0), ''])
            writer.writerow(['Total Outflows', '', '', summary.get('total_outflows', 0), ''])
            writer.writerow(['Net Flow', '', '', summary.get('net_flow', 0), ''])
    
    elif report_type == 'balance_sheet':
        # Write headers
        writer.writerow(['Account Type', 'Account Name', 'Balance'])
        
        # Write data
        if 'data' in report_data and isinstance(report_data['data'], dict):
            data = report_data['data']
            balance_sheet = data.get('balance_sheet', {})
            
            # Write assets
            if 'ASSET' in balance_sheet:
                writer.writerow(['ASSETS', '', ''])
                for account in balance_sheet['ASSET']:
                    writer.writerow(['', account.get('name', ''), account.get('balance', 0)])
                writer.writerow(['Total Assets', '', data.get('totals', {}).get('ASSET', 0)])
                writer.writerow([])
            
            # Write liabilities
            if 'LIABILITY' in balance_sheet:
                writer.writerow(['LIABILITIES', '', ''])
                for account in balance_sheet['LIABILITY']:
                    writer.writerow(['', account.get('name', ''), account.get('balance', 0)])
                writer.writerow(['Total Liabilities', '', data.get('totals', {}).get('LIABILITY', 0)])
                writer.writerow([])
            
            # Write equity
            if 'EQUITY' in balance_sheet:
                writer.writerow(['EQUITY', '', ''])
                for account in balance_sheet['EQUITY']:
                    writer.writerow(['', account.get('name', ''), account.get('balance', 0)])
                writer.writerow(['Total Equity', '', data.get('totals', {}).get('EQUITY', 0)])
    
    response = HttpResponse(output.getvalue(), content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="{report_type}_export.csv"'
    return response


def export_report_as_markdown_direct(report_data, report_type):
    """Export report directly as Markdown"""
    md_content = f"# {report_type.title()} Report\n\n"
    md_content += f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    
    if report_type == 'cashflow':
        # Handle multiple data formats
        if 'data' in report_data and isinstance(report_data['data'], dict):
            # Format from generate_report() or nested format
            if 'data' in report_data['data']:
                data = report_data['data']['data']  # Double nested
            else:
                data = report_data['data']  # Single nested
        elif 'inflows' in report_data or 'outflows' in report_data:
            data = report_data  # Direct format
        else:
            data = {}
        
        if 'summary' in data:
            summary = data['summary']
            md_content += "## Summary\n\n"
            md_content += f"- **Total Inflows**: ${summary.get('total_inflows', 0):,.2f}\n"
            md_content += f"- **Total Outflows**: ${summary.get('total_outflows', 0):,.2f}\n"
            md_content += f"- **Net Flow**: ${summary.get('net_flow', 0):,.2f}\n"
            md_content += f"- **Transaction Count**: {summary.get('transaction_count', 0)}\n\n"
        
        if 'inflows' in data:
            md_content += "## Inflows\n\n"
            md_content += "| Date | Account | Amount | Description |\n"
            md_content += "|------|---------|--------|-------------|\n"
            for flow in data['inflows']:
                md_content += f"| {flow.get('date', '')} | {flow.get('account', '')} | ${flow.get('amount', 0):,.2f} | {flow.get('description', '')} |\n"
            md_content += "\n"
        
        if 'outflows' in data:
            md_content += "## Outflows\n\n"
            md_content += "| Date | Account | Amount | Description |\n"
            md_content += "|------|---------|--------|-------------|\n"
            for flow in data['outflows']:
                md_content += f"| {flow.get('date', '')} | {flow.get('account', '')} | ${flow.get('amount', 0):,.2f} | {flow.get('description', '')} |\n"
    
    elif report_type == 'balance_sheet':
        # Handle Balance Sheet data format
        if 'data' in report_data and isinstance(report_data['data'], dict):
            # Format from generate_report()
            if 'data' in report_data['data']:
                data = report_data['data']['data']  # Double nested
            else:
                data = report_data['data']  # Single nested
        else:
            data = report_data  # Direct format
        
        if 'balance_sheet' in data:
            balance_sheet = data['balance_sheet']
            totals = data.get('totals', {})
            
            # Assets section
            if 'ASSET' in balance_sheet and balance_sheet['ASSET']:
                md_content += "## Assets\n\n"
                md_content += "| Account | Balance |\n"
                md_content += "|---------|--------:|\n"
                for asset in balance_sheet['ASSET']:
                    md_content += f"| {asset.get('name', '')} | ${asset.get('balance', 0):,.2f} |\n"
                md_content += f"| **Total Assets** | **${totals.get('ASSET', 0):,.2f}** |\n\n"
            
            # Liabilities section  
            if 'LIABILITY' in balance_sheet and balance_sheet['LIABILITY']:
                md_content += "## Liabilities\n\n"
                md_content += "| Account | Balance |\n"
                md_content += "|---------|--------:|\n"
                for liability in balance_sheet['LIABILITY']:
                    md_content += f"| {liability.get('name', '')} | ${liability.get('balance', 0):,.2f} |\n"
                md_content += f"| **Total Liabilities** | **${totals.get('LIABILITY', 0):,.2f}** |\n\n"
            
            # Equity section
            if 'EQUITY' in balance_sheet and balance_sheet['EQUITY']:
                md_content += "## Equity\n\n"
                md_content += "| Account | Balance |\n"
                md_content += "|---------|--------:|\n"
                for equity in balance_sheet['EQUITY']:
                    md_content += f"| {equity.get('name', '')} | ${equity.get('balance', 0):,.2f} |\n"
                md_content += f"| **Total Equity** | **${totals.get('EQUITY', 0):,.2f}** |\n\n"
            
            # Summary
            md_content += "## Summary\n\n"
            md_content += f"- **Total Assets**: ${totals.get('ASSET', 0):,.2f}\n"
            md_content += f"- **Total Liabilities**: ${totals.get('LIABILITY', 0):,.2f}\n"
            md_content += f"- **Total Equity**: ${totals.get('EQUITY', 0):,.2f}\n"
            md_content += f"- **Balanced**: {'✅ Yes' if data.get('balanced', False) else '❌ No'}\n"
    
    response = HttpResponse(md_content, content_type='text/markdown')
    response['Content-Disposition'] = f'attachment; filename="{report_type}_export.md"'
    return response


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def get_report(request, report_type):
    """
    GET /api/reports/{type}
    Generate report of specified type
    """
    try:
        if report_type not in REPORT_TYPES:
            return Response({
                'error': f'Unknown report type: {report_type}',
                'available_types': list(REPORT_TYPES.keys())
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Parse filters from query params
        filters = {}
        if 'start_date' in request.GET:
            filters['start_date'] = request.GET['start_date']
        if 'end_date' in request.GET:
            filters['end_date'] = request.GET['end_date']
        if 'as_of_date' in request.GET:
            filters['as_of_date'] = request.GET['as_of_date']
        if 'tag' in request.GET:
            filters['tag'] = request.GET['tag']
        
        # Generate report using Template Method
        report_generator = REPORT_TYPES[report_type]
        
        # Handle anonymous user - require authentication  
        user = request.user if hasattr(request, 'user') and request.user.is_authenticated else None
        if not user:
            return Response({
                'error': 'Authentication required'
            }, status=status.HTTP_401_UNAUTHORIZED)
        
        report_data = report_generator.generate_report(filters, user=user)
        
        # Store for potential export
        report_id = f"{report_type}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        set_generated_report(report_id, {
            'type': report_type,
            'data': report_data,
            'filters': filters,
            'created_at': datetime.now().isoformat()
        }, user=user)
        
        print(f"[DEBUG] Stored report {report_id} for user {user.id if user else 'anonymous'}")
        print(f"[DEBUG] Total reports in storage: {len(GENERATED_REPORTS)}")
        print(f"[DEBUG] Available reports: {list(GENERATED_REPORTS.keys())}")
        
        return Response({
            'report_id': report_id,
            'report': report_data,
            'export_csv_url': f'/api/reports/export/{report_id}/?format=csv',
            'export_md_url': f'/api/reports/export/{report_id}/?format=md',
            'debug_available_reports': list(GENERATED_REPORTS.keys())
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response({
            'error': f'Report generation failed: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
def test_export(request, report_id):
    """Test endpoint to debug URL routing"""
    return Response({
        'message': f'Test export endpoint reached with report_id: {report_id}',
        'path': request.path,
        'method': request.method,
        'params': dict(request.GET)
    })


@api_view(['GET'])
def simple_test(request):
    """Simple test endpoint"""
    return Response({'message': 'Simple test works!'})


@api_view(['GET'])
@permission_classes([permissions.AllowAny])  # Keep as test endpoint
def test_export_simple(request):
    """Test the full export flow with real data"""
    
    # Create sample cashflow data like auth_views
    test_data = {
        'summary': {
            'total_inflows': 1000.0,
            'total_outflows': 500.0,
            'net_flow': 500.0,
            'transaction_count': 3,
        },
        'inflows': [
            {'date': '2025-10-02', 'account': 'Salary', 'amount': 1000.0, 'description': 'Monthly salary'}
        ],
        'outflows': [
            {'date': '2025-10-02', 'account': 'Housing', 'amount': 500.0, 'description': 'Rent payment'}
        ]
    }
    
    # Store the report
    report_id = 'test_cashflow'
    set_generated_report(report_id, {
        'type': 'cashflow',
        'data': test_data,
        'filters': {},
        'created_at': datetime.now().isoformat()
    }, user=None)  # Test report doesn't need user
    
    # Export it immediately
    return export_report_as_csv_direct(test_data, 'cashflow')


@api_view(['GET'])
@permission_classes([permissions.AllowAny])  # Keep as test endpoint
def test_export_markdown(request):
    """Test the markdown export flow with real data"""
    
    # Create sample cashflow data like auth_views
    test_data = {
        'summary': {
            'total_inflows': 1000.0,
            'total_outflows': 500.0,
            'net_flow': 500.0,
            'transaction_count': 3,
        },
        'inflows': [
            {'date': '2025-10-02', 'account': 'Salary', 'amount': 1000.0, 'description': 'Monthly salary'}
        ],
        'outflows': [
            {'date': '2025-10-02', 'account': 'Housing', 'amount': 500.0, 'description': 'Rent payment'}
        ]
    }
    
    # Export it immediately as Markdown
    return export_report_as_markdown_direct(test_data, 'cashflow')


@csrf_exempt
def export_report(request, report_id):
    """
    GET /reports/{id}/export?format=csv|md
    Export stored report in specified format - UNIFIED VERSION
    """
    try:
        print(f"[DEBUG export_report] Looking for report_id: {report_id}")
        
        # Get user from request
        user = getattr(request, 'user', None) if hasattr(request, 'user') and request.user.is_authenticated else None
        
        # Get the stored report data for this user
        stored_reports = get_generated_reports(user=user)
        print(f"[DEBUG export_report] Available reports for user: {list(stored_reports.keys())}")
        if report_id not in stored_reports:
            return JsonResponse({
                'error': f'Report {report_id} not found'
            }, status=404)
        
        stored_report = stored_reports[report_id]
        report_type = stored_report.get('type', 'cashflow')
        report_data = stored_report.get('data', {})
        
        print(f"[DEBUG export_report] Found report type: {report_type}")
        print(f"[DEBUG export_report] Report data keys: {list(report_data.keys()) if isinstance(report_data, dict) else 'Not dict'}")
        print(f"[DEBUG export_report] Has inflows: {'inflows' in report_data}")
        print(f"[DEBUG export_report] Has outflows: {'outflows' in report_data}")
        
        export_format = request.GET.get('format', 'csv').lower()
        
        if export_format == 'csv':
            return export_report_as_csv_direct(report_data, report_type)
        else:  # markdown
            return export_report_as_markdown_direct(report_data, report_type)
            
    except Exception as e:
        return JsonResponse({
            'error': f'Export failed: {str(e)}'
        }, status=500)


def export_as_csv(report):
    """Export report as CSV"""
    output = io.StringIO()
    writer = csv.writer(output)
    
    report_type = report['type']
    report_data = report['data']['data']
    
    # Write CSV based on report type
    if report_type == 'cashflow':
        # CSV Headers
        writer.writerow(['Type', 'Date', 'Account', 'Amount', 'Description'])
        
        # Write inflows
        for flow in report_data['inflows']:
            writer.writerow(['Inflow', flow['date'], flow['account'], 
                           flow['amount'], flow['description']])
        
        # Write outflows
        for flow in report_data['outflows']:
            writer.writerow(['Outflow', flow['date'], flow['account'], 
                           flow['amount'], flow['description']])
        
        # Summary
        writer.writerow([])
        writer.writerow(['Summary', '', '', '', ''])
        writer.writerow(['Total Inflows', '', '', report_data['summary']['total_inflows'], ''])
        writer.writerow(['Total Outflows', '', '', report_data['summary']['total_outflows'], ''])
        writer.writerow(['Net Flow', '', '', report_data['summary']['net_flow'], ''])
    
    elif report_type == 'balance_sheet':
        # Balance Sheet CSV
        writer.writerow(['Account Type', 'Account Name', 'Balance'])
        
        for account_type, accounts in report_data['balance_sheet'].items():
            for account in accounts:
                writer.writerow([account_type, account['name'], account['balance']])
        
        writer.writerow([])
        writer.writerow(['Totals', '', ''])
        for account_type, total in report_data['totals'].items():
            writer.writerow([account_type, '', total])
    
    elif report_type == 'trial_balance':
        # Trial Balance CSV
        writer.writerow(['Account Name', 'Account Type', 'Debit', 'Credit', 'Balance'])
        
        for account in report_data['trial_balance']:
            writer.writerow([
                account['account_name'],
                account['account_type'],
                account['debit'],
                account['credit'],
                account['balance']
            ])
        
        writer.writerow([])
        writer.writerow(['Totals', '', report_data['totals']['total_debits'], 
                        report_data['totals']['total_credits'], ''])
    
    elif report_type == 'income_statement':
        # Income Statement CSV
        writer.writerow(['Category', 'Type', 'Amount'])
        
        writer.writerow(['=== INCOME ===', '', ''])
        for account, amount in report_data['income'].items():
            writer.writerow([account, 'Income', amount])
        
        writer.writerow(['=== EXPENSES ===', '', ''])
        for account, amount in report_data['expenses'].items():
            writer.writerow([account, 'Expense', amount])
        
        writer.writerow([])
        writer.writerow(['Total Income', '', report_data['totals']['total_income']])
        writer.writerow(['Total Expenses', '', report_data['totals']['total_expenses']])
        writer.writerow(['Net Income', '', report_data['totals']['net_income']])
    
    elif report_type == 'unnecessary_spend':
        # Unnecessary Spend CSV
        writer.writerow(['Category', 'Amount'])
        
        writer.writerow(['=== BY CATEGORY ===', ''])
        for category, amount in report_data['by_category'].items():
            writer.writerow([category, amount])
        
        writer.writerow([])
        writer.writerow(['=== BY MONTH ===', ''])
        for month, amount in report_data['by_month'].items():
            writer.writerow([month, amount])
        
        writer.writerow([])
        writer.writerow(['Total Unnecessary', report_data['summary']['total_unnecessary']])
        writer.writerow(['Total Expenses', report_data['summary']['total_expenses']])
        writer.writerow(['Unnecessary %', f"{report_data['summary']['unnecessary_percentage']:.1f}%"])
    
    response = HttpResponse(output.getvalue(), content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="{report["type"]}_report.csv"'
    return response


def export_as_markdown(report):
    """Export report as Markdown"""
    report_type = report['type']
    report_data = report['data']['data']
    generated_at = report['data']['generated_at']
    
    md_content = f"# {report_type.title().replace('_', ' ')} Report\n\n"
    md_content += f"Generated: {generated_at}\n\n"
    
    if report_type == 'cashflow':
        summary = report_data['summary']
        md_content += "## Summary\n\n"
        md_content += f"- **Total Inflows**: ${summary['total_inflows']:,.2f}\n"
        md_content += f"- **Total Outflows**: ${summary['total_outflows']:,.2f}\n"
        md_content += f"- **Net Flow**: ${summary['net_flow']:,.2f}\n"
        md_content += f"- **Transaction Count**: {summary['transaction_count']}\n\n"
        
        md_content += "## Recent Inflows\n\n"
        md_content += "| Date | Account | Amount | Description |\n"
        md_content += "|------|---------|---------|-------------|\n"
        
        for flow in report_data['inflows'][:10]:  # Top 10
            md_content += f"| {flow['date']} | {flow['account']} | ${flow['amount']:,.2f} | {flow['description']} |\n"
        
        md_content += "\n## Recent Outflows\n\n"
        md_content += "| Date | Account | Amount | Description |\n"
        md_content += "|------|---------|---------|-------------|\n"
        
        for flow in report_data['outflows'][:10]:  # Top 10
            md_content += f"| {flow['date']} | {flow['account']} | ${flow['amount']:,.2f} | {flow['description']} |\n"
    
    elif report_type == 'balance_sheet':
        md_content += "## Balance Sheet\n\n"
        
        for account_type, accounts in report_data['balance_sheet'].items():
            if accounts:
                md_content += f"### {account_type}\n\n"
                md_content += "| Account | Balance |\n"
                md_content += "|---------|----------|\n"
                
                for account in accounts:
                    md_content += f"| {account['name']} | ${account['balance']:,.2f} |\n"
                
                md_content += "\n"
        
        md_content += "## Totals\n\n"
        for account_type, total in report_data['totals'].items():
            md_content += f"- **{account_type}**: ${total:,.2f}\n"
    
    elif report_type == 'trial_balance':
        md_content += "## Trial Balance\n\n"
        md_content += "| Account Name | Account Type | Debit | Credit | Balance |\n"
        md_content += "|--------------|--------------|-------|--------|---------|\n"
        
        for account in report_data['trial_balance']:
            md_content += f"| {account['account_name']} | {account['account_type']} | "
            md_content += f"${account['debit']:,.2f} | ${account['credit']:,.2f} | ${account['balance']:,.2f} |\n"
        
        md_content += "\n## Totals\n\n"
        totals = report_data['totals']
        md_content += f"- **Total Debits**: ${totals['total_debits']:,.2f}\n"
        md_content += f"- **Total Credits**: ${totals['total_credits']:,.2f}\n"
        md_content += f"- **Balanced**: {'✅ Yes' if totals['balanced'] else '❌ No'}\n"
    
    elif report_type == 'income_statement':
        md_content += "## Income Statement\n\n"
        
        md_content += "### Income\n\n"
        md_content += "| Account | Amount |\n"
        md_content += "|---------|--------|\n"
        for account, amount in report_data['income'].items():
            md_content += f"| {account} | ${amount:,.2f} |\n"
        
        md_content += "\n### Expenses\n\n"
        md_content += "| Account | Amount |\n"
        md_content += "|---------|--------|\n"
        for account, amount in report_data['expenses'].items():
            md_content += f"| {account} | ${amount:,.2f} |\n"
        
        md_content += "\n### Summary\n\n"
        totals = report_data['totals']
        md_content += f"- **Total Income**: ${totals['total_income']:,.2f}\n"
        md_content += f"- **Total Expenses**: ${totals['total_expenses']:,.2f}\n"
        md_content += f"- **Net Income**: ${totals['net_income']:,.2f}\n"
    
    elif report_type == 'unnecessary_spend':
        md_content += "## Unnecessary Spending Analysis\n\n"
        
        summary = report_data['summary']
        md_content += "### Summary\n\n"
        md_content += f"- **Total Unnecessary Spending**: ${summary['total_unnecessary']:,.2f}\n"
        md_content += f"- **Total Expenses**: ${summary['total_expenses']:,.2f}\n"
        md_content += f"- **Unnecessary Percentage**: {summary['unnecessary_percentage']:.1f}%\n\n"
        
        md_content += "### By Category\n\n"
        md_content += "| Category | Amount |\n"
        md_content += "|----------|--------|\n"
        for category, amount in report_data['by_category'].items():
            md_content += f"| {category} | ${amount:,.2f} |\n"
        
        md_content += "\n### By Month\n\n"
        md_content += "| Month | Amount |\n"
        md_content += "|-------|--------|\n"
        for month, amount in report_data['by_month'].items():
            md_content += f"| {month} | ${amount:,.2f} |\n"
    
    response = HttpResponse(md_content, content_type='text/markdown')
    response['Content-Disposition'] = f'attachment; filename="{report["type"]}_report.md"'
    return response


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def list_reports(request):
    """List all available reports for the authenticated user"""
    user = getattr(request, 'user', None) if hasattr(request, 'user') and request.user.is_authenticated else None
    generated_reports = get_generated_reports(user=user)
    return Response({
        'available_types': list(REPORT_TYPES.keys()),
        'generated_reports': list(generated_reports.keys()),
        'report_count': len(generated_reports)
    }, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def export_transactions_csv(request):
    filters = {
        'date_from': request.GET.get('from'),
        'date_to': request.GET.get('to'),
        'account_id': request.GET.get('account'),
        'tag': request.GET.get('tag')
    }

    transactions = TempTransaction.objects.filter(user=request.user)
    
    # Apply filters manually
    if filters.get('date_from'):
        transactions = transactions.filter(date__gte=filters['date_from'])
    if filters.get('date_to'):
        transactions = transactions.filter(date__lte=filters['date_to'])
    if filters.get('account_id'):
        transactions = transactions.filter(account_id=filters['account_id'])
    if filters.get('tag'):
        # Note: temp_models.Transaction doesn't have tags, but we'll handle it gracefully
        pass
    exporter = ReportExporter()

    response = StreamingHttpResponse(
        exporter.generate_csv(transactions),
        content_type='text/csv'
    )
    response['Content-Disposition'] = 'attachment; filename="transactions.csv"'
    return response


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def export_transactions_markdown(request):
    filters = {
        'date_from': request.GET.get('from'),
        'date_to': request.GET.get('to'),
        'account_id': request.GET.get('account'),
        'tag': request.GET.get('tag')
    }

    transactions = TempTransaction.objects.filter(user=request.user)
    
    # Apply filters manually
    if filters.get('date_from'):
        transactions = transactions.filter(date__gte=filters['date_from'])
    if filters.get('date_to'):
        transactions = transactions.filter(date__lte=filters['date_to'])
    if filters.get('account_id'):
        transactions = transactions.filter(account_id=filters['account_id'])
    if filters.get('tag'):
        # Note: temp_models.Transaction doesn't have tags, but we'll handle it gracefully
        pass
    exporter = ReportExporter()

    response = StreamingHttpResponse(
        exporter.generate_markdown(transactions),
        content_type='text/markdown'
    )
    response['Content-Disposition'] = 'attachment; filename="transactions.md"'
    return response
