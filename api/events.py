from django.db.models.signals import post_save
from django.dispatch import receiver
from django.db.models import Sum
from backend.ledger.models import Split, Budget, Alert
from decimal import Decimal

class BudgetAlertService:
    @staticmethod
    def check_budget_exceeded(account_id, amount, date):
        budget = Budget.objects.filter(
            account_id=account_id,
            period='monthly'
        ).first()

        if not budget:
            return

        month_total = Split.objects.filter(
            account_id=account_id,
            transaction__date__month=date.month,
            transaction__date__year=date.year
        ).aggregate(total=Sum('amount'))['total'] or 0

        if month_total > budget.amount:
            Alert.objects.create(
                budget=budget,
                message=f"Budget exceeded for {budget.category}. "
                        f"Limit: {budget.amount}, Current: {month_total}",
                created_at=date
            )

@receiver(post_save, sender=Split)
def check_budget_alerts(sender, instance, created, **kwargs):
    if created and instance.account.account_type == 'EXPENSE':
        BudgetAlertService.check_budget_exceeded(
            instance.account.accountID,
            instance.amount,
            instance.transaction.date
        )