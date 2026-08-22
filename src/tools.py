import json
import os
from datetime import datetime, timezone

from graph_client import GraphClient

LOG_PATH = os.path.join(os.path.dirname(__file__), "..", "logs", "audit.jsonl")


def get_user(client: GraphClient, identifier: str) -> dict:
    return client.get(f"/users/{identifier}")


def get_group_memberships(client: GraphClient, user_id: str) -> list[dict]:
    result = client.get(f"/users/{user_id}/memberOf")
    return result.get("value", [])


def check_admin_roles(client: GraphClient, user_id: str) -> list[dict]:
    memberships = get_group_memberships(client, user_id)
    return [m for m in memberships if m.get("@odata.type") == "#microsoft.graph.directoryRole"]


def disable_account(client: GraphClient, user_id: str) -> None:
    client.patch(f"/users/{user_id}", {"accountEnabled": False})


def revoke_sessions(client: GraphClient, user_id: str) -> None:
    client.post(f"/users/{user_id}/revokeSignInSessions")


def remove_all_group_memberships(client: GraphClient, user_id: str) -> list[str]:
    memberships = get_group_memberships(client, user_id)
    removed = []
    for m in memberships:
        if m.get("@odata.type") != "#microsoft.graph.group":
            continue
        group_id = m["id"]
        client.delete(f"/groups/{group_id}/members/{user_id}/$ref")
        removed.append(group_id)
    return removed


def log_action(action: str, user_id: str, reason: str, actor: str = "plixa-offboarding-agent") -> None:
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action": action,
        "user_id": user_id,
        "actor": actor,
        "reason": reason,
    }
    with open(LOG_PATH, "a") as f:
        f.write(json.dumps(entry) + "\n")
