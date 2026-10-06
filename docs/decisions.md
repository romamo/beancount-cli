# Decisions

Rules the maintainers settled, numbered in order. Triage designs and code reviews check
every change against the entries whose "Applies to" it touches. Change a rule by adding an
entry that supersedes it, never by editing an old one.

## D-1: An invalid ledger option refuses with LEDGER_INVALID

- Decided: 2026-10-06, in romamo/beancount-cli#33
- Rule: When a ledger option the CLI reads (custom config such as new_transaction_file) is malformed, the command exits 80 LEDGER_INVALID before writing anything, also under --dry-run, naming the option in error.context; it never falls back to a guess or only warns
- Why: Fail fast: a fallback such as writing to the raw new_transaction_file pattern creates files the user never meant, and an agent only sees effect created
- Applies to: src/beancount_cli/services.py, ledger custom options, exit codes
- Enforced by: review

## D-2: An explicit --target beats ledger config

- Decided: 2026-10-06, in romamo/beancount-cli#37
- Rule: When a write command gets --target, it writes there even if the ledger sets new_transaction_file; the ledger option is still read and a malformed one still refuses with LEDGER_INVALID (D-1)
- Why: The caller named that file; silently writing elsewhere surprises an agent that only checks effect created
- Applies to: src/beancount_cli/services.py, src/beancount_cli/commands/transaction.py, --target, new_transaction_file
- Enforced by: review, regression test
