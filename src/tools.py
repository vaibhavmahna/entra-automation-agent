import json
import logging
import os
import secrets
import string
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


def get_registered_recovery_contact(client: GraphClient, user_id: str) -> dict:
    """Returns whichever real, verified recovery contact Entra already has on
    file for this user - the authenticationMethods objects behind SSPR, not
    the unverified otherMails/mobilePhone profile fields (which Microsoft is
    retiring from SSPR entirely as of Sept 2026). Empty values mean the user
    has nothing registered to verify against - a signal to escalate."""
    email_methods = client.get(f"/users/{user_id}/authentication/emailMethods").get("value", [])
    phone_methods = client.get(f"/users/{user_id}/authentication/phoneMethods").get("value", [])
    mobile = next((p["phoneNumber"] for p in phone_methods if p.get("phoneType") == "mobile"), None)
    return {
        "email": email_methods[0]["emailAddress"] if email_methods else None,
        "phone": mobile,
    }


def issue_temporary_access_pass(client: GraphClient, user_id: str, lifetime_minutes: int = 60) -> dict:
    """Issues a one-time, time-limited Temporary Access Pass - the real Entra
    mechanism for signing in without a password. The caller never receives
    this directly from us; it's only ever delivered to their already-
    registered recovery contact, and the caller reads it back to prove
    they received it there."""
    resp = client.post(
        f"/users/{user_id}/authentication/temporaryAccessPassMethods",
        {"lifetimeInMinutes": lifetime_minutes, "isUsableOnce": True},
    )
    return resp.json()


def generate_temp_password(length: int = 16) -> str:
    """Generates a random password meeting Entra's default complexity rules
    (upper, lower, digit, symbol) for a forced-reset scenario."""
    symbols = "!@#$%^&*"
    alphabet = string.ascii_letters + string.digits + symbols
    while True:
        password = "".join(secrets.choice(alphabet) for _ in range(length))
        if (
            any(c.islower() for c in password)
            and any(c.isupper() for c in password)
            and any(c.isdigit() for c in password)
            and any(c in symbols for c in password)
        ):
            return password


def reset_password(client: GraphClient, user_id: str, new_password: str) -> None:
    """Sets a new password directly and forces a change at next sign-in - the
    same mechanism behind the Entra admin center's own 'Reset password' button."""
    client.patch(
        f"/users/{user_id}",
        {"passwordProfile": {"password": new_password, "forceChangePasswordNextSignIn": True}},
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
