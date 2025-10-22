# Quick script to check imported transactions
from backend.ledger.models import Ledger, Transaction as LedgerTransaction, Account
from django.contrib.auth.models import User

# Get the user
user = User.objects.latest('id')
print(f"User: {user.username}")

# Get user's ledger
try:
    ledger = Ledger.objects.get(username=user.username)
    print(f"Ledger ID: {ledger.ledgerID}")
    
    # Count transactions
    transactions = LedgerTransaction.objects.filter(ledger=ledger).order_by('-date')
    print(f"\nTotal transactions in ledger: {transactions.count()}")
    
    # List them
    print("\nTransactions:")
    for tx in transactions:
        print(f"  - {tx.date} | {tx.desc[:50]} | ID: {tx.transactionID}")
        
    # Check accounts
    accounts = Account.objects.filter(ledger=ledger)
    print(f"\nTotal accounts in ledger: {accounts.count()}")
    print("\nAccounts:")
    for acc in accounts:
        print(f"  - {acc.name} ({acc.account_type}) | ID: {acc.accountID}")
        
except Ledger.DoesNotExist:
    print("No ledger found for this user!")
