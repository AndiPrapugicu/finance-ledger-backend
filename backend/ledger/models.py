# TODO: Persoana A - Finalizează schema entity
# Implementează: Account, Transaction, Split, Rule, Budget
# Criteriu: modele documentate + migrations funcționale

# Placeholder pentru Persoana A
# Aceasta va înlocui modelele temporare din api/temp_models.pyfrom django.db import models
from django.db import models
class Ledger(models.Model):
    ledgerID=models.AutoField(primary_key=True)
    username=models.CharField(max_length=200)

class Account(models.Model):
    ACCOUNT_TYPE_CHOICES = [
        ("ASSET", "Assets"),
        ("LIABILITY", "Liabilities"),
        ("INCOME", "Income"),
        ("EXPENSE", "Expenses"),
    ]

    accountID = models.AutoField(primary_key=True)
    ledger = models.ForeignKey("Ledger", on_delete=models.CASCADE, related_name="accounts")
    name = models.CharField(max_length=200)
    account_type = models.CharField(max_length=20, choices=ACCOUNT_TYPE_CHOICES)
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL)
    is_active = models.BooleanField(default=True)

class Split(models.Model):
    transaction = models.ForeignKey("Transaction", on_delete=models.CASCADE, related_name="splits")
    account = models.ForeignKey("Account", on_delete=models.CASCADE)
    amount = models.FloatField()

    def __str__(self):
        return f"{self.account.name}: {self.amount}"

class Tag(models.Model):
    name = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.name
#: id, date, desc, splits[], tags[], necessary: bool
class Transaction(models.Model):
    transactionID = models.AutoField(primary_key=True)
    ledger = models.ForeignKey("Ledger", on_delete=models.CASCADE)
    date = models.DateField()
    desc = models.TextField()
    tags = models.ManyToManyField("Tag", blank=True)
    necessary = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.date} - {self.desc}"
    
class Budget(models.Model):
    budgetID=models.AutoField(primary_key=True)
    ledger=models.ForeignKey(Ledger,on_delete=models.CASCADE)
    account=models.ForeignKey(Account,on_delete=models.CASCADE, null=True)
    category=models.CharField(max_length=200)  # e.g., "Food", "Rent"
    amount=models.FloatField()
    period=models.CharField(max_length=200)  # e.g., "monthly", "yearly"

from django.db import models

class Rule(models.Model):
    MATCHER_TYPE_CHOICES = [
        ('regex', 'Regex'),
        ('keyword', 'Keyword'),
    ]

    matcher = models.CharField(max_length=255)
    matcher_type = models.CharField(max_length=10, choices=MATCHER_TYPE_CHOICES)
    category = models.CharField(max_length=100)
    necessary = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.category}: {self.matcher} ({self.matcher_type})"


class ImportRecord(models.Model):
    file_hash = models.CharField(max_length=64, unique=True)
    filename = models.CharField(max_length=255, blank=True, null=True)
    imported_at = models.DateTimeField(auto_now_add=True)
    imported_count = models.IntegerField(default=0)
    meta = models.JSONField(default=dict, blank=True)  # opțional: rule summary, source info

    def __str__(self):
        return f"Import {self.filename or self.file_hash[:8]} @ {self.imported_at.isoformat()}"


class Alert(models.Model):
    alertID = models.AutoField(primary_key=True)
    budget = models.ForeignKey(Budget, on_delete=models.CASCADE)
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)

    class Meta:
        ordering = ['-created_at']