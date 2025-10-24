import traceback
from datetime import datetime
from rest_framework import status, generics, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.authtoken.models import Token
from django.contrib.auth import login, logout
from django.contrib.auth.models import User
from .auth_serializers import (
    UserRegistrationSerializer, 
    UserLoginSerializer, 
    UserProfileSerializer,
    UserAccountSerializer,
    UserTransactionSerializer
)
from .temp_models import Account, Transaction
from .pagination import StandardResultsSetPagination

from django.views.decorators.csrf import csrf_exempt


@api_view(['POST'])
@permission_classes([permissions.AllowAny])
@csrf_exempt
def register_view(request):
    """User registration endpoint with debug-safe error reporting"""
    try:
        serializer = UserRegistrationSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            token, created = Token.objects.get_or_create(user=user)
            return Response({
                'token': token.key,
                'user': UserProfileSerializer(user).data,
                'message': 'Registration successful'
            }, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        # Log traceback on server and return JSON error for easier debugging in deployed env
        tb = traceback.format_exc()
        print(f"[ERROR register_view] {str(e)}")
        print(tb)
        # Return message key so frontend error handling surfaces the server message
        return Response({
            'message': str(e),
            'traceback': tb
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def login_view(request):
    """User login endpoint"""
    serializer = UserLoginSerializer(data=request.data)
    if serializer.is_valid():
        user = serializer.validated_data['user']
        token, created = Token.objects.get_or_create(user=user)
        login(request, user)
        return Response({
            'token': token.key,
            'user': UserProfileSerializer(user).data,
            'message': 'Login successful'
        }, status=status.HTTP_200_OK)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def logout_view(request):
    """User logout endpoint"""
    try:
        # Delete the user's token
        request.user.auth_token.delete()
    except:
        pass
    logout(request)
    return Response({'message': 'Logout successful'}, status=status.HTTP_200_OK)


@api_view(['GET', 'PUT'])
@permission_classes([permissions.IsAuthenticated])
def profile_view(request):
    """User profile endpoint"""
    if request.method == 'GET':
        serializer = UserProfileSerializer(request.user)
        return Response(serializer.data)
    
    elif request.method == 'PUT':
        serializer = UserProfileSerializer(request.user, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def dashboard_data_view(request):
    """Dashboard data for authenticated user - using Ledger System"""
    user = request.user
    
    try:
        from backend.ledger.models import Ledger, Account as LedgerAccount, Transaction as LedgerTransaction, Split
        
        # Get or create user's ledger
        ledger, created = Ledger.objects.get_or_create(
            username=user.username,
            defaults={'username': user.username}
        )
        
        # Get user-specific accounts only from their ledger
        user_accounts = LedgerAccount.objects.filter(ledger=ledger, is_active=True)
        
        # Use same logic as WalletLedgerService for consistent calculation
        # Get all transactions for this user's ledger
        ledger_transactions = LedgerTransaction.objects.filter(ledger=ledger)
        
        # Calculate total balance from all ASSET account splits (same as WalletLedgerService)
        total_balance = 0
        for transaction in ledger_transactions:
            asset_splits = transaction.splits.filter(account__account_type='ASSET')
            for split in asset_splits:
                total_balance += float(split.amount)
        
        total_balance = round(total_balance, 2)
        
        # Calculate account summary (simplified)
        account_summary = {}
        asset_count = 0
        
        for transaction in ledger_transactions:
            for split in transaction.splits.all():
                acc_type = split.account.account_type.lower()
                
                if acc_type not in account_summary:
                    account_summary[acc_type] = {'count': 0, 'balance': 0, 'accounts': set()}
                
                account_summary[acc_type]['balance'] += float(split.amount)
                account_summary[acc_type]['accounts'].add(split.account.accountID)
        
        # Convert to count format
        for acc_type, data in account_summary.items():
            data['count'] = len(data['accounts'])
            del data['accounts']  # Remove set from final data
        
        # Get recent transactions for this user's ledger
        recent_transactions = LedgerTransaction.objects.filter(ledger=ledger).order_by('-date')[:10]
    
        # Convert to list format expected by frontend
        account_summary_list = [
            {
                'account_type': acc_type,
                'count': data['count'],
                'balance': data['balance']
            }
            for acc_type, data in account_summary.items()
        ]
        
        # Calculate monthly summary from ledger transactions
        from datetime import datetime, timedelta
        import calendar
        from django.utils import timezone
        
        monthly_summary = []
        current_date = timezone.now()
        
        for i in range(12):
            # Calculate month boundaries
            if current_date.month - i <= 0:
                target_month = current_date.month - i + 12
                target_year = current_date.year - 1
            else:
                target_month = current_date.month - i
                target_year = current_date.year
                
            month_start = timezone.make_aware(datetime(target_year, target_month, 1))
            if target_month == 12:
                month_end = timezone.make_aware(datetime(target_year + 1, 1, 1)) - timedelta(seconds=1)
            else:
                month_end = timezone.make_aware(datetime(target_year, target_month + 1, 1)) - timedelta(seconds=1)
            
            # Get transactions for this month
            month_transactions = LedgerTransaction.objects.filter(
                ledger=ledger,
                date__gte=month_start.date(),
                date__lte=month_end.date()
            )
            
            total_income = 0
            total_expenses = 0
            
            # Calculate income and expenses from splits
            for transaction in month_transactions:
                splits = Split.objects.filter(transaction=transaction)
                for split in splits:
                    if split.account.account_type == 'INCOME':
                        # Income splits are negative, so we take absolute value
                        total_income += abs(float(split.amount))
                    elif split.account.account_type == 'EXPENSE':
                        # Expense splits are positive, but we want to show as negative
                        total_expenses += float(split.amount)
            
            month_name = calendar.month_abbr[target_month] + " " + str(target_year)
            
            monthly_summary.append({
                'month': month_name,
                'income': total_income,
                'expenses': -total_expenses,  # Negative for expenses
                'net': total_income - total_expenses
            })
        
        # Reverse to get chronological order
        monthly_summary.reverse()
        
        # Prepare recent transactions data
        recent_transactions_list = []
        for trans in recent_transactions:
            # Calculate display amount from splits
            splits = Split.objects.filter(transaction=trans)
            expense_split = splits.filter(account__account_type='EXPENSE').first()
            income_split = splits.filter(account__account_type='INCOME').first()
            
            if expense_split:
                # For expenses, show negative amount
                amount = -abs(float(expense_split.amount))
            elif income_split:
                # For income, show positive amount
                amount = abs(float(income_split.amount))
            else:
                amount = 0
            
            recent_transactions_list.append({
                'id': str(trans.transactionID),
                'description': trans.desc,
                'date': trans.date.isoformat(),
                'amount': amount,
                'is_reconciled': False,
                'source': 'ledger'
            })
        
        # Calculate available balance from Digital Wallet account (unified system)
        digital_wallet_account = LedgerAccount.objects.filter(
            ledger=ledger,
            account_type='ASSET', 
            name='Digital Wallet'
        ).first()
        
        available_balance = 0
        if digital_wallet_account:
            wallet_splits = Split.objects.filter(account=digital_wallet_account)
            available_balance = sum(float(split.amount) for split in wallet_splits)
        
        response_data = {
            'total_accounts': user_accounts.count(),
            'total_transactions': LedgerTransaction.objects.filter(ledger=ledger).count(),
            'total_balance': total_balance,
            'account_summary': account_summary_list,
            'recent_transactions': recent_transactions_list,
            'monthly_summary': monthly_summary,
            'wallet': {
                'balance': available_balance,
                'currency': 'USD',
                'available_balance': available_balance,
            }
        }
        
        # Calculate financial goals and metrics from ledger data
        from .user_profile_models import UserProfile
        try:
            profile = UserProfile.objects.get(user=user)
            income_goal = float(profile.monthly_income_goal)
            monthly_budget = float(profile.monthly_expense_budget)
        except UserProfile.DoesNotExist:
            # Create profile with defaults if it doesn't exist
            profile = UserProfile.objects.create(user=user)
            income_goal = float(profile.monthly_income_goal)
            monthly_budget = float(profile.monthly_expense_budget)
        
        # Calculate current month metrics from ledger
        current_month_start = timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        current_month_transactions = LedgerTransaction.objects.filter(
            ledger=ledger,
            date__gte=current_month_start.date()
        )
        
        monthly_income_total = 0
        monthly_expenses_total = 0
        
        for transaction in current_month_transactions:
            splits = Split.objects.filter(transaction=transaction)
            for split in splits:
                if split.account.account_type == 'INCOME':
                    monthly_income_total += abs(float(split.amount))
                elif split.account.account_type == 'EXPENSE':
                    monthly_expenses_total += float(split.amount)
        
        # Calculate YTD metrics from ledger
        year_start = timezone.now().replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        ytd_transactions = LedgerTransaction.objects.filter(
            ledger=ledger,
            date__gte=year_start.date()
        )
        
        ytd_income_total = 0
        ytd_expenses_total = 0
        
        for transaction in ytd_transactions:
            splits = Split.objects.filter(transaction=transaction)
            for split in splits:
                if split.account.account_type == 'INCOME':
                    ytd_income_total += abs(float(split.amount))
                elif split.account.account_type == 'EXPENSE':
                    ytd_expenses_total += float(split.amount)
        
        # Calculate metrics
        ytd_net = ytd_income_total - ytd_expenses_total
        
        # Calculate savings rate
        if monthly_income_total > 0:
            monthly_savings = monthly_income_total - monthly_expenses_total
            savings_rate = (monthly_savings / monthly_income_total) * 100
        else:
            savings_rate = 0
            monthly_savings = 0
        
        # Calculate variances
        budget_variance = monthly_budget - monthly_expenses_total if monthly_budget > 0 else 0
        budget_variance_percentage = (budget_variance / monthly_budget) * 100 if monthly_budget > 0 else 0
        income_variance = monthly_income_total - income_goal if income_goal > 0 else 0
        income_variance_percentage = (income_variance / income_goal) * 100 if income_goal > 0 else 0
        
        # Calculate progress percentages
        income_progress = min((monthly_income_total / income_goal) * 100, 100) if income_goal > 0 else 0
        expense_progress = (monthly_expenses_total / monthly_budget) * 100 if monthly_budget > 0 else 0
        
        # Add financial goals to response
        response_data['financial_goals'] = {
            'income_goal': income_goal,
            'monthly_budget': monthly_budget,
            'monthly_income': monthly_income_total,
            'monthly_expenses': monthly_expenses_total,
            'income_progress_percentage': round(income_progress, 1),
            'expense_progress_percentage': round(expense_progress, 1),
            'remaining_income_needed': max(0, income_goal - monthly_income_total),
            'remaining_budget': max(0, monthly_budget - monthly_expenses_total),
            'savings_rate': round(savings_rate, 1),
            'monthly_savings': monthly_savings,
            'ytd_income': ytd_income_total,
            'ytd_expenses': ytd_expenses_total,
            'ytd_net': ytd_net,
            'budget_variance': budget_variance,
            'budget_variance_percentage': round(budget_variance_percentage, 1),
            'income_variance': income_variance,
            'income_variance_percentage': round(income_variance_percentage, 1),
        }
        
        # Set net worth as total balance from assets
        response_data['total_net_worth'] = total_balance
        
        return Response(response_data)
        
    except Exception as e:
        # Fallback with error details for debugging
        return Response({
            'error': f'Ledger system error: {str(e)}',
            'total_accounts': 0,
            'total_transactions': 0,
            'total_balance': 0,
            'account_summary': [],
            'recent_transactions': [],
            'monthly_summary': [],
            'financial_goals': {
                'income_goal': 0,
                'monthly_budget': 0,
                'monthly_income': 0,
                'monthly_expenses': 0,
                'income_progress_percentage': 0,
                'expense_progress_percentage': 0,
                'remaining_income_needed': 0,
                'remaining_budget': 0,
                'savings_rate': 0,
                'monthly_savings': 0,
                'ytd_income': 0,
                'ytd_expenses': 0,
                'ytd_net': 0,
                'budget_variance': 0,
                'budget_variance_percentage': 0,
                'income_variance': 0,
                'income_variance_percentage': 0,
            },
            'total_net_worth': 0,
            'traceback': traceback.format_exc()
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    return Response(response_data)


class UserAccountListView(generics.ListCreateAPIView):
    """List and create accounts for authenticated user"""
    serializer_class = UserAccountSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    
    def get_queryset(self):
        return Account.objects.filter(user=self.request.user, is_active=True)
    
    def get_serializer_context(self):
        # Pass request to serializer for `create`
        context = super().get_serializer_context()
        context['request'] = self.request
        return context


class UserTransactionListView(generics.ListCreateAPIView):
    """List and create transactions for authenticated user"""
    serializer_class = UserTransactionSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    
    def get_queryset(self):
        return Transaction.objects.filter(user=self.request.user)
    def get_serializer_context(self):
        # Pass request to serializer for `create`
        context = super().get_serializer_context()
        context['request'] = self.request
        return context


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def user_reports_data_view(request):
    """Reports data filtered by authenticated user with wallet integration"""
    user = request.user
    
    # Use unified LedgerTransaction system instead of old separate systems
    try:
        from backend.ledger.models import Ledger, Transaction as LedgerTransaction
        ledger = Ledger.objects.get(username=user.username)
        ledger_transactions = LedgerTransaction.objects.filter(ledger=ledger)
    except Ledger.DoesNotExist:
        ledger_transactions = LedgerTransaction.objects.none()
    
    # Calculate inflows/outflows from LedgerTransaction splits
    account_inflows = 0
    account_outflows = 0
    
    for tx in ledger_transactions:
        for split in tx.splits.all():
            amount = float(split.amount)
            if split.account.account_type in ['INCOME'] and amount < 0:
                account_inflows += abs(amount)  # Income splits are negative, so abs()
            elif split.account.account_type in ['EXPENSE'] and amount > 0:
                account_outflows += amount  # Expense splits are positive
    
    # Use only LedgerTransaction system totals
    total_inflows = account_inflows
    total_outflows = account_outflows
    
    # Build transaction lists from LedgerTransaction
    inflow_list = []
    outflow_list = []
    
    for tx in ledger_transactions.order_by('-date')[:20]:  # Get recent transactions
        # Find the meaningful amount from splits
        income_amount = 0
        expense_amount = 0
        main_account_name = 'Unknown'
        
        for split in tx.splits.all():
            if split.account.account_type == 'INCOME' and split.amount < 0:
                income_amount = abs(split.amount)  # Income splits are negative
                main_account_name = split.account.name
            elif split.account.account_type == 'EXPENSE' and split.amount > 0:
                expense_amount = split.amount  # Expense splits are positive
                main_account_name = split.account.name
        
        # Add to appropriate list
        if income_amount > 0:
            inflow_list.append({
                'date': tx.date.isoformat(),
                'account': main_account_name,
                'amount': float(income_amount),
                'description': tx.desc,
            })
        elif expense_amount > 0:
            outflow_list.append({
                'date': tx.date.isoformat(),
                'account': main_account_name,
                'amount': float(expense_amount),
                'description': tx.desc,
            })
    
    # Sort by date (most recent first)
    inflow_list.sort(key=lambda x: x['date'], reverse=True)
    outflow_list.sort(key=lambda x: x['date'], reverse=True)
    
    # Unified cashflow data structure using LedgerTransaction
    cashflow_data = {
        'summary': {
            'total_inflows': total_inflows,
            'total_outflows': total_outflows,
            'net_flow': total_inflows - total_outflows,
            'transaction_count': ledger_transactions.count(),
        },
        'inflows': inflow_list[:10],  # Limit to 10 most recent
        'outflows': outflow_list[:10],  # Limit to 10 most recent
    }
    
    report_id = f'cashflow_{user.id}'
    
    # Store report for export (import from reports.py)
    print(f"[DEBUG auth_views] About to store report: {report_id}")
    from .reports import set_generated_report
    set_generated_report(report_id, {
        'type': 'cashflow',
        'data': cashflow_data,
        'filters': {},
        'created_at': datetime.now().isoformat()
    })
    print(f"[DEBUG auth_views] Report stored successfully")
    
    report_data = {
        'report_id': report_id,
        'report': {
            'report_type': 'cashflow',
            'generated_at': datetime.now().isoformat(),
            'data': cashflow_data
        },
        'export_csv_url': f'/api/reports/{report_id}/export/?format=csv',
        'export_md_url': f'/api/reports/{report_id}/export/?format=md',
    }
    
    return Response(report_data)