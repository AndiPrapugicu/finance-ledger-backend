from backend.ledger.models import Transaction,Account
from backend.ledger.repos import DjangoAccountsRepo



class AccountService():
    def __init__(self,repository:DjangoAccountsRepo):
        self.repository=repository

    def create_account(self,name,account_type,parent,is_active):
        if not name:
            raise ValidationError("Account name is required")
        if account_type not in ["ASSET", "LIABILITY", "EQUITY", "INCOME", "EXPENSE"]:
            raise ValidationError(f"Invalid account type: {account_type}")

        account=self.repository.create(
            name=name,
            account_type=account_type,
            parent=parent,
            is_active=is_active)
        return account
    def get_account(self,account_id:int):
        return self.repository.get(account_id)
    def get_all_accounts(self,ledger_id:int):
        return self.repository.get_all(ledger_id)
    def update_account(self,account_id:int,name,account_type,parent,is_active):
        account=self.get_account(account_id)
        if not account:
            return None
        account.name=name
        account.account_type=account_type
        account.parent=parent
        account.is_active=is_active
        self.repository.update(account)
        return account
    def delete_account(self,account_id:int):
        account=self.get_account(account_id)
        if not account:
            return None
        self.repository.delete(account)
        return account
    
        
   