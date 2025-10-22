from django.test import TestCase
from django.utils import timezone
from backend.ledger.models import Budget, Account, Transaction, Split, Alert, Ledger
from decimal import Decimal

class BudgetTests(TestCase):
    def setUp(self):
        self.ledger = Ledger.objects.create()

        # Remove ledger from Account creation
        self.account = Account.objects.create(name="Food", account_type="EXPENSE")

        self.budget = Budget.objects.create(
            ledger=self.ledger,
            account=self.account,  # Use the same account instance
            category="Food",
            amount=1000.0,
            period="monthly"
        )

    def test_budget_alert_triggered(self):
        transaction = Transaction.objects.create(
            date=timezone.now().date(),
            desc="Large grocery purchase",
            ledger=self.ledger
        )

        Split.objects.create(
            transaction=transaction,
            account=self.account,  # Must be the same instance as above
            amount=1200.0
        )
        print(Alert.objects.all())
        self.assertTrue(
            Alert.objects.filter(
                budget=self.budget,
                is_read=False
            ).exists()
        )