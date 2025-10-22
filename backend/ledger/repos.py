from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Iterable
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from django.db import transaction as db_transaction
from django.core.exceptions import ObjectDoesNotExist

from .models import Ledger, Account, Transaction, Split, Tag


# Exceptii pentru layer repo

class RepoError(Exception):
    """Base repository exception."""

class NotFoundError(RepoError):
    """Entity not found in repository."""

class ValidationError(RepoError):
    """Validation failed (e.g. transaction not balanced)."""


# Interfata Repositories

class AccountsRepoInterface(ABC):
    @abstractmethod
    def create(self, name: str, type: str, ledger_id: int) -> Any:
        """Create and return an account object"""
        raise NotImplementedError

    @abstractmethod
    def get(self, pk: int) -> Optional[Any]:
        """Return account by primary key or None"""
        raise NotImplementedError

    @abstractmethod
    def get_by_name(self, name: str) -> Optional[Any]:
        """Return account by name or None."""
        raise NotImplementedError

    @abstractmethod
    def list(self) -> List[Any]:
        """Return list of all accounts ordered by name."""
        raise NotImplementedError


class TransactionsRepoInterface(ABC):
    @abstractmethod
    def create(
        self,
        *,
        ledger_id: int,
        date: date,
        description: str,
        splits: List[Dict[str, Any]],
        tags: Optional[List[str]] = None,
        necessary: bool = True,
    ) -> Any:
        """
        Create a transaction with splits.

        splits: list of dicts, each dict must contain:
          - 'amount' (Decimal or numeric-string)
          - either 'account_id' (int) or 'account_name' (str)
        The amounts must sum to zero (Decimal quantized to 2 decimals).
        """
        raise NotImplementedError

    @abstractmethod
    def get(self, pk: int) -> Optional[Any]:
        """Return transaction by pk (with splits prefetched)."""
        raise NotImplementedError

    @abstractmethod
    def list(self, **filters) -> List[Any]:
        """List transactions with simple filters (date range, account, tag)."""
        raise NotImplementedError


# Django implementations

class DjangoAccountsRepo(AccountsRepoInterface):
    def create(self, name: str, account_type: str, parent: Optional[int] = None, is_active: bool = True, ledger_id: int = 1) -> Account:
        parent_obj = None
        if parent:
            parent_obj = Account.objects.filter(pk=parent).first()
        
        # Get or create ledger using the correct field name
        from backend.ledger.models import Ledger
        ledger_obj, _ = Ledger.objects.get_or_create(ledgerID=ledger_id, defaults={'username': 'default'})
        
        return Account.objects.create(
            name=name,
            account_type=account_type,
            parent=parent_obj,
            is_active=is_active,
            ledger=ledger_obj,
        )

    def get(self, pk: int) -> Optional[Account]:
        return Account.objects.filter(pk=pk).first()

    def get_by_name(self, name: str) -> Optional[Account]:
        return Account.objects.filter(name=name).first()

    def list(self) -> List[Account]:
        return list(Account.objects.order_by("name").all())



class DjangoTransactionsRepo(TransactionsRepoInterface):
    def _normalize_amount(self, raw) -> Decimal:
        try:
            d = Decimal(str(raw))
        except (InvalidOperation, TypeError) as e:
            raise ValidationError(f"Invalid amount value: {raw}") from e
        return d.quantize(Decimal("0.01"))

    def create(
        self,
        *,
        ledger_id: int,
        date: date,
        description: str,
        splits: List[Dict[str, Any]],
        tags: Optional[List[str]] = None,
        necessary: bool = True,
    ) -> Transaction:
        if not isinstance(splits, Iterable) or len(splits) == 0:
            raise ValidationError("Transaction must have at least one split.")

        # Normalize amounts and compute total
        decimal_splits = []
        total = Decimal("0.00")
        for s in splits:
            if "amount" not in s:
                raise ValidationError(f"Missing 'amount' in split: {s}")
            amount = self._normalize_amount(s["amount"])
            decimal_splits.append({**s, "amount": amount})
            total += amount

        total = total.quantize(Decimal("0.01"))
        if total != Decimal("0.00"):
            raise ValidationError(f"Transaction not balanced: splits sum to {total}")

        with db_transaction.atomic():
            try:
                ledger = Ledger.objects.get(pk=ledger_id)
            except ObjectDoesNotExist:
                raise ValidationError(f"Ledger id {ledger_id} not found")

            tx = Transaction.objects.create(
                ledger=ledger,
                date=date,
                desc=description or "",
                necessary=necessary,
            )

            # Creează splits direct asociate tranzacției (transaction non-null)
            for s in decimal_splits:
                account = None
                if "account_id" in s:
                    try:
                        account = Account.objects.get(pk=int(s["account_id"]))
                    except ObjectDoesNotExist:
                        raise ValidationError(f"Account id {s['account_id']} not found")
                elif "account_name" in s:
                    account = Account.objects.filter(name=s["account_name"]).first()
                    if account is None:
                        raise ValidationError(f"Account name '{s['account_name']}' not found")
                else:
                    raise ValidationError("Each split requires 'account_id' or 'account_name'")

                # Creăm split asociat tranzacției imediat
                Split.objects.create(transaction=tx, account=account, amount=float(s["amount"]))

            # Adaugă tags dacă există
            if tags:
                for t in tags:
                    tag_obj, _ = Tag.objects.get_or_create(name=t)
                    tx.tags.add(tag_obj)

            tx.refresh_from_db()
            return tx

    def get(self, pk: int) -> Optional[Transaction]:
        return (
            Transaction.objects.prefetch_related("splits__account", "tags")
            .filter(pk=pk)
            .first()
        )

    def list(self, **filters) -> List[Transaction]:
        qs = Transaction.objects.prefetch_related("splits__account", "tags").all()
        date_from = filters.get("date_from")
        date_to = filters.get("date_to")
        account_id = filters.get("account_id")
        tag = filters.get("tag")

        if date_from:
            qs = qs.filter(date__gte=date_from)
        if date_to:
            qs = qs.filter(date__lte=date_to)
        if account_id:
            # Use pk here (works even if the Account primary key is named differently, e.g. accountID)
            qs = qs.filter(splits__account__pk=account_id).distinct()
        if tag:
            qs = qs.filter(tags__name=tag)

        return list(qs.order_by("-date"))


