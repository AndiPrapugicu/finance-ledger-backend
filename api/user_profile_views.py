from rest_framework import status, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from .user_profile_models import UserProfile
from decimal import Decimal
import json

@api_view(['GET', 'PATCH'])
@permission_classes([permissions.IsAuthenticated])
def user_financial_goals_view(request):
    """
    GET: Retrieve user's financial goals
    PATCH: Update user's financial goals
    """
    try:
        profile, created = UserProfile.objects.get_or_create(user=request.user)
        
        if request.method == 'GET':
            return Response({
                'monthly_income_goal': float(profile.monthly_income_goal),
                'monthly_expense_budget': float(profile.monthly_expense_budget),
                'currency': profile.currency,
                'income_goal_enabled': profile.income_goal_enabled,
                'budget_alerts_enabled': profile.budget_alerts_enabled,
            }, status=status.HTTP_200_OK)
        
        elif request.method == 'PATCH':
            data = request.data
            
            # Update goals if provided
            if 'monthly_income_goal' in data:
                profile.monthly_income_goal = Decimal(str(data['monthly_income_goal']))
            
            if 'monthly_expense_budget' in data:
                profile.monthly_expense_budget = Decimal(str(data['monthly_expense_budget']))
            
            if 'currency' in data:
                profile.currency = data['currency']
            
            if 'income_goal_enabled' in data:
                profile.income_goal_enabled = data['income_goal_enabled']
            
            if 'budget_alerts_enabled' in data:
                profile.budget_alerts_enabled = data['budget_alerts_enabled']
            
            profile.save()
            
            return Response({
                'message': 'Financial goals updated successfully',
                'monthly_income_goal': float(profile.monthly_income_goal),
                'monthly_expense_budget': float(profile.monthly_expense_budget),
                'currency': profile.currency,
                'income_goal_enabled': profile.income_goal_enabled,
                'budget_alerts_enabled': profile.budget_alerts_enabled,
            }, status=status.HTTP_200_OK)
            
    except Exception as e:
        return Response({
            'error': f'Server error: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)