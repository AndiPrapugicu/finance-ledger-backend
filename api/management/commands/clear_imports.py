from django.core.management.base import BaseCommand
from backend.ledger.models import ImportRecord


class Command(BaseCommand):
    help = 'Clear all import records to allow re-importing files'

    def handle(self, *args, **options):
        count = ImportRecord.objects.all().count()
        self.stdout.write(f"Found {count} import records")
        
        ImportRecord.objects.all().delete()
        
        self.stdout.write(self.style.SUCCESS(
            'Successfully deleted all import records! You can now re-import files.'
        ))
