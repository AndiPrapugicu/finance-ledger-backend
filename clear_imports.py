# Script to clear import records and allow re-import
from backend.ledger.models import ImportRecord

# Delete all import records
count = ImportRecord.objects.all().count()
print(f"Found {count} import records")

ImportRecord.objects.all().delete()
print("All import records deleted! You can now re-import files.")
