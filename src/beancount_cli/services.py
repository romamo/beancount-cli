import sys
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from beancount import loader
from beancount.core import data
from beancount.parser import printer

from beancount_cli.adapters import from_core_transaction, to_core_transaction
from beancount_cli.models import AccountModel, CurrencyCode, TransactionModel


class LedgerService:
    def __init__(self, ledger_file: Path):
        self.ledger_file = ledger_file
        self.entries: list[data.Directive] = []
        self.errors: list[Any] = []
        self.options: dict[str, Any] = {}
        self._loaded = False

    def load(self):
        if self._loaded:
            return
        if not self.ledger_file.exists():
            raise FileNotFoundError(f"Ledger file not found: {self.ledger_file}")

        # Load the file
        self.entries, self.errors, self.options = loader.load_file(str(self.ledger_file))
        self._loaded = True

    def get_operating_currencies(self) -> list[str]:
        if not self._loaded:
            self.load()
        return self.options.get("operating_currency", [])

    def get_accounts(self) -> list[str]:
        if not self._loaded:
            self.load()
        # Extract open directives to get accounts, or use realization?
        # A simple set comprehension over Open directives is fast.
        return sorted([e.account for e in self.entries if isinstance(e, data.Open)])

    def get_commodities(self) -> list[str]:
        if not self._loaded:
            self.load()
        return sorted([e.currency for e in self.entries if isinstance(e, data.Commodity)])

    def get_custom_config(self, key: str) -> str | None:
        """
        Extract config from 'custom "cli-config" "key" "value"' directives.
        """
        if not self._loaded:
            self.load()
        # Iterate in reverse to get latest override? Or first?
        # Usually config is at top.
        # Iterate in reverse to get latest override
        for e in reversed(self.entries):
            if isinstance(e, data.Custom) and e.type == "cli-config":
                if len(e.values) < 2:
                    continue

                # Check directly the values
                val_key = e.values[0]
                val_value = e.values[1]

                # Beancount parser returns strings in custom directives as str,
                # but sometimes wrapped. Check for .value attribute just in case.
                if hasattr(val_key, "value"):
                    val_key = val_key.value
                if hasattr(val_value, "value"):
                    val_value = val_value.value

                if val_key == key:
                    return val_value
        return None


class ValidationService:
    def __init__(self, ledger_service: LedgerService):
        self.ledger = ledger_service

    def validate_transaction(self, tx: TransactionModel) -> list[str]:
        errors = []
        valid_accounts = set(self.ledger.get_accounts())
        valid_commodities = set(self.ledger.get_commodities())

        for p in tx.postings:
            if p.account not in valid_accounts:
                # Check if it's a known parent? No, Beancount requires Open directives.
                # Just flag it.
                errors.append(f"Account '{p.account}' does not exist (no Open directive).")

            if p.units.currency not in valid_commodities:
                # Beancount doesn't strictly require Commodity directives for all currencies
                # (e.g. USD), but if strict mode is on... let's just warn or skip common ones?
                # Actually beancount allow_undefined_currencies option controls this.
                # For now, let's trust the ledger options or just skip this check if empty.
                if valid_commodities:
                    errors.append(f"Currency '{p.units.currency}' not in declared commodities.")

        return errors


