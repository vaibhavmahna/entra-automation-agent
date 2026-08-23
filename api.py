import sys

from dotenv import load_dotenv
from fastapi import FastAPI
from pydantic import BaseModel

sys.path.insert(0, "src")

from graph_client import GraphClient
from tools import (
    disable_account,
    log_action,
    remove_all_group_memberships,
    revoke_sessions,
)

load_dotenv()

app = FastAPI(
    title="Plixa Offboarding Agent Tools",
    description="Deterministic actions the offboarding judgment agent can call. Each action operates on the sandbox tenant only.",
    version="1.0.0",
)


class ActionRequest(BaseModel):
    user_id: str
    reason: str


class EscalateRequest(BaseModel):
    user_id: str
    explanation: str


def _client() -> GraphClient:
    return GraphClient()


@app.post("/disable-account", operation_id="disableAccount")
def disable_account_endpoint(body: ActionRequest):
    """Disable the user's Entra ID account as part of standard offboarding."""
    disable_account(_client(), body.user_id)
    log_action("disable_account", body.user_id, body.reason)
    return {"status": "disabled", "user_id": body.user_id}


@app.post("/revoke-sessions", operation_id="revokeSessions")
def revoke_sessions_endpoint(body: ActionRequest):
    """Revoke all active sign-in sessions for the user."""
    revoke_sessions(_client(), body.user_id)
    log_action("revoke_sessions", body.user_id, body.reason)
    return {"status": "revoked", "user_id": body.user_id}


@app.post("/remove-group-memberships", operation_id="removeGroupMemberships")
def remove_group_memberships_endpoint(body: ActionRequest):
    """Remove the user from all their current group memberships."""
    client = _client()
    removed = remove_all_group_memberships(client, body.user_id)
    log_action("remove_group_memberships", body.user_id, f"{body.reason} Removed {len(removed)} group(s).")
    return {"status": "removed", "user_id": body.user_id, "groups_removed": len(removed)}


@app.post("/escalate", operation_id="escalateToHuman")
def escalate_endpoint(body: EscalateRequest):
    """Escalate this offboarding case to a human reviewer instead of proceeding automatically."""
    log_action("escalate", body.user_id, body.explanation, actor="plixa-judgment-agent")
    return {"status": "escalated", "user_id": body.user_id}
