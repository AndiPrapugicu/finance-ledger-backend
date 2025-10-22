from decimal import Decimal
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from api.wallet_models import Wallet
from backend.ledger.models import Transaction as LedgerTransaction, Split

def apply_splits_to_wallet(user, splits, transaction_desc="Split transaction applied"):
    """
    Adjust wallet balance according to splits.
    Only ASSET and INCOME accounts increase wallet, EXPENSE and LIABILITY decrease wallet.
    """
    wallet, _ = Wallet.objects.get_or_create(user=user)

    net_change = Decimal('0.00')

    for split in splits:
        account = split.account  # LedgerAccount
        amount = split.amount

        if account.account_type in ['ASSET', 'INCOME']:
            net_change += amount
        elif account.account_type in ['EXPENSE', 'LIABILITY']:
            net_change -= amount
        # EQUITY accounts ignored

    if net_change != 0:
        if net_change > 0:
            wallet.add_funds(net_change, description=transaction_desc)
        else:
            wallet.deduct_funds(abs(net_change), description=transaction_desc)


@receiver(post_save, sender=LedgerTransaction)
def sync_transaction_to_wallet(sender, instance: LedgerTransaction, created, **kwargs):
    """
    After creating/updating a LedgerTransaction, adjust user's wallet based on splits.
    """
    splits = Split.objects.filter(transaction=instance)
    if splits.exists():
        apply_splits_to_wallet(
            user=instance.ledger.user,  # assume Ledger has user relation
            splits=splits,
            transaction_desc=f"LedgerTransaction {instance.transactionID}: {instance.desc}"
        )


@receiver(post_delete, sender=LedgerTransaction)
def remove_transaction_from_wallet(sender, instance: LedgerTransaction, **kwargs):
    """
    When a LedgerTransaction is deleted, reverse its effect on the wallet.
    """
    splits = Split.objects.filter(transaction=instance)
    if splits.exists():
        # Reverse the net change
        reversed_splits = []
        for split in splits:
            reversed_split = Split(account=split.account, amount=-split.amount)
            reversed_splits.append(reversed_split)

        apply_splits_to_wallet(
            user=instance.ledger.user,
            splits=reversed_splits,
            transaction_desc=f"LedgerTransaction {instance.transactionID} deleted"
        )
@receiver(post_save, sender=LedgerTransaction)
def sync_transaction_to_wallet(sender, instance, created, **kwargs):
    # Get user from ledger username
    from django.contrib.auth.models import User
    try:
        user = User.objects.get(username=instance.ledger.username)
        wallet, _ = Wallet.objects.get_or_create(user=user)
        # This signal seems to be for a different type of transaction
        # Skip for now as LedgerTransaction doesn't have amount/account directly
        pass
    except User.DoesNotExist:
        pass  # Skip if user not found


# Sync LedgerTransactions
@receiver(post_save, sender=LedgerTransaction)
def sync_ledger_transaction_to_wallet(sender, instance, created, **kwargs):
    from django.contrib.auth.models import User
    try:
        user = User.objects.get(username=instance.ledger.username)
        splits = Split.objects.filter(transaction=instance)
        if splits.exists():
            apply_splits_to_wallet(
                user=user,
                splits=splits,
                transaction_desc=f"LedgerTransaction {instance.transactionID}: {instance.desc}"
            )
    except User.DoesNotExist:
        pass  # Skip if user not found


@receiver(post_delete, sender=LedgerTransaction)
def remove_ledger_transaction_from_wallet(sender, instance, **kwargs):
    from django.contrib.auth.models import User
    try:
        user = User.objects.get(username=instance.ledger.username)
        splits = Split.objects.filter(transaction=instance)
        if splits.exists():
            reversed_splits = [Split(account=s.account, amount=-s.amount) for s in splits]
            apply_splits_to_wallet(
                user=user,
                splits=reversed_splits,
                transaction_desc=f"LedgerTransaction {instance.transactionID} deleted"
            )
    except User.DoesNotExist:
        pass  # Skip if user not found