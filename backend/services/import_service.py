import hashlib
import io
import csv
import re
from decimal import Decimal, InvalidOperation
from typing import Optional, List, Dict, Any
from datetime import datetime
import yaml

from django.utils import timezone
from django.db import transaction
from django.http import JsonResponse

from backend.ledger.models import ImportRecord, Rule
from backend.ledger.repos import DjangoAccountsRepo, DjangoTransactionsRepo


def _compute_hash(file_bytes: bytes, rules_bytes: Optional[bytes]) -> str:
    h = hashlib.sha256()
    h.update(file_bytes)
    if rules_bytes:
        h.update(b"::RULES::")
        h.update(rules_bytes)
    return h.hexdigest()


def _parse_amount(s: str) -> Decimal:
    if s is None:
        raise ValueError("Amount missing")
    s = str(s).strip()
    s = s.replace(",", "")
    if s.startswith("(") and s.endswith(")"):
        s = "-" + s[1:-1]
    return Decimal(s)


def _parse_date(s: str):
    s = (s or "").strip()
    if not s:
        return None
    fmts = ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y")
    for f in fmts:
        try:
            return datetime.strptime(s, f).date()
        except Exception:
            continue
    try:
        return datetime.fromisoformat(s).date()
    except Exception:
        return None


def _load_rules_from_yaml_bytes(b: bytes) -> List[Dict[str, Any]]:
    if not b:
        return []
    content = b.decode("utf-8")
    parsed = yaml.safe_load(content)
    if parsed is None:
        return []
    if isinstance(parsed, dict):
        parsed = parsed.get("rules", [])
    return parsed


def _match_rule(text: str, rules_list: List[Dict[str, Any]]):
    txt = (text or "").lower()
    for r in rules_list:
        mt = r.get("matcher_type", "keyword")
        matcher = r.get("matcher")
        if not matcher:
            continue
        if mt == "keyword":
            for kw in [k.strip() for k in matcher.split(",") if k.strip()]:
                if kw.lower() in txt:
                    return r
        elif mt == "regex":
            try:
                if re.search(matcher, text, flags=re.IGNORECASE):
                    return r
            except re.error:
                continue
    return None


def _ensure_account(accounts_repo: DjangoAccountsRepo, account_name: str, fallback_type: str, ledger_id: int):
    """
    Get or create Account by exact name. If not found => create with fallback_type.
    fallback_type should be one of: 'ASSET','LIABILITY','INCOME','EXPENSE'
    """
    acc = accounts_repo.get_by_name(account_name)
    if acc:
        # If account exists but belongs to a different ledger, don't reuse it.
        try:
            acc_ledger_id = getattr(acc.ledger, 'ledgerID', getattr(acc.ledger, 'id', None))
        except Exception:
            acc_ledger_id = None

        if acc_ledger_id == ledger_id:
            return acc
        # Otherwise, create a new account in the target ledger to avoid cross-ledger contamination
        return accounts_repo.create(name=account_name, account_type=fallback_type, parent=None, is_active=True, ledger_id=ledger_id)

    # create with ledger_id
    return accounts_repo.create(name=account_name, account_type=fallback_type, parent=None, is_active=True, ledger_id=ledger_id)


class CSVImportResult:
    def __init__(self, created_count: int, skipped: bool, import_record: Optional[ImportRecord], errors: List[str]):
        self.created_count = created_count
        self.skipped = skipped
        self.import_record = import_record
        self.errors = errors