# In-memory stubs (pentru test)


@dataclass
class _AccountStub:
    id: int
    name: str
    type: str
    ledger_id: int
    created_at: datetime = field(default_factory=datetime.utcnow)

@dataclass
class _SplitStub:
    account_id: int
    amount: Decimal

@dataclass
class _TransactionStub:
    id: int
    date: date
    description: str
    necessary: bool
    tags: List[str]
    splits: List[_SplitStub]
    ledger_id: int
    created_at: datetime = field(default_factory=datetime.utcnow)


class InMemoryAccountsRepo(AccountsRepoInterface):
    def __init__(self):
        self._store: Dict[int, _AccountStub] = {}
        self._next = 1

    def create(self, name: str, type: str, ledger_id: int) -> _AccountStub:
        obj = _AccountStub(id=self._next, name=name, type=type, ledger_id=ledger_id)
        self._store[self._next] = obj
        self._next += 1
        return obj

    def get(self, pk: int) -> Optional[_AccountStub]:
        return self._store.get(pk)

    def get_by_name(self, name: str) -> Optional[_AccountStub]:
        for a in self._store.values():
            if a.name == name:
                return a
        return None

    def list(self) -> List[_AccountStub]:
        return sorted(list(self._store.values()), key=lambda a: a.name)


class InMemoryTransactionsRepo(TransactionsRepoInterface):
    def __init__(self, accounts_repo: InMemoryAccountsRepo):
        self._store: Dict[int, _TransactionStub] = {}
        self._next = 1
        self._accounts = accounts_repo

    def _normalize_amount(self, raw) -> Decimal:
        try:
            return Decimal(str(raw)).quantize(Decimal("0.01"))
        except Exception:
            raise ValidationError(f"Invalid amount: {raw}")

    def create(
        self,
        *,
        ledger_id: int,
        date: date,
        description: str,
        splits: List[Dict[str, Any]],
        tags: Optional[List[str]] = None,
        necessary: bool = True,
    ) -> _TransactionStub:
        if not splits:
            raise ValidationError("Transaction must have splits")

        decimal_splits = []
        total = Decimal("0.00")
        for s in splits:
            if "amount" not in s:
                raise ValidationError("Missing amount in split")
            amt = self._normalize_amount(s["amount"])
            account_id = s.get("account_id")

            if account_id is None:
                if "account_name" in s:
                    acc = self._accounts.get_by_name(s["account_name"])
                    if not acc:
                        raise ValidationError(f"Account name '{s['account_name']}' not found")
                    account_id = acc.id
                else:
                    raise ValidationError("Each split needs 'account_id' or 'account_name'")

            decimal_splits.append(_SplitStub(account_id=int(account_id), amount=amt))
            total += amt

        total = total.quantize(Decimal("0.01"))
        if total != Decimal("0.00"):
            raise ValidationError(f"Transaction not balanced: sum={total}")

        tx = _TransactionStub(
            id=self._next,
            date=date,
            description=description or "",
            necessary=necessary,
            tags=tags or [],
            splits=decimal_splits,
            ledger_id=ledger_id,
        )
        self._store[self._next] = tx
        self._next += 1
        return tx

    def get(self, pk: int) -> Optional[_TransactionStub]:
        return self._store.get(pk)

    def list(self, **filters) -> List[_TransactionStub]:
        results = list(self._store.values())
        date_from = filters.get("date_from")
        date_to = filters.get("date_to")
        account_id = filters.get("account_id")
        tag = filters.get("tag")

        if date_from:
            results = [r for r in results if r.date >= date_from]
        if date_to:
            results = [r for r in results if r.date <= date_to]
        if account_id:
            results = [r for r in results if any(s.account_id == account_id for s in r.splits)]
        if tag:
            results = [r for r in results if tag in r.tags]

        return sorted(results, key=lambda r: r.date, reverse=True)