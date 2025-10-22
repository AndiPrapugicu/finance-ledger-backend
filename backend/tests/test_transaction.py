from django.test import TestCase
from backend.services.transaction_service import TransactionService
from backend.ledger.repos import DjangoTransactionsRepo, DjangoAccountsRepo
from backend.services.account_service import AccountService
from backend.ledger.models import Ledger, Splits


class TestTranscationModel(TestCase):
    def setUp(self):
        self.repo =DjangoTransactionsRepo()
        self.acc_repo=DjangoAccountsRepo()
        self.acc_service = AccountService(self.acc_repo)
        self.tr_service = TransactionService(self.repo)
        self.ledger = Ledger.objects.create(username="testuser")
        self.account1 = self.acc_service.create_account(
             "Cash", "ASSET", None, True
        )
    
    def test_create_transaction_with_imbalanced_splits(self):
        splits = [
            {"account_id": self.account1.accountID, "amount": 100},
            {"account_id": self.account1.accountID, "amount": 50},  # imbalanced
            ]
        with self.assertRaises(Exception):
            transaction=self.tr_service.create_transaction(
                ledger_id=self.ledger.ledgerID,
                date="2023-10-10",
                desc="Test Transaction",
                splits=splits,
                tags=[],
                necessary=True
            )
    def test_create_balanced_transaction(self):
        splits = [
        {"account_id": self.account1.accountID, "amount": 100},
        {"account_id": self.account1.accountID, "amount":-100},  # imbalanced
        ]
        transaction=self.tr_service.create_transaction(
                ledger_id=self.ledger.ledgerID,
                date="2023-10-10",
                desc="Test Transaction",
                splits=splits,
                tags=[],
                necessary=True
            )
        self.assertIsNotNone(transaction)
        self.assertEqual(transaction.desc,"Test Transaction")