from django.test import TestCase
from backend.ledger.models import Ledger
from backend.services.account_service import AccountService
from backend.ledger.repos import DjangoAccountsRepo

class AccountModelTest(TestCase):

    # fixtures = ['accounts.json']
    def setUp(self):
        self.ledger = Ledger.objects.create(username="testuser")
        self.repo = DjangoAccountsRepo()
        self.service = AccountService(self.repo)

    def test_account_name_required(self):
        with self.assertRaises(Exception):
            self.service.create_account(
             "", "ASSET", None, True
            )

    def test_account_type_choices(self):
        acc = self.service.create_account(
            "Cash", "ASSET", None, True
        )
        self.assertEqual(acc.account_type, "ASSET")
        with self.assertRaises(Exception):
           self.service.create_account(
                "Cash", "iNVALID", None, True
            )