class TransactionService:
    def __init__(self, ledger_file: Path):
        self.ledger_file = ledger_file
        self.ledger_service = LedgerService(ledger_file)
        self.validator = ValidationService(self.ledger_service)

    # ... list_transactions ... (omitted from replace chunk to keep it small?
    # No, I need to keep the file valid)
    # Wait, replace_file_content needs Context.
    # I'll replace the TransactionService class start and add_transaction method.

    def list_transactions(
        self,
        account_regex: str | None = None,
        payee_regex: str | None = None,
        tag: str | None = None,
        currency: CurrencyCode.Input | None = None,
        bql_where: str | None = None,
    ) -> list[TransactionModel]:
        self.ledger_service.load()
        entries = self.ledger_service.entries
        txs = [e for e in entries if isinstance(e, data.Transaction)]

        filtered_txs = []
        import re

        for tx in txs:
            match = True
            if account_regex:
                if not any(re.search(account_regex, p.account) for p in tx.postings):
                    match = False
            if match and payee_regex:
                if not (tx.payee and re.search(payee_regex, tx.payee)):
                    match = False
            if match and tag:
                if not (tx.tags and tag in tx.tags):
                    match = False
            if match and currency:
                if not any(p.units and p.units.currency == currency for p in tx.postings):
                    match = False
            if match:
                filtered_txs.append(tx)

        if bql_where:
            try:
                import beanquery  # type: ignore
                from beancount.core.compare import hash_entry
                from beanquery.parser import ParseError  # type: ignore
                from beanquery.sources import beancount  # type: ignore

                conn = beanquery.Connection()
                table = beancount.PostingsTable(
                    self.ledger_service.entries, self.ledger_service.options
                )
                # Register as both postings and entries for convenience
                conn.tables["postings"] = table
                conn.tables["entries"] = table
                conn.tables[None] = table

                cursor = conn.cursor()
                # We use the 'id' column which refers to the parent transaction hash
                cursor.execute(f"SELECT id WHERE {bql_where}")
                ids = {r[0] for r in cursor.fetchall()}

                # Apply BQL IDs to current filtered list
                filtered_txs = [tx for tx in filtered_txs if hash_entry(tx) in ids]
            except (ImportError, SyntaxError, ValueError, ParseError) as e:
                raise ValueError(f"BQL query failed: {e}") from e

        return [from_core_transaction(tx) for tx in filtered_txs]

    def add_transaction(
        self, tx: TransactionModel, draft: bool = False, print_only: bool = False
    ) -> None:
        """
        Add a transaction to the ledger.
        """
        if draft:
            tx.flag = "!"
        else:
            tx.flag = "*"

        # Validate
        errors = self.validator.validate_transaction(tx)
        if errors:
            error_msg = "Transaction failed validation:\n" + "\n".join(f"- {e}" for e in errors)
            if not draft:
                raise ValueError(error_msg)
            else:
                print(f"Warning: {error_msg}", file=sys.stderr)

        core_tx = to_core_transaction(tx)
        entry_str = printer.format_entry(core_tx)

        if print_only:
            print(entry_str)
            return

        # Check for configured inbox
        inbox_file_str = self.ledger_service.get_custom_config("new_transaction_file")
        target_file = self.ledger_file

        if inbox_file_str:
            # Resolve relative to ledger file
            # Format pattern with transaction data
            # variables: {year}, {month}, {day}, {slug}, {payee}
            from datetime import datetime

            # Use transaction date if available, else today
            tx_date = tx.date

            placeholders = {
                "year": tx_date.year,
                "month": f"{tx_date.month:02d}",
                "day": f"{tx_date.day:02d}",
                "payee": "".join(c for c in (tx.payee or "unknown") if c.isalnum() or c in "_-"),
                "slug": "".join(
                    c for c in (tx.payee or tx.narration or "tx") if c.isalnum() or c in "_-"
                ),
            }

            try:
                formatted_path = inbox_file_str.format(**placeholders)
            except KeyError as e:
                # Fallback if unknown placeholder
                print(
                    f"Warning: Unknown placeholder {e} in new_transaction_file config. "
                    "Using raw string.",
                    file=sys.stderr,
                )
                formatted_path = inbox_file_str

            target_path = (self.ledger_file.parent / formatted_path).resolve()

            # If the formatted path ends in extension, treat as file.
            # If it doesn't, treat as dir and append default filename.
            # Simple heuristic: if it has an extension, it's a file.
            if target_path.suffix:
                # Ensure parent dirs exist
                target_path.parent.mkdir(parents=True, exist_ok=True)
                target_file = target_path

                # Append mode for existing file or new file
                mode = "a" if target_file.exists() else "w"
                with open(target_file, mode) as f:
                    if mode == "a":
                        f.write("\n")
                    f.write(entry_str)
                print(f"Transaction appended to {target_file}")
                return
            else:
                # Directory mode
                target_path.mkdir(parents=True, exist_ok=True)

                timestamp = datetime.now().strftime("%Y-%m-%dT%H%M%S%f")[:19]
                filename = f"{timestamp}_{placeholders['slug']}.beancount"
                target_file = target_path / filename

                with open(target_file, "w") as f:
                    f.write(entry_str)
                print(f"Transaction created in {target_file}")
                return

        with open(target_file, "a") as f:
            f.write("\n" + entry_str)
        print(f"Transaction appended to {target_file}")


