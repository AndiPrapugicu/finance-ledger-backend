"""
Ledger Accounts Views
API endpoints for ledger-based accounts with real balances
"""
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from .ledger_accounts_service import LedgerAccountsService


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def ledger_accounts_list(request):
    """
    GET /api/ledger/accounts/
    List all accounts from user's ledger with calculated balances
    """
    try:
        service = LedgerAccountsService(request.user)
        accounts = service.get_accounts_with_balances()
        
        return Response({
            'results': accounts,
            'count': len(accounts)
        }, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({
            'error': f'Failed to fetch accounts: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def ledger_accounts_grouped(request):
    """
    GET /api/ledger/accounts/grouped/
    Get accounts grouped by type (ASSET, LIABILITY, INCOME, EXPENSE) with balances
    """
    try:
        service = LedgerAccountsService(request.user)
        grouped_data = service.get_accounts_grouped_by_type()
        
        return Response(grouped_data, status=status.HTTP_200_OK)
    except Exception as e:
        import traceback
        print(f"[ERROR] ledger_accounts_grouped: {e}")
        print(traceback.format_exc())
        return Response({
            'error': f'Failed to fetch grouped accounts: {str(e)}',
            'traceback': traceback.format_exc()
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def ledger_account_detail(request, account_id):
    """
    GET /api/ledger/accounts/{account_id}/
    Get detailed information for a specific account including recent transactions
    """
    try:
        service = LedgerAccountsService(request.user)
        account_data = service.get_account_detail(account_id)
        
        if account_data is None:
            return Response({
                'error': 'Account not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        return Response(account_data, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({
            'error': f'Failed to fetch account details: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
