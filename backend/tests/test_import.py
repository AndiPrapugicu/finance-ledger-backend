import pytest
from backend.services.import_service import ImportService
from backend.ledger.models import Transaction, Ledger


@pytest.mark.django_db
def test_import_creates_transactions():
    csv_path = "cli/sample_transactions.csv"
    rules_path = "cli/sample_rules.yaml"

    ledger = Ledger.objects.first()
    assert ledger is not None, "Trebuie să existe un Ledger în DB"

    service = ImportService()
    result = service.import_csv(
        ledger_id=ledger.id,
        csv_path=csv_path,
        rules_path=rules_path,
    )

    assert result["created_count"] > 0
    assert Transaction.objects.count() == result["created_count"]


@pytest.mark.django_db
def test_import_is_idempotent():
    csv_path = "cli/sample_transactions.csv"
    rules_path = "cli/sample_rules.yaml"

    ledger = Ledger.objects.first()
    service = ImportService()

    # Prima rulare
    result1 = service.import_csv(
        ledger_id=ledger.id, csv_path=csv_path, rules_path=rules_path
    )
    created_count_first = result1["created_count"]

    # A doua rulare
    result2 = service.import_csv(
        ledger_id=ledger.id, csv_path=csv_path, rules_path=rules_path
    )

    assert result2["created_count"] == 0
    assert result2["skipped"] is True
    assert Transaction.objects.count() == created_count_first
