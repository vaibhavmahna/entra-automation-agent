import json
import logging
import os
from datetime import datetime, timezone

from graph_client import GraphClient

LOG_PATH = os.path.join(os.path.dirname(__file__), "..", "logs", "audit.jsonl")
logger = logging.getLogger("plixa.audit")


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


def _resolve_object_id(client: GraphClient, identifier: str) -> str:
    """Group-membership endpoints require the directory object ID, not a UPN -
    unlike /users/{id}, which accepts either. Resolve whatever we're given."""
    if "@" not in identifier:
        return identifier
    return get_user(client, identifier)["id"]


def remove_all_group_memberships(client: GraphClient, user_id: str) -> list[str]:
    object_id = _resolve_object_id(client, user_id)
    memberships = get_group_memberships(client, object_id)
    removed = []
    for m in memberships:
        if m.get("@odata.type") != "#microsoft.graph.group":
            continue
        group_id = m["id"]
        client.delete(f"/groups/{group_id}/members/{object_id}/$ref", ignore_404=True)
        removed.append(group_id)
    return removed


def find_group(client: GraphClient, group_name: str) -> dict:
    result = client.get("/groups", params={"$filter": f"displayName eq '{group_name}'"})
    groups = result.get("value", [])
    if not groups:
        raise ValueError(f"No group found named {group_name!r}")
    return groups[0]


def list_group_members(client: GraphClient, group_id: str) -> list[dict]:
    result = client.get(f"/groups/{group_id}/members")
    return result.get("value", [])


def is_group_member(client: GraphClient, user_id: str, group_id: str) -> bool:
    object_id = _resolve_object_id(client, user_id)
    members = list_group_members(client, group_id)
    return any(m["id"] == object_id for m in members)


def add_group_membership(client: GraphClient, user_id: str, group_id: str) -> None:
    object_id = _resolve_object_id(client, user_id)
    client.post(
        f"/groups/{group_id}/members/$ref",
        {"@odata.id": f"https://graph.microsoft.com/v1.0/directoryObjects/{object_id}"},
    )


def log_action(action: str, user_id: str, reason: str, actor: str = "plixa-offboarding-agent") -> None:
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action": action,
        "user_id": user_id,
        "actor": actor,
        "reason": reason,
    }
    line = json.dumps(entry)

    # Always log via the standard logging module - Azure Functions forwards this
    # to Application Insights automatically, which is the durable audit trail in
    # the cloud (the deployed filesystem is read-only under Run-From-Package).
    logger.info("audit: %s", line)

    # Also write locally when possible, for convenience during local development.
    try:
        os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
        with open(LOG_PATH, "a") as f:
            f.write(line + "\n")
    except OSError:
        pass
