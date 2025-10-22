from django.test import TestCase
from django.urls import reverse
from backend.services.export_service import ReportExporter
from api.models import Transaction, Account, Split, Tag
from datetime import date

class ExportTests(TestCase):
    def setUp(self):
        self.account1 = Account.objects.create(name="Checking", account_type="asset")
        self.account2 = Account.objects.create(name="Groceries", account_type="expense")
        self.tag = Tag.objects.create(name="food")

        self.transaction = Transaction.objects.create(
            date=date(2024, 1, 1),
            desc="Grocery shopping"
        )
        Split.objects.create(transaction=self.transaction, account=self.account1, amount=-50.00)
        Split.objects.create(transaction=self.transaction, account=self.account2, amount=50.00)
        self.transaction.tags.add(self.tag)

    def test_csv_export(self):
        response = self.client.get(reverse('export-csv'))
        self.assertEqual(response['Content-Type'], 'text/csv')
        content = b''.join(response.streaming_content).decode('utf-8')
        self.assertIn('Date,Description,Account,Amount,Tags', content)
        self.assertIn('2024-01-01,Grocery shopping,Checking,-50.00,food', content)

    def test_markdown_export(self):
        response = self.client.get(reverse('export-markdown'))
        self.assertEqual(response['Content-Type'], 'text/markdown')
        content = b''.join(response.streaming_content).decode('utf-8')
        self.assertIn('# Transaction Report', content)
        self.assertIn('| Date | Description | Account | Amount | Tags |', content)
        self.assertIn('| 2024-01-01 | Grocery shopping | Checking | -50.00 | food |', content)