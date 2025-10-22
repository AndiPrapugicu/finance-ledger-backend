from typing import List, Iterator
import csv
from io import StringIO
from datetime import date
from decimal import Decimal

class ReportExporter:
    def generate_csv(self, transactions: List['Transaction']) -> Iterator[str]:
        output = StringIO()
        writer = csv.writer(output)

        # Write header
        writer.writerow(['Date', 'Description', 'Account', 'Amount', 'Tags'])
        yield output.getvalue()
        output.seek(0)
        output.truncate()

        # Stream transaction data
        for tx in transactions:
            for split in tx.splits.all():
                writer.writerow([
                    tx.date.strftime('%Y-%m-%d'),
                    tx.desc,
                    split.account.name,
                    f"{split.amount:.2f}",
                    ','.join(t.name for t in tx.tags.all())
                ])
                yield output.getvalue()
                output.seek(0)
                output.truncate()

    def generate_markdown(self, transactions: List['Transaction']) -> Iterator[str]:
        # Header
        yield "# Transaction Report\n\n"
        yield "| Date | Description | Account | Amount | Tags |\n"
        yield "|------|-------------|----------|--------|------|\n"

        # Transaction rows
        for tx in transactions:
            for split in tx.splits.all():
                yield f"| {tx.date.strftime('%Y-%m-%d')} | {tx.desc} | {split.account.name} | "
                yield f"{split.amount:.2f} | {','.join(t.name for t in tx.tags.all())} |\n"