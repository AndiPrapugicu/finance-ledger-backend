from rest_framework import status, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from django.db.models import Sum
from django.shortcuts import get_object_or_404
from backend.ledger.models import Budget, Account, Transaction, Split, Ledger
from .serializers import BudgetSerializer
from datetime import datetime, timedelta

@api_view(['DELETE'])
@permission_classes([permissions.IsAuthenticated])
def delete_budget(request, budget_id):
    """
    DELETE /api/budgets/{budget_id}/ - Delete a specific budget
    """
    # Get or create ledger for user
    ledger, created = Ledger.objects.get_or_create(username=request.user.username)

    # Get the budget and ensure it belongs to the user
    budget = get_object_or_404(Budget, budgetID=budget_id, ledger=ledger)

    budget.delete()

    return Response({'message': 'Budget deleted successfully'}, status=status.HTTP_204_NO_CONTENT)

@api_view(['GET', 'POST'])
@permission_classes([permissions.IsAuthenticated])
def budget_list_create(request):
    """
    GET /api/budgets/ - List all budgets for authenticated user
    POST /api/budgets/ - Create new budget for authenticated user
    """
    if request.method == 'GET':
        # Get or create ledger for user
        ledger, created = Ledger.objects.get_or_create(username=request.user.username)
        budgets = Budget.objects.filter(ledger=ledger)
        budget_data = []

        for budget in budgets:
            # Calculate actual spending from transactions
            actual_amount = calculate_actual_spending(budget, request.user)

            # Determine status
            status_value = determine_budget_status(budget.amount, actual_amount)

            budget_data.append({
                'id': str(budget.budgetID),
                'category': budget.category,
                'planned_amount': float(budget.amount),
                'actual_amount': float(actual_amount),
                'period': budget.period,
                'status': status_value
            })

        return Response(budget_data)

    elif request.method == 'POST':
        data = request.data

        # Get or create ledger for user
        ledger, created = Ledger.objects.get_or_create(username=request.user.username)

        budget = Budget.objects.create(
            ledger=ledger,
            category=data['category'],
            amount=data['amount'],
            period=data.get('period', 'monthly')
        )

        actual_amount = calculate_actual_spending(budget, request.user)
        status_value = determine_budget_status(budget.amount, actual_amount)

        budget_response = {
            'id': str(budget.budgetID),
            'category': budget.category,
            'planned_amount': float(budget.amount),
            'actual_amount': float(actual_amount),
            'period': budget.period,
            'status': status_value
        }

        return Response(budget_response, status=status.HTTP_201_CREATED)

@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def create_default_budgets(request):
    """
    POST /api/budgets/create-defaults/ - Create default budgets for new user
    """
    # Get or create ledger for user
    ledger, created = Ledger.objects.get_or_create(username=request.user.username)

    # Check if user already has budgets
    existing_budgets = Budget.objects.filter(ledger=ledger).count()
    if existing_budgets > 0:
        # Return existing budgets instead of creating new ones
        return budget_list_create(request)

    # Create default budgets
    default_budgets = [
        {'category': 'Food & Dining', 'amount': 500, 'period': 'monthly'},
        {'category': 'Transportation', 'amount': 200, 'period': 'monthly'},
        {'category': 'Entertainment', 'amount': 150, 'period': 'monthly'},
    ]

    created_budgets = []
    for budget_data in default_budgets:
        budget = Budget.objects.create(
            ledger=ledger,
            category=budget_data['category'],
            amount=budget_data['amount'],
            period=budget_data['period']
        )

        actual_amount = calculate_actual_spending(budget, request.user)
        status_value = determine_budget_status(budget.amount, actual_amount)

        created_budgets.append({
            'id': str(budget.budgetID),
            'category': budget.category,
            'planned_amount': float(budget.amount),
            'actual_amount': float(actual_amount),
            'period': budget.period,
            'status': status_value
        })

    return Response(created_budgets, status=status.HTTP_201_CREATED)

def calculate_actual_spending(budget, user):
    """Calculate actual spending for a budget category"""
    # Get current month transactions for the category
    today = datetime.now().date()
    month_start = today.replace(day=1)

    # Get user's ledger
    try:
        ledger = Ledger.objects.get(username=user.username)
    except Ledger.DoesNotExist:
        return 0

    # Map budget categories to keyword lists for more robust matching
    category_keywords = {
        'Food & Dining': [
            'grocery', 'grocer', 'groceries', 'food', 'dining', 'restaurant', 'supermarket', 'supermart',
            'mart', 'cafe', 'coffee', 'lunch', 'deli', 'bistro', 'meal', 'takeaway', 'take-away', 'delivery',
            'uber eats', 'doordash', 'postmates', 'instacart', 'wholefoods', 'costco', 'aldi', 'lidl', 'tesco'
        ],
        'Transportation': [
            'transport', 'taxi', 'uber', 'lyft', 'bus', 'train', 'metro', 'subway', 'tram', 'rail', 'parking',
            'toll', 'ride', 'fare', 'transit', 'flight', 'airline', 'airport', 'rental', 'car hire', 'taxi fare'
        ],
        'Entertainment': [
            'entertainment', 'stream', 'netflix', 'cinema', 'movie', 'tickets',
            'spotify', 'music', 'concert', 'theatre', 'play', 'game', 'xbox', 'ps', 'steam', 'playstore', 'subscription', 'streamflix'
        ]
    }

    # Get all expense accounts for ledger and filter by keywords if mapping exists
    expense_qs = Account.objects.filter(ledger=ledger, account_type='EXPENSE', is_active=True)

    keywords = category_keywords.get(budget.category)
    if keywords:
        expense_accounts = [a for a in expense_qs if any(kw in (a.name or '').lower() for kw in keywords)]
    else:
        # Fallback: use the old simple matching on the first word
        first_word = budget.category.split()[0] if budget.category else ''
        expense_accounts = list(expense_qs.filter(name__icontains=first_word))

    if not expense_accounts:
        return 0

    # Calculate total spending from splits
    # If expense_accounts is a queryset we passed above, ensure it's a list of account instances or ids
    account_ids = [a.accountID if hasattr(a, 'accountID') else getattr(a, 'id', None) for a in expense_accounts]

    total_spending = Split.objects.filter(
        account__accountID__in=account_ids,
        transaction__date__gte=month_start,
        transaction__date__lte=today,
        transaction__ledger=ledger
    ).aggregate(total=Sum('amount'))['total'] or 0

    return abs(total_spending)  # Make positive for display

def determine_budget_status(planned_amount, actual_amount):
    """Determine budget status based on spending"""
    if actual_amount == 0:
        return "under_budget"

    percentage = (actual_amount / planned_amount) * 100

    if percentage > 100:
        return "over_budget"
    elif percentage >= 80:
        return "on_track"
    else:
        return "under_budget"