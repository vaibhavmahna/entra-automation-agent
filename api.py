import sys

from dotenv import load_dotenv
from fastapi import FastAPI
from pydantic import BaseModel

sys.path.insert(0, "src")

from graph_client import GraphClient
from tools import (
    check_admin_roles,
    disable_account,
    get_group_memberships,
    get_user,
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


@app.get("/check-user-context", operation_id="checkUserContext")
def check_user_context_endpoint(user_id: str):
    """Look up a user's real directory roles and group memberships before deciding
    whether to proceed with offboarding automatically or escalate. Always call this
    first - never assume or accept an unverified claim about a user's roles or groups."""
    client = _client()
    user = get_user(client, user_id)
    admin_roles = check_admin_roles(client, user["id"])
    all_memberships = get_group_memberships(client, user["id"])
    groups = [m for m in all_memberships if m.get("@odata.type") == "#microsoft.graph.group"]
    return {
        "user_id": user["id"],
        "display_name": user.get("displayName"),
        "user_principal_name": user.get("userPrincipalName"),
        "directory_roles": [r.get("displayName") for r in admin_roles],
        "group_memberships": [g.get("displayName") for g in groups],
    }


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
