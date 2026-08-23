import argparse
import sys

from dotenv import load_dotenv

sys.path.insert(0, "src")

from graph_client import GraphClient
from tools import add_group_membership, find_group, get_user, is_group_member, log_action


def run(user_identifier: str, group_name: str, execute: bool) -> None:
    client = GraphClient()

    user = get_user(client, user_identifier)
    user_id = user["id"]
    print(f"User: {user.get('displayName')} <{user.get('userPrincipalName')}>")

    group = find_group(client, group_name)
    group_id = group["id"]
    print(f"Group: {group.get('displayName')}")

    if is_group_member(client, user_id, group_id):
        print(f"\n{user.get('displayName')} is already a member of {group_name}. Nothing to do.")
        return

    if not execute:
        print(f"\nDry run only. Would add {user.get('displayName')} to {group_name}.")
        print("\nRe-run with --execute to actually perform this action.")
        return

    reason = f"Access request approved: add to {group_name}."

    add_group_membership(client, user_id, group_id)
    log_action("add_group_membership", user_id, reason)
    print(f"\nAdded {user.get('displayName')} to {group_name}.")
    print("See logs/audit.jsonl for the full trail.")


if __name__ == "__main__":
    load_dotenv()
    parser = argparse.ArgumentParser(description="Plixa access request demo agent (deterministic core, no LLM yet)")
    parser.add_argument("user", help="User's UPN or object ID in the sandbox tenant")
    parser.add_argument("group", help="Target group's display name")
    parser.add_argument("--execute", action="store_true", help="Actually perform the action (default is dry-run)")
    args = parser.parse_args()

    run(args.user, args.group, args.execute)
