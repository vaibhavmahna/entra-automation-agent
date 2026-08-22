# Plixa Offboarding Demo Agent

Deterministic core for the offboarding & deprovisioning workflow, built against the
sandbox Entra tenant. Given a user, it disables the account, revokes active sessions,
and removes group memberships — with a hardcoded safety check that refuses to
proceed automatically if the user holds any directory role (admin), until the
LLM judgment layer replaces that check with something smarter.

The LLM/agent layer (trigger interpretation, risk classification, orchestration,
audit-reason generation) is a separate, not-yet-built phase on top of this.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Fill in `.env` with the sandbox tenant's app registration details:
- `GRAPH_TENANT_ID`
- `GRAPH_CLIENT_ID`
- `GRAPH_CLIENT_SECRET`

Required Graph API application permissions (with admin consent granted in the
sandbox tenant): `User.ReadWrite.All`, `GroupMember.ReadWrite.All`,
`Directory.Read.All` (for reading directory role assignments).

## Usage

Dry run (no writes, just shows what would happen):

```bash
python main.py someone@plixademosandbox.onmicrosoft.com
```

Actually perform the offboarding:

```bash
python main.py someone@plixademosandbox.onmicrosoft.com --execute
```

Every real action is appended to `logs/audit.jsonl`.
