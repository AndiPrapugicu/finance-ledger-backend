#Backend: services/transaction_service.py  — double-entry validation (reject     dezechilibru). 
#Criteriu: unit test care confirmă respingere cu mesaj clar. 
from backend.ledger.models import Transaction
from backend.ledger.repos import DjangoTransactionsRepo
class TransactionService():
    def __init__(self,repository:DjangoTransactionsRepo):
        self.repository=repository
        
    def create_transaction(self,ledger_id:int,date,desc,splits,tags,necessary):
        try:
            transaction=self.repository.create(
                ledger_id=ledger_id,
                date=date,
                description=desc,
                splits=splits,
                tags=tags,
                necessary=necessary
            )
        except Exception as e:
            raise e
        return transaction
    def get_transaction(self,transaction_id:int):
        return self.repository.get(transaction_id)
    def get_all_transactions(self,ledger_id:int):
        return self.repository.get_all(ledger_id)
    def update_transaction(self,transaction_id:int,date,desc,splits,tags,necessary):
        transaction=self.get_transaction(transaction_id)
        if not transaction:
            return None
        transaction.date=date
        transaction.desc=desc
        transaction.necessary=necessary
        self.repository.update(transaction)
        return transaction
    def delete_transaction(self,transaction_id:int):
        transaction=self.get_transaction(transaction_id)
        if not transaction:
            return None
        self.repository.delete(transaction)
        return transaction