from rest_framework import generics, status, permissions
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.authentication import TokenAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.db import transaction
from .wallet_models import Wallet, PaymentMethod, WalletTransaction
from .wallet_serializers import (
    WalletSerializer, PaymentMethodSerializer, WalletTransactionSerializer,
    AddFundsSerializer, CreatePaymentMethodSerializer, WalletTransferSerializer
)
from .pagination import StandardResultsSetPagination
from .wallet_ledger_service import WalletLedgerService
from backend.ledger.models import Transaction as LedgerTransaction, Split, Ledger
from decimal import Decimal
from .temp_models import Account


class WalletDetailView(generics.RetrieveAPIView):
    """Get user's wallet details using ledger system"""
    serializer_class = WalletSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request, *args, **kwargs):
        try:
            wallet_service = WalletLedgerService(request.user)
            summary = wallet_service.get_summary()
            
            # Sync legacy wallet balance
            wallet_service.sync_legacy_wallet_balance()
            
            # Get legacy wallet for serializer compatibility
            wallet, created = Wallet.objects.get_or_create(user=request.user)
            
            # Return data in expected format
            return Response({
                'id': wallet.id,
                'user': request.user.id,
                'balance': summary['balance'],
                'currency': summary['currency'],
                'available_balance': summary['available_balance'],
                'created_at': wallet.created_at,
                'updated_at': wallet.updated_at,
                'monthly_summary': {
                    'income': summary['monthly_income'],
                    'expenses': summary['monthly_expenses'],
                    'net': summary['monthly_net']
                }
            })
        except Exception as e:
            import traceback
            print(f"[ERROR] WalletDetailView error for user {request.user.username}: {e}")
            print(traceback.format_exc())
            return Response({
                'error': f'Failed to retrieve wallet details: {str(e)}',
                'details': traceback.format_exc()
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def add_funds_view(request):
    """Add funds to user's wallet using ledger system"""
    serializer = AddFundsSerializer(data=request.data)
    
    if serializer.is_valid():
        amount = float(serializer.validated_data['amount'])
        description = serializer.validated_data.get('description', 'Funds added')
        payment_method_id = serializer.validated_data.get('payment_method_id')
        
        # Validate payment method if provided
        payment_method = None
        if payment_method_id:
            try:
                payment_method = PaymentMethod.objects.get(
                    id=payment_method_id, 
                    user=request.user,
                    is_active=True
                )
            except PaymentMethod.DoesNotExist:
                return Response(
                    {'error': 'Payment method not found'}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        try:
            # Use wallet ledger service
            wallet_service = WalletLedgerService(request.user)
            result = wallet_service.add_funds(
                amount=amount,
                description=description,
                payment_method_id=payment_method_id
            )
            
            return Response({
                'message': 'Funds added successfully',
                'transaction_id': result['ledger_transaction'].transactionID,
                'amount': amount,
                'new_balance': result['new_balance'],
                'description': description,
                'payment_method': payment_method.name if payment_method else None
            }, status=status.HTTP_201_CREATED)
            
        except Exception as e:
            return Response(
                {'error': f'Failed to add funds: {str(e)}'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
    
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class PaymentMethodListCreateView(generics.ListCreateAPIView):
    """List and create payment methods"""
    permission_classes = [permissions.IsAuthenticated]
    
    def get_serializer_class(self):
        if self.request.method == 'POST':
            return CreatePaymentMethodSerializer
        return PaymentMethodSerializer
    
    def get_queryset(self):
        return PaymentMethod.objects.filter(
            user=self.request.user,
            is_active=True
        )


class PaymentMethodDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Retrieve, update, or delete a payment method"""
    serializer_class = PaymentMethodSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        return PaymentMethod.objects.filter(user=self.request.user)
    
    def perform_destroy(self, instance):
        """Soft delete by setting is_active to False"""
        instance.is_active = False
        instance.save()


class WalletTransactionListView(generics.ListAPIView):
    """List wallet transactions from ledger system"""
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    
    def get(self, request, *args, **kwargs):
        wallet_service = WalletLedgerService(request.user)
        
        # Get page size from query params
        page_size = int(request.query_params.get('page_size', 20))
        transactions = wallet_service.get_transactions(limit=page_size)
        
        # Format for frontend compatibility
        formatted_transactions = []
        for tx in transactions:
            formatted_transactions.append({
                'id': tx['id'],
                'amount': str(tx['amount']),
                'transaction_type': tx['transaction_type'],
                'description': tx['description'],
                'status': tx['status'],
                'created_at': tx['date'].isoformat() if hasattr(tx['date'], 'isoformat') else str(tx['date']),
                'payment_method': None,  # Can be extended later
                'wallet': self._get_legacy_wallet_id(request.user)
            })
        
        return Response({
            'count': len(formatted_transactions),
            'next': None,  # Simplified pagination
            'previous': None,
            'results': formatted_transactions
        })
    
    def _get_legacy_wallet_id(self, user):
        wallet, _ = Wallet.objects.get_or_create(user=user)
        return wallet.id


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def wallet_summary_view(request):
    """Get wallet summary with statistics using ledger system"""
    try:
        wallet_service = WalletLedgerService(request.user)
        
        # Get summary from ledger
        summary = wallet_service.get_summary()
        
        # Get recent transactions from ledger
        recent_transactions = wallet_service.get_transactions(limit=5)
        
        # Get payment methods count
        payment_methods_count = PaymentMethod.objects.filter(
            user=request.user,
            is_active=True
        ).count()
        
        # Get legacy wallet for compatibility
        wallet, created = Wallet.objects.get_or_create(user=request.user)
        
        # Calculate totals from ledger transactions
        all_transactions = wallet_service.get_transactions(limit=1000)  # Get more for totals
        total_deposits = sum(t['amount'] for t in all_transactions if t['transaction_type'] in ['deposit', 'income'])
        total_withdrawals = sum(t['amount'] for t in all_transactions if t['transaction_type'] in ['withdrawal', 'expense'])
        
        return Response({
            'balance': summary['balance'],
            'currency': summary['currency'],
            'available_balance': summary['available_balance'],
            'total_deposits': total_deposits,
            'total_withdrawals': total_withdrawals,
            'monthly_income': summary['monthly_income'],
            'monthly_expenses': summary['monthly_expenses'],
            'monthly_net': summary['monthly_net'],
            'payment_methods_count': payment_methods_count,
            'recent_transactions': recent_transactions,
            'wallet_created': wallet.created_at,
            'last_transaction': recent_transactions[0]['date'] if recent_transactions else None,
            'ledger_integrated': True
        })
    except Exception as e:
        import traceback
        print(f"[ERROR] wallet_summary_view error for user {request.user.username}: {e}")
        print(traceback.format_exc())
        return Response({
            'error': f'Failed to retrieve wallet summary: {str(e)}',
            'details': traceback.format_exc()
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def set_default_payment_method_view(request, payment_method_id):
    """Set a payment method as default"""
    try:
        payment_method = PaymentMethod.objects.get(
            id=payment_method_id,
            user=request.user,
            is_active=True
        )
        
        # Remove default from all other payment methods
        PaymentMethod.objects.filter(
            user=request.user,
            is_default=True
        ).update(is_default=False)
        
        # Set this one as default
        payment_method.is_default = True
        payment_method.save()
        
        return Response({
            'success': True,
            'message': f'{payment_method.name} set as default payment method'
        })
        
    except PaymentMethod.DoesNotExist:
        return Response(
            {'error': 'Payment method not found'},
            status=status.HTTP_404_NOT_FOUND
        )


@api_view(['GET'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def wallet_transactions_ledger_view(request):
    """Get wallet transactions from LedgerTransaction system"""
    try:
        # Get user's ledger
        try:
            ledger = Ledger.objects.get(username=request.user.username)
        except Ledger.DoesNotExist:
            return Response([], status=status.HTTP_200_OK)
        
        # Get transactions from ledger
        transactions = LedgerTransaction.objects.filter(ledger=ledger).order_by('-date', '-transactionID')
        
        # Convert to wallet-compatible format
        wallet_transactions = []
        for transaction in transactions:
            # Get splits for this transaction
            splits = Split.objects.filter(transaction=transaction)
            
            # For wallet display, we want to show the meaningful amount
            # Look for the largest absolute amount (which represents the transaction amount)
            # In double-entry bookkeeping, we typically have equal and opposite amounts
            amounts = [abs(float(split.amount)) for split in splits]
            transaction_amount = max(amounts) if amounts else 0
            
            # Determine transaction type by looking at account types
            # In double-entry: INCOME accounts get negative amounts, EXPENSE accounts get positive amounts
            expense_income_splits = splits.filter(account__account_type__in=['EXPENSE', 'INCOME'])
            if expense_income_splits.exists():
                # Check if there's an INCOME account (negative amount = income transaction)
                income_split = expense_income_splits.filter(account__account_type='INCOME').first()
                expense_split = expense_income_splits.filter(account__account_type='EXPENSE').first()
                
                if income_split and income_split.amount < 0:
                    transaction_type = 'income'  # Income transaction (salary, etc.)
                elif expense_split and expense_split.amount > 0:
                    transaction_type = 'expense'  # Expense transaction (grocery, etc.)
                else:
                    transaction_type = 'expense'  # Default for expense/income transactions
            else:
                # For transfers between assets/liabilities, check if assets increased or decreased
                asset_splits = splits.filter(account__account_type='ASSET')
                if asset_splits.exists():
                    # If asset amounts are positive, it's a deposit (money in)
                    # If asset amounts are negative, it's a withdrawal (money out)
                    total_asset_change = sum(float(split.amount) for split in asset_splits)
                    transaction_type = 'deposit' if total_asset_change > 0 else 'withdrawal'
                else:
                    transaction_type = 'expense'  # Default fallback
            
            wallet_transactions.append({
                'id': transaction.transactionID,
                'transaction_type': transaction_type,  # Use correct field name
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
        
        return Response(wallet_transactions, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response({
            'error': f'Failed to fetch wallet transactions: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def transfer_funds_view(request):
    """Transfer funds between user's wallet and another account using ledger system"""
    if request.method != 'POST':
        return Response({'error': 'Invalid request method'}, status=status.HTTP_405_METHOD_NOT_ALLOWED)
    
    serializer = WalletTransferSerializer(data=request.data)
    
    if serializer.is_valid():
        amount = float(serializer.validated_data['amount'])
        description = serializer.validated_data.get('description', 'Funds transfer')
        destination_account_id = serializer.validated_data['destinationAccount']
        
        try:
            # Use wallet ledger service
            wallet_service = WalletLedgerService(request.user)
            result = wallet_service.transfer_funds(
                amount=amount,
                description=description,
                target_account_id=destination_account_id
            )
            
            return Response({
                'success': True,
                'message': 'Funds transferred successfully',
                'transaction_id': result['ledger_transaction'].transactionID,
                'amount': amount,
                'new_balance': str(result['new_balance']),
                'description': description,
                'destination_account_id': destination_account_id
            }, status=status.HTTP_201_CREATED)
            
        except Exception as e:
            return Response(
                {'success': False, 'error': f'Failed to transfer funds: {str(e)}'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
    
    return Response({'success': False, 'errors': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

class WalletTransferView(generics.GenericAPIView):
    serializer_class = WalletTransferSerializer
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            sender_wallet = Wallet.objects.get(id=data['walletId'])
            recipient_account = Account.objects.get(id=data['destinationAccount'])
        except Wallet.DoesNotExist:
            return Response({"error": "Wallet not found"}, status=404)
        except Account.DoesNotExist:
            return Response({"error": "Destination account not found"}, status=404)

        payment_method = None
        if data.get('paymentMethod'):
            payment_method = PaymentMethod.objects.filter(
                id=data['paymentMethod'], user=request.user, is_active=True
            ).first()

        try:
            sender_wallet.transfer_funds(
                destination_account=recipient_account,
                amount=data['amount'],
                description=data.get('description', 'Wallet transfer'),
                payment_method=payment_method
            )
        except ValueError as e:
            return Response({"error": str(e)}, status=400)

        return Response({"success": True, "message": "Transfer completed"})

# Import models for the summary view aggregation
from django.db import models