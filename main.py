import argparse
import sys

from dotenv import load_dotenv

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


def run(user_identifier: str, execute: bool) -> None:
    client = GraphClient()

    user = get_user(client, user_identifier)
    user_id = user["id"]
    print(f"User: {user.get('displayName')} <{user.get('userPrincipalName')}>")

    admin_roles = check_admin_roles(client, user_id)
    if admin_roles:
        role_names = ", ".join(r.get("displayName", r["id"]) for r in admin_roles)
        print(f"ESCALATE: user holds directory role(s): {role_names}")
        print("Refusing to proceed automatically. Needs human sign-off.")
        return

    groups = [m for m in get_group_memberships(client, user_id) if m.get("@odata.type") == "#microsoft.graph.group"]
    group_names = [g.get("displayName", g["id"]) for g in groups]
    print(f"Current groups: {', '.join(group_names) or '(none)'}")

    if not execute:
        print("\nDry run only. Would perform, in order:")
        print("  1. Disable account")
        print("  2. Revoke active sessions")
        print(f"  3. Remove from {len(groups)} group(s)")
        print("\nRe-run with --execute to actually perform these actions.")
        return

    reason = "Standard offboarding: no directory roles or exceptions found."

    disable_account(client, user_id)
    log_action("disable_account", user_id, reason)
    print("Disabled account.")

    revoke_sessions(client, user_id)
    log_action("revoke_sessions", user_id, reason)
    print("Revoked active sessions.")

    removed = remove_all_group_memberships(client, user_id)
    log_action("remove_group_memberships", user_id, f"{reason} Removed {len(removed)} group(s).")
    print(f"Removed from {len(removed)} group(s).")

    print("\nOffboarding complete. See logs/audit.jsonl for the full trail.")


if __name__ == "__main__":
    load_dotenv()
    parser = argparse.ArgumentParser(description="Plixa offboarding demo agent (deterministic core, no LLM yet)")
    parser.add_argument("user", help="User's UPN or object ID in the sandbox tenant")
    parser.add_argument("--execute", action="store_true", help="Actually perform the actions (default is dry-run)")
    args = parser.parse_args()

    run(args.user, args.execute)
