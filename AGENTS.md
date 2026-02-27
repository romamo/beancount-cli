# AGENTS.md - Beancount CLI Guide for AI End Agents

This document provides instructions for **AI Agents** operating the Beancount CLI to manage or query a user's accounting data. 

*(If you are an AI Coding Agent tasked with modifying the python source code of this repository, please refer to `CODING_AGENTS.md` instead).*

---

## 1. Operating Rules & Workflows

If you are executing shell commands to help a human analyze or modify their `main.beancount` ledger, adhere to the following operational rules:

### Core Configuration & Bootstrapping
- **Ledger Path**: The CLI requires a target `.beancount` file. You can either pass it directly via `--file /path/to/main.beancount` or set the environment variable: `export BEANCOUNT_FILE=/path/to/main.beancount`.
- **Self Discovery**: If you are unsure about the available arguments for a command, ALWAYS run `uv run bean <command> --help` to read the descriptive schemas and examples embedded directly in the source code.

### Available Capabilities (High-Level)
- **`account list/create`**: Create and list chart of accounts.
- **`transaction list/add`**: Query and batch insert accounting transactions.
- **`report`**: Generate detailed mathematical rollups (`balance-sheet`, `trial-balance`, `holdings`, `audit`).
- **`commodity`**: Manage currency rules.
- **`price`**: Fetch remote price quotes for commodities.
- **`format/tree`**: Maintain correct text indentation and view include trees.
- **Single Item Retrieval**: Use `--format json` when you require nested, hierarchical data structures.
- **Human Display**: The default format is `table`. Only use this if you are dumping the raw execution output directly to the user's terminal interface. 

### Advanced JSON Data Pipelines
- **Data Insertion**: Write commands (like `transaction add`, `account create`, `commodity create`) accept rigorous JSON payloads dynamically through STDIN (`--json -`).
- **Schema Discovery**: If you need to know the required JSON structure to insert a transaction via STDIN, DO NOT GUESS. Run:
   ```bash
   uv run bean transaction schema
   ``` 
   This will output the exact Pydantic boundary schema expected by the application.
- **Native BQL**: `transaction list` supports Beancount Query Language (BQL) directly via the `--where` flag (e.g., `uv run bean transaction list --where "account ~ 'Expenses'"`).
- **Unix Composability**: Use the global `--format` flag *before* the command to pipe outputs.
   - *Example Pipeline:* `uv run bean --format json account list | uv run bean account create --json -`
- **Batch Processing**: Never loop shell executions to insert items one-by-one! Construct a massive JSON array and pipe the entire array to `transaction add --json -` for instantaneous batch processing.
