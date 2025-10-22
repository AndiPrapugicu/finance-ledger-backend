from django.core.management.base import BaseCommand
from backend.ledger.models import Ledger, Account


class Command(BaseCommand):
    help = "Find duplicate 'Digital Wallet' accounts per ledger, keep first and deactivate others"

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be changed without saving'
        )

    def handle(self, *args, **options):
        dry_run = options.get('dry_run', False)
        total_ledgers = 0
        total_duplicates = 0
        changed_ledgers = 0

        for ledger in Ledger.objects.all().order_by('ledgerID'):
            total_ledgers += 1
            # Account model in ledger uses accountID as PK; order by accountID
            accounts = list(Account.objects.filter(ledger=ledger, name='Digital Wallet').order_by('accountID'))
            if len(accounts) <= 1:
                continue

            kept = accounts[0]
            duplicates = accounts[1:]
            total_duplicates += len(duplicates)
            changed_ledgers += 1

            self.stdout.write(self.style.WARNING(
                f"Ledger ledgerID={getattr(ledger,'ledgerID', None)} (username={getattr(ledger,'username',None)}) has {len(accounts)} Digital Wallet accounts. Keeping accountID={getattr(kept,'accountID', None)}, will deactivate {[getattr(a,'accountID',None) for a in duplicates]}"
            ))

            if not dry_run:
                for a in duplicates:
                    try:
                        a.is_active = False
                        a.save()
                    except Exception as e:
                        self.stdout.write(self.style.ERROR(f"Failed to deactivate account accountID={getattr(a,'accountID',None)}: {e}"))

        self.stdout.write(self.style.SUCCESS(f"Processed {total_ledgers} ledgers. Found {total_duplicates} duplicate accounts across {changed_ledgers} ledgers."))
