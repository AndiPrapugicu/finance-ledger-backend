from django.core.management.base import BaseCommand
from api.models import Account

class Command(BaseCommand):
    help = 'Create sample account data for testing'

    def handle(self, *args, **options):
        fixtures = [
            {'name': 'Assets', 'account_type': 'ASSET'},
            {'name': 'Cash', 'account_type': 'ASSET', 'parent_name': 'Assets'},
            {'name': 'Checking Account', 'account_type': 'ASSET', 'parent_name': 'Cash'},
            {'name': 'Savings Account', 'account_type': 'ASSET', 'parent_name': 'Cash'},
            {'name': 'Liabilities', 'account_type': 'LIABILITY'},
            {'name': 'Credit Cards', 'account_type': 'LIABILITY', 'parent_name': 'Liabilities'},
            {'name': 'Income', 'account_type': 'INCOME'},
            {'name': 'Salary', 'account_type': 'INCOME', 'parent_name': 'Income'},
            {'name': 'Expenses', 'account_type': 'EXPENSE'},
            {'name': 'Food', 'account_type': 'EXPENSE', 'parent_name': 'Expenses'},
            {'name': 'Transportation', 'account_type': 'EXPENSE', 'parent_name': 'Expenses'},
        ]
        
        created_accounts = []
        account_map = {}
        
        # First pass: create parent accounts
        for fixture in fixtures:
            if 'parent_name' not in fixture:
                account, created = Account.objects.get_or_create(
                    name=fixture['name'],
                    defaults={'account_type': fixture['account_type']}
                )
                account_map[fixture['name']] = account
                if created:
                    created_accounts.append(account.name)
        
        # Second pass: create child accounts
        for fixture in fixtures:
            if 'parent_name' in fixture:
                parent = account_map.get(fixture['parent_name'])
                if parent:
                    account, created = Account.objects.get_or_create(
                        name=fixture['name'],
                        defaults={
                            'account_type': fixture['account_type'],
                            'parent': parent
                        }
                    )
                    account_map[fixture['name']] = account
                    if created:
                        created_accounts.append(account.name)
        
        self.stdout.write(
            self.style.SUCCESS(f'Successfully created {len(created_accounts)} accounts: {", ".join(created_accounts)}')
        )