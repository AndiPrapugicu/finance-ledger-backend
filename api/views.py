from django.shortcuts import render
from rest_framework.decorators import api_view, parser_classes, permission_classes
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework import status, permissions
from backend.ledger.models import Tag, Account, Transaction as LedgerTransaction, Split, Alert
from backend.services.reporting_service import ReportingService
from django.utils import timezone
from django.db.models import Count, Sum
from datetime import datetime, timedelta
from decimal import Decimal

import yaml
from backend.services.import_service import ImportService

@api_view(['GET'])
@permission_classes([permissions.AllowAny])
def api_root(request):
    """API Root endpoint"""
    return Response({
        'message': 'Ledger API v1.0',
        'endpoints': {
            'dashboard': '/api/dashboard/',
            'accounts': '/api/accounts/',
            'account_detail': '/api/accounts/{id}/',
            'account_hierarchy': '/api/accounts/hierarchy/',
            'create_fixtures': '/api/accounts/fixtures/',
            'import' : '/api/import/',
        }
    })

@api_view(['POST'])
@parser_classes([MultiPartParser, FormParser])
@permission_classes([permissions.IsAuthenticated])
def import_csv(request):
    """
    Endpoint pentru import CSV + rules.
    Va apela ImportService.import_csv și va returna JSON serializabil.
    """
    csv_file = request.FILES.get("csv")
    rules_file = request.FILES.get("rules")

    if not csv_file:
        return Response({"error": "CSV file is required"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        # Get or create user's ledger
        from backend.ledger.models import Ledger
        ledger, created = Ledger.objects.get_or_create(
            username=request.user.username,
            defaults={'username': request.user.username}
        )
        
        # Get asset account name from request or use default
        asset_account_name = request.data.get('asset_account', 'ASSET:Bank Account')
        
        # Pass the authenticated user's ledger_id to the service
        service = ImportService()
        # Support optional 'force' flag from form-data or querystring to force re-import
        force_flag = False
        if request.data.get('force') in ('1', 'true', 'True'):
            force_flag = True
        if request.query_params.get('force') in ('1', 'true', 'True'):
            force_flag = True
        setattr(service, '_force_delete_existing', force_flag)

        result = service.import_csv(
            csv_file, 
            rules_file, 
            ledger_id=ledger.ledgerID,
            asset_account_name=asset_account_name
        )

        data = {
            "created_count": getattr(result, "created_count", None),
            "skipped": getattr(result, "skipped", False),
            "errors": getattr(result, "errors", []),
            "import_record_id": getattr(result.import_record, "id", None) if getattr(result, "import_record", None) else None,
            "ledger_id": ledger.ledgerID
        }

        return Response({"status": "ok", "result": data}, status=status.HTTP_200_OK)
    except Exception as e:
        import traceback
        # Logare pe server recomandată; aici trimitem eroarea în JSON pentru debug
        print(f"[ERROR] Import CSV failed: {e}")
        print(traceback.format_exc())
        return Response({"status": "error", "message": str(e), "traceback": traceback.format_exc()}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
@api_view(['GET'])
@permission_classes([permissions.AllowAny])
def list_tags(request):
    """
    Return a list of all unique tag names
    """
    tags = Tag.objects.all().values_list("name", flat=True)
    return Response(list(tags))

@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def dashboard_data(request):
    """
    Return dashboard summary data for authenticated user
    """
    try:
        # Get user's ledger for proper balance calculation
        from backend.ledger.models import Ledger, Transaction as LedgerTransaction, Split, Account as LedgerAccount
        
        # Use EXACT same logic as list_ledger_transactions endpoint
        from backend.ledger.models import Ledger
        
        try:
            ledger = Ledger.objects.get(username=request.user.username)
        except Ledger.DoesNotExist:
            ledger = None
        
        # Get account counts and balances by type for authenticated user
        account_summary = []
        total_balance = 0
        
        if ledger:
            # Use WalletLedgerService directly to ensure consistency
            from .wallet_ledger_service import WalletLedgerService
            
            wallet_service = WalletLedgerService(request.user)
            calculated_balance = wallet_service.get_balance()
            
            # FORCE the total_balance to be the calculated value
            total_balance = calculated_balance
            
            # Create simple account summary
            account_summary.append({
                'account_type': 'asset',
                'count': 1,
                'balance': calculated_balance
            })
        else:
            # Fallback to Account model if no ledger
            for account_type, display_name in Account.ACCOUNT_TYPE_CHOICES:
                accounts = Account.objects.filter(user=request.user, account_type=account_type, is_active=True)
                count = accounts.count()
                
                account_summary.append({
                    'account_type': account_type.lower(),
                    'count': count,
                    'balance': 0
                })
        
        # Get recent transactions
        recent_transactions = []
        transactions = LedgerTransaction.objects.select_related().prefetch_related('splits').order_by('-date')[:5]
        for transaction in transactions:
            # Calculate total amount from splits
            total_amount = transaction.splits.aggregate(total=Sum('amount'))['total'] or 0
            recent_transactions.append({
                'id': str(transaction.transactionID),
                'description': transaction.desc,
                'date': transaction.date.isoformat(),
                'amount': float(total_amount),
                'is_reconciled': False  # placeholder, adjust based on your logic
            })
        
        # Calculate monthly summary (simplified version)
        today = datetime.now().date()
        current_month_start = today.replace(day=1)
        last_month_start = (current_month_start - timedelta(days=1)).replace(day=1)
        
        # Get income and expense transactions for current and last month
        def get_monthly_data(start_date, end_date, month_name):
            income = 0
            expenses = 0
            
            month_transactions = LedgerTransaction.objects.filter(
                date__gte=start_date,
                date__lt=end_date
            ).prefetch_related('splits__account')
            
            for transaction in month_transactions:
                for split in transaction.splits.all():
                    if split.account.account_type == 'INCOME':
                        income += split.amount
                    elif split.account.account_type == 'EXPENSE':
                        expenses += abs(split.amount)  # Make expenses positive for display
            
            return {
                'month': month_name,
                'income': float(income),
                'expenses': float(expenses),
                'net': float(income - expenses)
            }
        
        monthly_summary = []
        # Current month
        current_month_end = (current_month_start.replace(month=current_month_start.month % 12 + 1) 
                           if current_month_start.month < 12 
                           else current_month_start.replace(year=current_month_start.year + 1, month=1))
        monthly_summary.append(get_monthly_data(
            current_month_start, 
            current_month_end, 
            current_month_start.strftime('%B %Y')
        ))
        
        # Last month
        monthly_summary.append(get_monthly_data(
            last_month_start, 
            current_month_start, 
            last_month_start.strftime('%B %Y')
        ))
        
        # Calculate totals for authenticated user
        total_accounts = Account.objects.filter(user=request.user, is_active=True).count()
        total_transactions = LedgerTransaction.objects.count()
        
        dashboard_data = {
            'total_accounts': total_accounts,
            'total_transactions': total_transactions,
            'total_balance': total_balance,  # Already calculated above
            'account_summary': account_summary,
            'recent_transactions': recent_transactions,
            'monthly_summary': monthly_summary
        }
        
        return Response(dashboard_data)
        
    except Exception as e:
        return Response(
            {'error': f'Failed to fetch dashboard data: {str(e)}'}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
@api_view(['GET'])
def trial_balance(request):
    start_date = request.query_params.get('start_date')
    end_date = request.query_params.get('end_date')
    return Response(ReportingService.trial_balance(start_date, end_date))

@api_view(['GET'])
def cashflow(request):
    start_date = request.query_params.get('start_date')
    end_date = request.query_params.get('end_date')
    return Response(ReportingService.cashflow_report(start_date, end_date))

@api_view(['GET'])
def unnecessary_spending(request):
    start_date = request.query_params.get('start_date')
    end_date = request.query_params.get('end_date')
    return Response(ReportingService.unnecessary_spending(start_date, end_date))

@api_view(['GET'])
def alerts(request):
    return Response(Alert.objects.filter(
        is_read=False,
        created_at__gte=timezone.now() - timedelta(days=30)
    ).values())