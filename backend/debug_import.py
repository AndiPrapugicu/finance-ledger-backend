# backend/debug_import.py
import os
import sys
import io
import csv

# --- asigură-te că rulezi din folderul project_root/backend (vezi instrucțiuni mai jos) ---
proj_backend = os.path.dirname(os.path.abspath(__file__))        # .../project/backend
project_root = os.path.dirname(proj_backend)                     # .../project

# pune project_root în sys.path astfel încât Django să fie importabil
sys.path.insert(0, project_root)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings")

import django
django.setup()

from backend.services.import_service import ImportService, _parse_amount, _parse_date, _load_rules_from_yaml_bytes, _match_rule

# Paths (ajustează dacă ai fișierele în altă parte)
csv_path = os.path.join("C:", "\\Users", "MrCag", "Documents", "Github", "Python-Academy-Projects", "cli", "sample_transactions.csv")
rules_path = os.path.join("C:", "\\Users", "MrCag", "Documents", "Github", "Python-Academy-Projects", "cli", "sample_rules.yaml")

print("CSV path:", csv_path)
print("Rules path:", rules_path)
print("----")

if not os.path.exists(csv_path):
    print("ERROR: CSV file not found at:", csv_path)
    sys.exit(1)

# read bytes and text
with open(csv_path, "rb") as f:
    file_bytes = f.read()
text = file_bytes.decode("utf-8-sig", errors="replace")

print("First 20 lines of CSV (for quick inspection):")
for i, line in enumerate(text.splitlines()[:20], start=1):
    print(f"{i:02d}: {line}")
print("----\n")

# load rules if present
rules_list = []
if os.path.exists(rules_path):
    rules_bytes = open(rules_path, "rb").read()
    rules_list = _load_rules_from_yaml_bytes(rules_bytes)
    print("Loaded rules (sample):", rules_list[:5])
else:
    print("No rules file found (will use DB rules or none).")
print("----\n")

# Show parsing of first rows
reader = csv.DictReader(io.StringIO(text))
print("Parsed rows sample (first 10) and parsing attempts:")
for idx, row in enumerate(reader, start=1):
    print(f"\nROW {idx}: {row}")
    low_keys = {k.lower(): k for k in row.keys()}
    # detect amount key like in service
    amount_key = None
    for candidate in ("amount", "amt", "value", "transaction amount"):
        if candidate in low_keys:
            amount_key = low_keys[candidate]
            break
    if not amount_key:
        for k in row.keys():
            if k.lower().startswith("amount"):
                amount_key = k
                break

    date_key = low_keys.get("date") or low_keys.get("transaction date") or None
    payee_key = low_keys.get("payee") or low_keys.get("description") or low_keys.get("merchant") or None
    tag_key = low_keys.get("tags") or low_keys.get("tag") or None

    print("  detected keys -> amount_key:", amount_key, " date_key:", date_key, " payee_key:", payee_key, " tag_key:", tag_key)

    # try parse amount
    if amount_key and row.get(amount_key) is not None:
        try:
            amt = _parse_amount(row[amount_key])
        except Exception as e:
            amt = f"PARSE_ERROR: {e}"
    else:
        amt = "MISSING"
    print("  parsed amount:", amt)

    # try parse date
    if date_key and row.get(date_key) is not None:
        try:
            d = _parse_date(row.get(date_key))
        except Exception as e:
            d = f"DATE_PARSE_ERROR: {e}"
    else:
        d = "MISSING"
    print("  parsed date:", d)

    # combined text & rule match
    desc_text = row.get("desc") or row.get("description") or ""
    payee_text = row.get(payee_key) if payee_key else ""
    combined_text = f"{payee_text} {desc_text}".strip()
    matched = _match_rule(combined_text, rules_list)
    print("  combined_text:", combined_text, " matched rule:", matched)

    if idx >= 10:
        break

print("\n---- Now running ImportService.import_csv(...) (this will attempt to create DB objects) ----")

svc = ImportService()

rf = open(rules_path, "rb") if os.path.exists(rules_path) else None
cf = open(csv_path, "rb")
try:
    result = svc.import_csv(cf, rf)
finally:
    cf.close()
    if rf:
        rf.close()

print("\nImportService result summary:")
print(" created_count:", getattr(result, "created_count", None))
print(" skipped:", getattr(result, "skipped", None))
print(" errors (len):", len(getattr(result, "errors", [])))
print(" errors:", getattr(result, "errors", []))
if getattr(result, "import_record", None):
    ir = result.import_record
    print(" ImportRecord id:", ir.id, " imported_count:", ir.imported_count, " meta:", ir.meta)
else:
    print(" No ImportRecord returned")