class ImportService:
    def __init__(self, accounts_repo: Optional[DjangoAccountsRepo] = None, tx_repo: Optional[DjangoTransactionsRepo] = None):
        self.accounts_repo = accounts_repo or DjangoAccountsRepo()
        self.tx_repo = tx_repo or DjangoTransactionsRepo()

    def import_csv(self, fileobj, rules_fileobj=None, ledger_id: int = 1, asset_account_name: str = "ASSET:Bank") -> CSVImportResult:
        """
        fileobj: file-like opened in binary mode (uploaded file .read() gives bytes)
        rules_fileobj: optional file-like for rules YAML (binary)
        ledger_id: required ledger id to attach transactions to (Transaction model has ledger FK)
        asset_account_name: name of the asset/bank account to use for all splits
        """
        # read bytes (fileobj may be Django InMemoryUploadedFile)
        file_bytes = fileobj.read()
        rules_bytes = rules_fileobj.read() if rules_fileobj else None

        file_hash = _compute_hash(file_bytes, rules_bytes)

        # idempotency check
        existing = ImportRecord.objects.filter(file_hash=file_hash).first()
        # Note: we may receive a 'force' flag in request.POST in the view wrapper to allow re-import
        # The view-level import_csv will optionally pass through `force_delete_existing` via kwargs.
        force_delete_existing = getattr(self, "_force_delete_existing", False)

        if existing:
            if force_delete_existing:
                # Explicit request to re-import: delete previous record and continue
                existing.delete()
            else:
                # Dacă importul anterior a creat ceva, marcăm skip.
                if existing.imported_count and existing.imported_count > 0:
                    return CSVImportResult(created_count=existing.imported_count, skipped=True, import_record=existing,
                                           errors=[])
                # Dacă import anterior a eșuat (imported_count == 0), vrem să permitem re-run:
                # ștergem înregistrarea precedentă (sau alternativ reîncercăm și suprascriem)
                existing.delete()

        from backend.ledger.models import Ledger
        ledger_obj, _ = Ledger.objects.get_or_create(
            pk=ledger_id,
            defaults={"username": f"ledger_{ledger_id}"}
        )
        # parse rules from YAML if given; else load from DB
        rules_list = []
        if rules_bytes:
            rules_list = _load_rules_from_yaml_bytes(rules_bytes)
        else:
            # fallback: load Rule objects from DB
            rules_list = []
            for r in Rule.objects.all().order_by("id"):
                rules_list.append({
                    "matcher": r.matcher,
                    "matcher_type": r.matcher_type,
                    "category": r.category,
                    "necessary": bool(r.necessary),
                })

        text = file_bytes.decode("utf-8-sig", errors="replace")
        reader = csv.DictReader(io.StringIO(text))

        created = 0
        errors = []
        created_tx_ids = []

        def detect_type_from_name(name: str):
            n = name.lower()
            if "asset" in n:
                return "ASSET"
            if "liabil" in n:
                return "LIABILITY"
            if "income" in n:
                return "INCOME"
            if "expense" in n:
                return "EXPENSE"
            return "ASSET"

        asset_type = detect_type_from_name(asset_account_name)
        asset_acc = _ensure_account(self.accounts_repo, asset_account_name, asset_type, ledger_id)

        for idx, row in enumerate(reader, start=1):
            try:
                print(f"[DEBUG] Processing row {idx}: {row}")  # Debug logging
                low_keys = {k.lower(): k for k in row.keys()}
                amount_key = None
                for candidate in ("amount", "amt", "value", "transaction amount"):
                    if candidate in low_keys:
                        amount_key = low_keys[candidate]; break
                if not amount_key:
                    for k in row.keys():
                        if k.lower().startswith("amount"):
                            amount_key = k; break
                
                if not amount_key:
                    print(f"[ERROR] Row {idx}: No amount column found. Available keys: {list(row.keys())}")
                    errors.append(f"row {idx}: No amount column found")
                    continue

                date_key = low_keys.get("date") or low_keys.get("transaction date") or None
                payee_key = low_keys.get("payee") or low_keys.get("description") or low_keys.get("merchant") or None
                tag_key = low_keys.get("tags") or low_keys.get("tag") or None

                amount = _parse_amount(row[amount_key]) if amount_key else Decimal("0.00")
                tx_date = _parse_date(row.get(date_key)) if date_key else timezone.now().date()
                
                # Safe handling of payee and description
                payee_text = ""
                if payee_key and payee_key in row:
                    payee_text = str(row.get(payee_key) or "")
                
                desc_text = ""
                if "desc" in row:
                    desc_text = str(row.get("desc") or "")
                elif "description" in low_keys:
                    desc_key = low_keys["description"]
                    desc_text = str(row.get(desc_key) or "")
                
                combined_text = f"{payee_text} {desc_text}".strip()
                if not combined_text:
                    combined_text = "Imported Transaction"

                matched_rule = _match_rule(combined_text, rules_list)

                if matched_rule:
                    category = matched_rule.get("category")
                    necessary = bool(matched_rule.get("necessary", False))
                else:
                    if amount < 0:
                        category = "Expenses:Uncategorized"
                    else:
                        category = "Income:Uncategorized"
                    necessary = False

                if ":" not in category:
                    if amount < 0:
                        category_name = f"Expenses:{category}"
                        cat_type = "EXPENSE"
                    else:
                        category_name = f"Income:{category}"
                        cat_type = "INCOME"
                else:
                    category_name = category
                    cat_type = detect_type_from_name(category_name)

                category_acc = _ensure_account(self.accounts_repo, category_name, cat_type, ledger_id)

                asset_split_amt = amount
                category_split_amt = -amount

                splits = [
                    {"account_id": asset_acc.accountID if hasattr(asset_acc, "accountID") else getattr(asset_acc, "id", None), "amount": asset_split_amt},
                    {"account_id": category_acc.accountID if hasattr(category_acc, "accountID") else getattr(category_acc, "id", None), "amount": category_split_amt},
                ]

                tags = []
                if tag_key and row.get(tag_key):
                    tag_string = str(row.get(tag_key))
                    # Support both comma and pipe separators for tags
                    if '|' in tag_string:
                        tags = [t.strip() for t in tag_string.split("|") if t.strip()]
                    else:
                        tags = [t.strip() for t in tag_string.split(",") if t.strip()]

                tx = self.tx_repo.create(
                    ledger_id=ledger_id,
                    date=tx_date,
                    description=combined_text,
                    splits=splits,
                    tags=tags,
                    necessary=necessary,
                )
                created += 1
                created_tx_ids.append(getattr(tx, "transactionID", getattr(tx, "id", None)))
                print(f"[SUCCESS] Row {idx}: Created transaction {getattr(tx, 'transactionID', 'N/A')}")
            except Exception as e:
                print(f"[ERROR] Row {idx} failed: {str(e)}")
                import traceback
                traceback.print_exc()
                errors.append(f"row {idx}: {str(e)}")

        # store import record
        with transaction.atomic():
            ir = ImportRecord.objects.create(
                file_hash=file_hash,
                filename=getattr(fileobj, "name", None),
                imported_count=created,
                meta={"tx_ids": created_tx_ids, "errors": errors}
            )

        return CSVImportResult(created_count=created, skipped=False, import_record=ir, errors=errors)

