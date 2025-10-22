from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.utils.decorators import method_decorator
from django.views import View
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework import status, permissions
from .temp_models import Account, Transaction
from .wallet_models import Wallet
from backend.ledger.models import Transaction as LedgerTransaction, Split
import json
from datetime import datetime
from decimal import Decimal
import uuid
from .pagination import paginate_transactions
from backend.ledger.models import Tag

@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def create_transaction(request):
    """
    POST /api/transactions/
    Create a new transaction and sync with wallet
    """
    try:
        data = json.loads(request.body) if isinstance(request.body, bytes) else request.data
        
        # Validate required fields
        required_fields = ['description', 'date', 'amount', 'account_id']
        for field in required_fields:
            if field not in data:
                return Response({
                    'error': f'Missing required field: {field}'
                }, status=status.HTTP_400_BAD_REQUEST)
        
        # Validate account exists and belongs to user
        try:
            account = Account.objects.get(id=data['account_id'], user=request.user)
        except Account.DoesNotExist:
            return Response({
                'error': 'Account not found or access denied'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Create transaction (will automatically sync with wallet via signal)
        transaction = Transaction.objects.create(
            user=request.user,
            account=account,
            date=datetime.fromisoformat(data['date']).date(),
            description=data['description'],
            amount=Decimal(str(data['amount'])),
            category=data.get('category', ''),
            is_reconciled=data.get('is_reconciled', False)
        )
        
        return Response({
            'id': transaction.id,
            'description': transaction.description,
            'date': transaction.date.isoformat(),
            'amount': float(transaction.amount),
            'account_id': transaction.account.id,
            'account_name': transaction.account.name,
            'category': transaction.category,
            'is_reconciled': transaction.is_reconciled,
            'message': 'Transaction created successfully and synced with wallet'
        }, status=status.HTTP_201_CREATED)
        
    except json.JSONDecodeError:
        return Response({
            'error': 'Invalid JSON in request body'
        }, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        return Response({
            'error': f'Server error: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['PATCH'])
@permission_classes([permissions.IsAuthenticated])
def reconcile_transaction(request, transaction_id):
    """
    PATCH /api/transactions/{id}/reconcile
    Toggle reconcile status for a transaction
    """
    try:
        # Find transaction belonging to user
        try:
            transaction = Transaction.objects.get(id=transaction_id, user=request.user)
        except Transaction.DoesNotExist:
            return Response({
                'error': 'Transaction not found or access denied'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Toggle reconcile status
        transaction.is_reconciled = not transaction.is_reconciled
        transaction.save()
        
        return Response({
            'id': transaction.id,
            'is_reconciled': transaction.is_reconciled,
            'message': f'Transaction {"reconciled" if transaction.is_reconciled else "unreconciled"}'
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response({
            'error': f'Server error: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def list_transactions(request):
    """
    GET /api/transactions/list/
    List user's transactions with pagination and filters
    """
    try:
        # Parse pagination parameters
        page = int(request.GET.get('page', 1))
        page_size = min(int(request.GET.get('page_size', 15)), 50)  # Max 50
        
        # Parse filter parameters
        filter_reconciled = request.GET.get('reconciled')
        filter_start_date = request.GET.get('start_date')
        filter_end_date = request.GET.get('end_date')
        search = request.GET.get('search', '').lower()
        
        # Start with user's transactions
        transactions = Transaction.objects.filter(user=request.user)
        
        # Apply filters
        if filter_reconciled is not None:
            is_reconciled = filter_reconciled.lower() == 'true'
            transactions = transactions.filter(is_reconciled=is_reconciled)
        
        if filter_start_date:
            start_date = datetime.fromisoformat(filter_start_date).date()
            transactions = transactions.filter(date__gte=start_date)
        
        if filter_end_date:
            end_date = datetime.fromisoformat(filter_end_date).date()
            transactions = transactions.filter(date__lte=end_date)
        
        if search:
            transactions = transactions.filter(description__icontains=search)
        
        # Order by date (newest first)
        transactions = transactions.order_by('-date', '-created_at')
        
        # Convert to list for pagination
        transactions_list = []
        for t in transactions:
            transactions_list.append({
                'id': t.id,
                'description': t.description,
                'date': t.date.isoformat(),
                'amount': float(t.amount),
                'account_id': t.account.id,
                'account_name': t.account.name,
                'account_type': t.account.account_type,
                'category': t.category,
                'is_reconciled': t.is_reconciled,
                'created_at': t.created_at.isoformat(),
            })
    
        page = int(request.GET.get('page', 1))
        page_size = int(request.GET.get('page_size', 15))
        paginated_data = paginate_transactions(transactions_list, page, page_size)
        
        return JsonResponse(paginated_data)
        
    except Exception as e:
        return Response({
            'error': f'Server error: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['DELETE'])
@permission_classes([permissions.IsAuthenticated])
def delete_transaction(request, transaction_id):
    """
    DELETE /api/transactions/{id}
    Delete a transaction
    """
    try:
        transaction = Transaction.objects.get(id=transaction_id, user=request.user)
        transaction.delete()
        
        return Response({
            'message': 'Transaction deleted successfully'
        }, status=status.HTTP_200_OK)
        
    except Transaction.DoesNotExist:
        return Response({
            'error': 'Transaction not found or access denied'
        }, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({
            'error': f'Server error: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def create_double_entry_transaction(request):
    """
    POST /api/transactions/double-entry/
    Create a double-entry transaction in the ledger system
    """
    try:
        from backend.ledger.models import Ledger, Account as LedgerAccount
        
        # Use request.data directly (already parsed by DRF)
        data = request.data
        
        # Validate required fields
        required_fields = ['desc', 'date', 'splits']
        for field in required_fields:
            if field not in data:
                return Response({
                    'error': f'Missing required field: {field}'
                }, status=status.HTTP_400_BAD_REQUEST)
        
        # Validate splits
        splits = data['splits']
        if not splits or len(splits) < 2:
            return Response({
                'error': 'At least 2 splits are required for double-entry'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Validate splits balance to zero
        total = Decimal('0')
        for split in splits:
            if 'amount' not in split or 'accountId' not in split:
                return Response({
                    'error': 'Each split must have amount and accountId'
                }, status=status.HTTP_400_BAD_REQUEST)
            total += Decimal(str(split['amount']))
        
        if total != Decimal('0'):
            return Response({
                'error': f'Splits must balance to zero. Current total: {total}'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Get or create user's ledger
        ledger, created = Ledger.objects.get_or_create(
            username=request.user.username
        )
        
        # Create transaction
        transaction = LedgerTransaction.objects.create(
            ledger=ledger,
            desc=data['desc'],
            date=datetime.fromisoformat(data['date']).date(),
            necessary=data.get('necessary', True)
        )
        
        # Create splits
        for split_data in splits:
            try:
                account = LedgerAccount.objects.get(accountID=split_data['accountId'])
            except LedgerAccount.DoesNotExist:
                transaction.delete()  # Cleanup
                return Response({
                    'error': f'Account {split_data["accountId"]} not found'
                }, status=status.HTTP_404_NOT_FOUND)
            
            Split.objects.create(
                transaction=transaction,
                account=account,
                amount=Decimal(str(split_data['amount']))
            )
        
        # Handle tags if provided
        if 'tags' in data and data['tags']:
            for tag_name in data['tags']:
                tag, created = Tag.objects.get_or_create(name=tag_name)
                transaction.tags.add(tag)
        
        return Response({
            'message': 'Double-entry transaction created successfully',
            'transactionId': transaction.transactionID
        }, status=status.HTTP_201_CREATED)
        
    except json.JSONDecodeError:
        return Response({
            'error': 'Invalid JSON in request body'
        }, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        return Response({
            'error': f'Server error: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def list_ledger_transactions(request):
    """
    GET /api/transactions/ledger/
    List users double-entry ledger transactions
    """
    try:
        from backend.ledger.models import Ledger
        
        # Get users ledger
        try:
            ledger = Ledger.objects.get(username=request.user.username)
        except Ledger.DoesNotExist:
            # If no ledger exists, return empty list
            return Response({
                "results": [],
                "count": 0,
                "next": None,
                "previous": None
            }, status=status.HTTP_200_OK)
        
        # Get transactions for this ledger
        transactions = LedgerTransaction.objects.filter(ledger=ledger).order_by("-date", "-transactionID")
        
        transactions_list = []
        for transaction in transactions:
            # Get all splits for this transaction
            splits = Split.objects.filter(transaction=transaction)
            splits_data = []
            
            for split in splits:
                splits_data.append({
                    "accountId": split.account.accountID,
                    "amount": str(split.amount),
                    "accountType": split.account.account_type,
                    "accountName": split.account.name
                })
            
            # Get tags
            tags = [tag.name for tag in transaction.tags.all()]
            
            transactions_list.append({
                "id": transaction.transactionID,
                "account_id": splits_data[0]["accountId"] if splits_data else None,  # First split account for compatibility
                "date": transaction.date.isoformat(),
                "desc": transaction.desc,
                "splits": splits_data,
                "tags": tags,
                "necessary": transaction.necessary
            })
        
        return Response({
            "results": transactions_list,
            "count": len(transactions_list),
            "next": None,
            "previous": None
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response({
            "error": f"Server error: {str(e)}"
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["GET"])
@permission_classes([permissions.AllowAny])
def list_ledger_accounts(request):
    """
    GET /api/accounts/ledger/
    List all ledger accounts available for double-entry transactions
    """
    try:
        from backend.ledger.models import Account as LedgerAccount
        
        accounts = LedgerAccount.objects.filter(is_active=True).order_by('account_type', 'name')
        
        accounts_list = []
        for account in accounts:
            accounts_list.append({
                "id": account.accountID,
                "name": account.name,
                "account_type": account.account_type,
                "parent": account.parent.accountID if account.parent else None,
                "is_active": account.is_active
            })
        
        return Response(accounts_list, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response({
            "error": f"Server error: {str(e)}"
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