class MapService:
    def __init__(self, root_file: Path):
        self.root_file = root_file

    def get_include_tree(self) -> dict[str, Any]:
        """
        Recursively find included files.
        Returns a nested dict: { "file.beancount": { "subfile.beancount": {} } }
        """
        tree: dict[str, Any] = {}
        with open(self.root_file, encoding="utf-8") as f:
            content = f.read()

        # Parse includes manually to avoid full loading overhead/flattening
        import re

        include_pattern = re.compile(r'^\s*include\s+"([^"]+)"', re.MULTILINE)

        for match in include_pattern.finditer(content):
            included_path_str = match.group(1)

            # Handle globs
            if "*" in included_path_str or "?" in included_path_str:
                # Resolve parent dir and glob pattern
                # Beancount includes are relative to the file containing the include
                base_dir = self.root_file.parent

                # If path is absolute (rare in beancount but possible)
                if Path(included_path_str).is_absolute():
                    # Glob on absolute path
                    # This is tricky as glob needs a root.
                    # Path(included_path_str).parent.glob(Path(included_path_str).name)
                    parent = Path(included_path_str).parent
                    pattern = Path(included_path_str).name
                    matches = list(parent.glob(pattern))
                else:
                    # Relative glob
                    # We need to construct the full path pattern
                    # But glob() is a method on Path.
                    # e.g. include "trades/*.beancount" -> base_dir.glob("trades/*.beancount")
                    matches = list(base_dir.glob(included_path_str))

                if not matches:
                    # Keep the glob pattern in tree to show it matched nothing
                    tree[f"{included_path_str} (No matches)"] = {}

                for m in sorted(matches):
                    sub_service = MapService(m)
                    tree[str(m)] = sub_service.get_include_tree()

            else:
                # Direct file
                included_path = (self.root_file.parent / included_path_str).resolve()
                sub_service = MapService(included_path)
                tree[str(included_path)] = sub_service.get_include_tree()

        return tree


