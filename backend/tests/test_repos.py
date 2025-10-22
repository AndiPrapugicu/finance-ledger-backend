from django.test import TestCase
from backend.ledger.models import Account, Ledger
from backend.ledger.repos import DjangoAccountsRepo


class AccountsRepoTest(TestCase):
    def setUp(self):
        self.repo = DjangoAccountsRepo()

    def test_create_account(self):
        acc = self.repo.create(
            name="CashTest",
            account_type="ASSET",
            parent=None,
            is_active=True,
        )
        self.assertIsInstance(acc, Account)
        self.assertEqual(acc.name, "CashTest")
        self.assertEqual(acc.account_type, "ASSET")
        self.assertTrue(acc.is_active)

    def test_get_account(self):
        acc = self.repo.create(
            name="BankTest",
            account_type="LIABILITY",
            parent=None,
            is_active=True,
        )
        fetched = self.repo.get(acc.pk)
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.name, "BankTest")
        self.assertEqual(fetched.account_type, "LIABILITY")