from django.views.decorators.csrf import csrf_exempt

@csrf_exempt
def import_csv(request):
    """
    Django view pentru endpoint-ul /api/import/
    """
    if request.method != "POST":
        return JsonResponse({"status": "error", "message": "Only POST allowed"}, status=405)

    csv_file = request.FILES.get("csv")
    rules_file = request.FILES.get("rules")

    if not csv_file:
        return JsonResponse({"status": "error", "message": "Missing CSV file"}, status=400)

    service = ImportService()
    # Support an optional "force" flag to re-import even if an identical file was previously imported.
    force_flag = False
    # Check POST form field first (sent as form-data), then querystring
    if request.POST.get("force") in ("1", "true", "True"):
        force_flag = True
    if request.GET.get("force") in ("1", "true", "True"):
        force_flag = True

    # Attach a transient attribute on the service instance to control idempotency behavior
    setattr(service, "_force_delete_existing", force_flag)
    try:
        result = service.import_csv(csv_file, rules_file)
        # Build a friendly list of created transactions (id, date, description, amount)
        transactions_summary = []
        try:
            if getattr(result, 'import_record', None):
                tx_ids = result.import_record.meta.get('tx_ids', []) if isinstance(result.import_record.meta, dict) else []
                if tx_ids:
                    from backend.ledger.models import Transaction as LedgerTransaction
                    for tid in tx_ids:
                        try:
                            t = LedgerTransaction.objects.get(transactionID=tid)
                            splits = t.splits.all()
                            tx_amount = max((abs(float(s.amount)) for s in splits), default=0)
                            transactions_summary.append({
                                'id': t.transactionID,
                                'date': t.date.isoformat(),
                                'description': t.desc,
                                'amount': tx_amount
                            })
                        except Exception:
                            # ignore missing transactions
                            continue
        except Exception:
            transactions_summary = []

        return JsonResponse({
            "status": "ok",
            "created_count": result.created_count,
            "skipped": result.skipped,
            "errors": result.errors,
            "transactions": transactions_summary,
        }, status=200)
    except Exception as e:
        return JsonResponse({"status": "error", "message": str(e)}, status=500)