class ReportService:
    def __init__(self, ledger_service: LedgerService):
        self.ledger = ledger_service

    def get_balances(
        self,
        account_roots: list[str] | None = None,
        convert_to: CurrencyCode.Input | None = None,
        valuation: str = "market",
    ) -> dict[str, dict[str, dict[str, Decimal]]]:
        """
        Return {account: {"units": {curr: amt}, "cost": {curr: amt}}},
        optionally filtered, converted, and valued.
        """
        self.ledger.load()
        from beancount.core import prices as prices_lib
        from beancount.core import realization

        real_root = realization.realize(self.ledger.entries)

        # Build price map if conversion needed
        prices = None
        if convert_to:
            prices = prices_lib.build_price_map(self.ledger.entries)

        balances = {}

        def traverse(node):
            # Compute cumulative balance
            cb = realization.compute_balance(node)
            if not cb.is_empty():
                units = {}
                cost = {}

                if convert_to:
                    # Valuation logic
                    total_converted = Decimal(0)
                    for pos in cb:
                        if pos.units.currency == convert_to:
                            total_converted += pos.units.number
                        # Get operating currencies for transitive conversion
                        # (e.g. PPFD -> EUR -> USD)
                        via_currencies = self.ledger.get_operating_currencies()

                        if valuation == "market":
                            # Use beancount.core.convert for robust conversion
                            # (handles indirect paths)
                            from beancount.core import convert

                            try:
                                converted_amt = convert.convert_amount(
                                    pos.units, convert_to, prices, via=via_currencies
                                )
                                if converted_amt.currency == convert_to:
                                    total_converted += converted_amt.number
                                else:
                                    # Fallback to cost if price not found?
                                    if pos.cost and pos.cost.currency == convert_to:
                                        total_converted += pos.units.number * pos.cost.number
                                    elif pos.cost:
                                        # Try converting cost to target
                                        from beancount import Amount

                                        cost_amt = Amount(
                                            pos.units.number * pos.cost.number, pos.cost.currency
                                        )
                                        converted_cost = convert.convert_amount(
                                            cost_amt, convert_to, prices, via=via_currencies
                                        )
                                        if converted_cost.currency == convert_to:
                                            total_converted += converted_cost.number
                                    else:
                                        units[pos.units.currency] = (
                                            units.get(pos.units.currency, Decimal(0))
                                            + pos.units.number
                                        )
                            except (KeyError, TypeError) as e:
                                raise ValueError(
                                    f"Failed to convert amount {pos.units} to {convert_to}"
                                ) from e
                        elif valuation == "cost":
                            # Cost valuation
                            from beancount.core import convert

                            if pos.cost:
                                from beancount import Amount

                                cost_amt = Amount(
                                    pos.units.number * pos.cost.number, pos.cost.currency
                                )
                                try:
                                    converted_cost = convert.convert_amount(
                                        cost_amt, convert_to, prices, via=via_currencies
                                    )
                                    if converted_cost.currency == convert_to:
                                        total_converted += converted_cost.number
                                    else:
                                        units[pos.units.currency] = (
                                            units.get(pos.units.currency, Decimal(0))
                                            + pos.units.number
                                        )
                                except (KeyError, TypeError) as e:
                                    raise ValueError(
                                        f"Failed to convert cost {cost_amt} to {convert_to}"
                                    ) from e
                            else:
                                # No cost (cash). Try converting units to target currency
                                # for cost basis
                                try:
                                    converted_units = convert.convert_amount(
                                        pos.units, convert_to, prices, via=via_currencies
                                    )
                                    if converted_units.currency == convert_to:
                                        total_converted += converted_units.number
                                    else:
                                        units[pos.units.currency] = (
                                            units.get(pos.units.currency, Decimal(0))
                                            + pos.units.number
                                        )
                                except (KeyError, TypeError) as e:
                                    raise ValueError(
                                        f"Failed to convert units {pos.units} to {convert_to}"
                                    ) from e
                        else:
                            # Not convertible under this valuation
                            units[pos.units.currency] = (
                                units.get(pos.units.currency, Decimal(0)) + pos.units.number
                            )

                    if total_converted != 0:
                        units[convert_to] = units.get(convert_to, Decimal(0)) + total_converted
                        cost[convert_to] = cost.get(convert_to, Decimal(0)) + total_converted
                else:
                    # Standard logic
                    for pos in cb:
                        u_curr = pos.units.currency
                        units[u_curr] = units.get(u_curr, Decimal(0)) + pos.units.number

                        if pos.cost and pos.cost.number is not None:
                            c_curr = pos.cost.currency
                            cost[c_curr] = cost.get(c_curr, Decimal(0)) + (
                                pos.units.number * pos.cost.number
                            )
                        else:
                            cost[u_curr] = cost.get(u_curr, Decimal(0)) + pos.units.number

                if (units or cost) and node.account:
                    balances[node.account] = {"units": units, "cost": cost}
            for child in node.values():
                traverse(child)

        if account_roots:
            for root in account_roots:
                if root in real_root:
                    traverse(real_root[root])
        else:
            traverse(real_root)

        return balances

    def get_holdings(
        self, valuation: str = "market", target_currencies: list[CurrencyCode.Input] | None = None
    ) -> dict[str, Any]:
        """
        Return structured holdings data for Assets.
        {
            "accounts": {
                account: {
                    "units": {curr: amt},
                    "market_values": {target: amt},
                    "cost_basis": {target: amt},
                    "unrealized_gains": {target: amt}
                }
            },
            "totals": {
                target: { "market": amt, "cost": amt, "gain": amt }
            }
        }
        """
        if not target_currencies:
            # Fallback to operating currencies or raw units
            target_currencies = self.ledger.get_operating_currencies()

        results: dict[str, Any] = {
            "accounts": {},
            "totals": {
                t: {"market": Decimal(0), "cost": Decimal(0), "gain": Decimal(0)}
                for t in (target_currencies or [])
            },
        }

        # 1. Get raw base balances (units and cost)
        base_balances = self.get_balances(account_roots=["Assets"], convert_to=None)

        # 2. Get converted balances for each target (Market and Cost)
        market_data = {}
        cost_data = {}
        for target in target_currencies or []:
            market_data[target] = self.get_balances(
                account_roots=["Assets"], convert_to=target, valuation="market"
            )
            cost_data[target] = self.get_balances(
                account_roots=["Assets"], convert_to=target, valuation="cost"
            )

        # 3. Identify leaf accounts and aggregate
        for acc in sorted(base_balances.keys()):
            has_child = any(other.startswith(acc + ":") for other in base_balances.keys())
            if not has_child:
                # This is a leaf account
                acc_holdings = {
                    "units": base_balances[acc]["units"],
                    "market_values": {},
                    "cost_basis": {},
                    "unrealized_gains": {},
                }

                for target in target_currencies or []:
                    # Market Value
                    m_bal = market_data[target].get(acc, {"units": {}})
                    m_val = m_bal["units"].get(target, Decimal(0))

                    # Cost Basis
                    c_bal = cost_data[target].get(acc, {"units": {}})
                    c_val = c_bal["units"].get(target, Decimal(0))

                    gain = m_val - c_val

                    acc_holdings["market_values"][target] = m_val
                    acc_holdings["cost_basis"][target] = c_val
                    acc_holdings["unrealized_gains"][target] = gain

                    results["totals"][target]["market"] += m_val
                    results["totals"][target]["cost"] += c_val
                    results["totals"][target]["gain"] += gain

                # Check if account has any non-zero holdings
                has_holdings = any(v != 0 for v in acc_holdings["units"].values())
                has_market = any(v != 0 for v in acc_holdings["market_values"].values())

                if has_holdings or has_market:
                    results["accounts"][acc] = acc_holdings

        return results


