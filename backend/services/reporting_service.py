from datetime import datetime
from django.db.models import Sum, F
from django.db import models
from backend.ledger.models import Transaction, Split, Account, Budget
from decimal import Decimal

class ReportingService:
    @staticmethod
    def trial_balance(start_date=None, end_date=None):
        query = Split.objects.values('account__name', 'account__account_type')\
            .annotate(balance=Sum('amount'))

        if start_date and end_date:
            query = query.filter(transaction__date__range=[start_date, end_date])

        return query.order_by('account__account_type', 'account__name')

    @staticmethod
    def cashflow_report(start_date, end_date):
        return Split.objects.filter(
            transaction__date__range=[start_date, end_date],
            account__account_type__in=['INCOME', 'EXPENSE']
        ).values(
            'account__name',
            'transaction__date__month'
        ).annotate(
            total=Sum('amount')
        ).order_by('transaction__date__month', 'account__name')

    @staticmethod
    def unnecessary_spending(start_date, end_date):
        return Split.objects.filter(
            transaction__date__range=[start_date, end_date],
            transaction__necessary=False,
            account__account_type='EXPENSE'
        ).values('account__name').annotate(
            total=Sum('amount')
        ).order_by('-total')