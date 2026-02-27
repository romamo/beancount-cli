# Bkper CLI Competitor Analysis

## Overview

[bkper-cli](https://github.com/bkper/bkper-cli) is a command-line interface for [Bkper](https://bkper.com/), a Google-centric financial accounting platform. It allows users to manage financial data (books, accounts, transactions, balances) and to build, deploy, and manage Bkper apps directly from the terminal. 

## Technical Stack
- **Language**: TypeScript (using raw ESM modules, strict mode)
- **Runtime**: Node.js (>= 18)
- **Tooling**: Bun (primary dependency manager/runner), Mocha & Chai (testing), GTS (Google TypeScript Setup for style enforcement), OpenAPI TypeScript (for type generation).
- **Core Dependencies**: `commander` (CLI framework), `bkper-js` (their API client), `esbuild`, `vite` (for app dev server), `yaml`.

## Core Capabilities

### 1. Data Management
- **Books & Collections**: Create, list, configure settings (locales, timezones, decimal separators).
- **Chart of Accounts**: Manage accounts, nest them into groups, and define their type (Asset, Liability, Incoming, Outgoing).
- **Transactions**: Full CRUD support. Draft transactions, post them, check/reconcile, merge duplicates, and query using an advanced search syntax (e.g., `-q "after:2025-01-01"`).
- **Balances**: Aggregated balance reporting with tree/level expansion.

### 2. Output Formatting & Composability (Standout Features)
Bkper CLI heavily emphasizes programmatic use:
- **Formats**: Supports `table` (default, human-readable), `json` (single-item details, data transfer), and `csv` (for list commands).
- **AI Agent Native**: It explicitly documents CSV usage for AI agents to save token usage (3-5x fewer tokens compared to JSON).
- **Unix Piping**: Commands are designed to be piped. A `list` command can output JSON, which is directly piped into a `create` or `update` command. 
  - *Example*: `bkper account list -b SOURCE --format json | bkper account create -b DEST`
- **Batch Operations**: Most `create` or `update` operations accept JSON arrays via STDIN to process batch updates efficiently.

### 3. Application Lifecycle Management
- Developers can build apps interacting with Bkper.
- Commands help scaffold (`app init`), run local dev servers (`app dev`), deploy to Cloudflare Workers (`app deploy`), and manage secrets.

## Project Structure & Engineering Standards
- **Strict Typing**: No `any` types allowed. Highly structured domain logic isolated from presentation (`src/domain`, `src/commands`, `src/render`).
- **Testing**: Separated into unit tests, integration tests (running against a local/remote API), and deployment tests. Test files mirror the exact hierarchy of the source files.
- **Documentation**: A detailed `README.md` aiming at both users and developers, plus an `AGENTS.md` file specifically designed to instruct LLM code assistants on how to navigate the repository, testing commands, and coding guidelines.

## Key Takeaways for Beancount-CLI
1. **Piping & Composability**: Allowing our CLI to accept JSON/CSV output from one command (like querying transactions) into another (bulk update/edit) via STDIN is incredibly powerful.
2. **AI-Targeted Documentation**: Creating an `AGENTS.md` and explicitly detailing the most token-efficient output formats (like prioritizing CSV over JSON for lists) is a great pattern.
3. **Batch Processing**: Supporting batch transaction or account creation via STDIN prevents heavy overhead when importing large datasets.
4. **Output Formats**: A global flag for output formatting (`--format table|json|csv`) should be a strong consideration if not already present.