class AccountService:
    def __init__(self, ledger_file: Path):
        self.ledger_file = ledger_file
        self.ledger_service = LedgerService(ledger_file)

    def list_accounts(self) -> list[AccountModel]:
        self.ledger_service.load()
        # Find Open directives
        accounts = []
        for e in self.ledger_service.entries:
            if isinstance(e, data.Open):
                accounts.append(
                    AccountModel(
                        name=e.account,
                        open_date=e.date,
                        currencies=e.currencies if e.currencies else [],
                        meta=e.meta,
                    )
                )
        return sorted(accounts, key=lambda a: a.name)

    def create_account(self, account: AccountModel) -> None:
        """
        Create a new account by appending an Open directive.
        """
        self.ledger_service.load()
        existing = set(self.ledger_service.get_accounts())
        if account.name in existing:
            raise ValueError(f"Account '{account.name}' already exists.")

        # Create Open directive
        open_dir = data.Open(
            meta=account.meta,
            date=account.open_date or date.today(),
            account=account.name,
            currencies=account.currencies,
            booking=None,
        )

        entry_str = printer.format_entry(open_dir)

        # Determine where to write.
        # Ideally, we should find where other accounts are defined, but that's complex.
        # Check for cli-config "new_account_file"
        target_file = self.ledger_file
        config_file = self.ledger_service.get_custom_config("new_account_file")

        if config_file:
            target_path = (self.ledger_file.parent / config_file).resolve()
            if target_path.exists() or target_path.parent.exists():
                target_file = target_path

        with open(target_file, "a") as f:
            f.write("\n" + entry_str)
        print(f"Account created in {target_file}")


class CommodityService:
    def __init__(self, ledger_file: Path):
        self.ledger_file = ledger_file
        self.ledger_service = LedgerService(ledger_file)

    def create_commodity(
        self,
        currency: CurrencyCode.Input,
        name: str | None = None,
        meta: dict[str, Any] | None = None,
    ) -> None:
        """
        Create a Commodity directive.
        """
        self.ledger_service.load()
        existing = set(self.ledger_service.get_commodities())
        if str(currency) in existing:
            raise ValueError(f"Commodity '{currency}' already exists.")

        meta = meta or {}
        if name:
            meta["name"] = name

        comm_dir = data.Commodity(meta=meta, date=date.today(), currency=currency)

        entry_str = printer.format_entry(comm_dir)

        # Determine target file
        target_file = self.ledger_file
        config_file = self.ledger_service.get_custom_config("new_commodity_file")

        if config_file:
            target_path = (self.ledger_file.parent / config_file).resolve()
            if target_path.exists() or target_path.parent.exists():
                target_file = target_path

        with open(target_file, "a") as f:
            f.write("\n" + entry_str)
        print(f"Commodity created in {target_file}")
