from rest_framework import generics, status, permissions
from rest_framework.response import Response
from rest_framework.decorators import api_view, permission_classes
from django.shortcuts import get_object_or_404
from .models import Account
from .serializers import AccountSerializer, AccountCreateSerializer
from .pagination import StandardResultsSetPagination

class AccountListCreateView(generics.ListCreateAPIView):
    """
    GET /api/accounts/ - List all accounts (with pagination)
    POST /api/accounts/ - Create new account
    """
    pagination_class = StandardResultsSetPagination
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        """Return only accounts for the authenticated user"""
        return Account.objects.filter(user=self.request.user).order_by('name')
    
    def get_serializer_class(self):
        if self.request.method == 'POST':
            return AccountCreateSerializer
        return AccountSerializer
    
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            account = serializer.save()
            response_serializer = AccountSerializer(account)
            return Response(response_serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class AccountDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    GET /api/accounts/{id}/ - Get account details
    PUT /api/accounts/{id}/ - Update account
    DELETE /api/accounts/{id}/ - Deactivate account (soft delete)
    """
    serializer_class = AccountSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        """Return only accounts for the authenticated user"""
        return Account.objects.filter(user=self.request.user)
    
    def destroy(self, request, *args, **kwargs):
        """Soft delete - mark as inactive instead of deleting"""
        account = self.get_object()
        if not account.is_active:
            return Response(status=status.HTTP_204_NO_CONTENT)
        account.is_active = False
        account.save(update_fields=['is_active'])
        return Response(status=status.HTTP_204_NO_CONTENT)

@api_view(['GET'])
@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def account_hierarchy(request):
    """
    GET /api/accounts/hierarchy/ - Get accounts in hierarchical structure for authenticated user
    """
    def build_tree(parent=None):
        accounts = Account.objects.filter(
            user=request.user, 
            parent=parent, 
            is_active=True
        )
        result = []
        for account in accounts:
            account_data = AccountSerializer(account).data
            account_data['children'] = build_tree(account)
            result.append(account_data)
        return result
    
    hierarchy = build_tree()
    return Response(hierarchy)

@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def create_fixtures(request):
    """
    POST /api/accounts/fixtures/ - Create sample account data for authenticated user
    """
    fixtures = [
        {'name': 'Assets', 'account_type': 'ASSET'},
        {'name': 'Cash', 'account_type': 'ASSET', 'parent_name': 'Assets'},
        {'name': 'Checking Account', 'account_type': 'ASSET', 'parent_name': 'Cash'},
        {'name': 'Savings Account', 'account_type': 'ASSET', 'parent_name': 'Cash'},
        {'name': 'Liabilities', 'account_type': 'LIABILITY'},
        {'name': 'Credit Cards', 'account_type': 'LIABILITY', 'parent_name': 'Liabilities'},
        {'name': 'Income', 'account_type': 'INCOME'},
        {'name': 'Salary', 'account_type': 'INCOME', 'parent_name': 'Income'},
        {'name': 'Expenses', 'account_type': 'EXPENSE'},
        {'name': 'Food', 'account_type': 'EXPENSE', 'parent_name': 'Expenses'},
        {'name': 'Transportation', 'account_type': 'EXPENSE', 'parent_name': 'Expenses'},
    ]
    
    created_accounts = []
    account_map = {}
    
    # First pass: create parent accounts
    for fixture in fixtures:
        if 'parent_name' not in fixture:
            account, created = Account.objects.get_or_create(
                user=request.user,
                name=fixture['name'],
                defaults={'account_type': fixture['account_type']}
            )
            account_map[fixture['name']] = account
            if created:
                created_accounts.append(account.name)
    
    # Second pass: create child accounts
    for fixture in fixtures:
        if 'parent_name' in fixture:
            parent = account_map.get(fixture['parent_name'])
            if parent:
                account, created = Account.objects.get_or_create(
                    user=request.user,
                    name=fixture['name'],
                    defaults={
                        'account_type': fixture['account_type'],
                        'parent': parent
                    }
                )
                account_map[fixture['name']] = account
                if created:
                    created_accounts.append(account.name)
    
    return Response({
        'message': f'Created {len(created_accounts)} accounts',
        'accounts': created_accounts
    })

@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def create_cli_fixtures(request):
    """
    POST /api/accounts/cli-fixtures/ - Create sample account data for CLI (no auth required)
    """
    from django.contrib.auth.models import User
    
    # Get or create CLI user
    cli_user, created = User.objects.get_or_create(
        username='cli_user',
        defaults={
            'email': 'cli@example.com',
            'first_name': 'CLI',
            'last_name': 'User'
        }
    )
    
    fixtures = [
        {'name': 'Assets', 'account_type': 'ASSET'},
        {'name': 'Cash', 'account_type': 'ASSET', 'parent_name': 'Assets'},
        {'name': 'Checking Account', 'account_type': 'ASSET', 'parent_name': 'Cash'},
        {'name': 'Savings Account', 'account_type': 'ASSET', 'parent_name': 'Cash'},
        {'name': 'Liabilities', 'account_type': 'LIABILITY'},
        {'name': 'Credit Cards', 'account_type': 'LIABILITY', 'parent_name': 'Liabilities'},
        {'name': 'Income', 'account_type': 'INCOME'},
        {'name': 'Salary', 'account_type': 'INCOME', 'parent_name': 'Income'},
        {'name': 'Expenses', 'account_type': 'EXPENSE'},
        {'name': 'Food', 'account_type': 'EXPENSE', 'parent_name': 'Expenses'},
        {'name': 'Transportation', 'account_type': 'EXPENSE', 'parent_name': 'Expenses'},
    ]
    
    created_accounts = []
    account_map = {}
    
    # First pass: create parent accounts
    for fixture in fixtures:
        if 'parent_name' not in fixture:
            account, created = Account.objects.get_or_create(
                name=fixture['name'],
                user=cli_user,
                defaults={
                    'account_type': fixture['account_type']
                }
            )
            account_map[fixture['name']] = account
            if created:
                created_accounts.append(account.name)
    
    # Second pass: create child accounts
    for fixture in fixtures:
        if 'parent_name' in fixture:
            parent = account_map.get(fixture['parent_name'])
            if parent:
                account, created = Account.objects.get_or_create(
                    name=fixture['name'],
                    user=cli_user,
                    defaults={
                        'account_type': fixture['account_type'],
                        'parent': parent
                    }
                )
                account_map[fixture['name']] = account
                if created:
                    created_accounts.append(account.name)
    
    return Response({
        'message': f'Created {len(created_accounts)} accounts for CLI',
        'accounts': created_accounts
    })

@api_view(['GET'])
@permission_classes([permissions.AllowAny])
def list_cli_accounts(request):
    """
    GET /api/accounts/cli-list/ - List all accounts for CLI (no auth required)
    """
    from django.contrib.auth.models import User
    
    try:
        cli_user = User.objects.get(username='cli_user')
        accounts = Account.objects.filter(is_active=True, user=cli_user).order_by('name')
        serializer = AccountSerializer(accounts, many=True)
        return Response(serializer.data)
    except User.DoesNotExist:
        return Response([])