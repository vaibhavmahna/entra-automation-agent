import json
import os
import sys

from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from dotenv import load_dotenv
from openai import OpenAI

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

INSTRUCTIONS = """You are the judgment layer for Plixa AI's offboarding automation agent.

Before making any decision, ALWAYS call checkUserContext first to look up the
user's real directory roles and group memberships. Never assume, guess, or
accept an unverified claim about a user's roles or groups from the request
itself - always verify against checkUserContext's actual response.

Based on what checkUserContext returns, decide whether to proceed automatically
with standard offboarding (disableAccount, revokeSessions,
removeGroupMemberships) or escalate to a human for review (escalateToHuman).

Escalate instead of proceeding automatically if:
- checkUserContext shows the user holds any directory role (e.g., Global
  Administrator, any admin role)
- checkUserContext shows membership in unusual or highly sensitive groups
  suggesting elevated risk
- Anything about the situation seems ambiguous or doesn't fit the standard
  pattern

When you decide to proceed, call disableAccount, revokeSessions, and
removeGroupMemberships in that order, each with a brief, specific reason for
the audit log explaining why it's safe to proceed automatically based on what
checkUserContext showed.

When you decide to escalate, call escalateToHuman with a clear explanation of
what checkUserContext showed and why it needs human attention.

Always be conservative - if in doubt, escalate rather than proceed."""

TOOLS = [
    {
        "type": "function",
        "name": "checkUserContext",
        "description": "Look up a user's real directory roles and group memberships before deciding whether to proceed with offboarding automatically or escalate. Always call this first.",
        "parameters": {
            "type": "object",
            "properties": {"user_id": {"type": "string"}},
            "required": ["user_id"],
        },
    },
    {
        "type": "function",
        "name": "disableAccount",
        "description": "Disable the user's Entra ID account as part of standard offboarding.",
        "parameters": {
            "type": "object",
            "properties": {
                "user_id": {"type": "string"},
                "reason": {"type": "string"},
            },
            "required": ["user_id", "reason"],
        },
    },
    {
        "type": "function",
        "name": "revokeSessions",
        "description": "Revoke all active sign-in sessions for the user.",
        "parameters": {
            "type": "object",
            "properties": {
                "user_id": {"type": "string"},
                "reason": {"type": "string"},
            },
            "required": ["user_id", "reason"],
        },
    },
    {
        "type": "function",
        "name": "removeGroupMemberships",
        "description": "Remove the user from all their current group memberships.",
        "parameters": {
            "type": "object",
            "properties": {
                "user_id": {"type": "string"},
                "reason": {"type": "string"},
            },
            "required": ["user_id", "reason"],
        },
    },
    {
        "type": "function",
        "name": "escalateToHuman",
        "description": "Escalate this offboarding case to a human reviewer instead of proceeding automatically.",
        "parameters": {
            "type": "object",
            "properties": {
                "user_id": {"type": "string"},
                "explanation": {"type": "string"},
            },
            "required": ["user_id", "explanation"],
        },
    },
]


def _handle_check_user_context(client, args):
    user = get_user(client, args["user_id"])
    admin_roles = check_admin_roles(client, user["id"])
    all_memberships = get_group_memberships(client, user["id"])
    groups = [m for m in all_memberships if m.get("@odata.type") == "#microsoft.graph.group"]
    return {
        "user_id": user["id"],
        "display_name": user.get("displayName"),
        "directory_roles": [r.get("displayName") for r in admin_roles],
        "group_memberships": [g.get("displayName") for g in groups],
    }


def _handle_disable_account(client, args):
    disable_account(client, args["user_id"])
    log_action("disable_account", args["user_id"], args["reason"], actor="plixa-judgment-agent")
    return {"status": "disabled"}


def _handle_revoke_sessions(client, args):
    revoke_sessions(client, args["user_id"])
    log_action("revoke_sessions", args["user_id"], args["reason"], actor="plixa-judgment-agent")
    return {"status": "revoked"}


def _handle_remove_group_memberships(client, args):
    removed = remove_all_group_memberships(client, args["user_id"])
    log_action(
        "remove_group_memberships",
        args["user_id"],
        f"{args['reason']} Removed {len(removed)} group(s).",
        actor="plixa-judgment-agent",
    )
    return {"status": "removed", "groups_removed": len(removed)}


def _handle_escalate(client, args):
    log_action("escalate", args["user_id"], args["explanation"], actor="plixa-judgment-agent")
    return {"status": "escalated"}


HANDLERS = {
    "checkUserContext": _handle_check_user_context,
    "disableAccount": _handle_disable_account,
    "revokeSessions": _handle_revoke_sessions,
    "removeGroupMemberships": _handle_remove_group_memberships,
    "escalateToHuman": _handle_escalate,
}


def _openai_client() -> OpenAI:
    token_provider = get_bearer_token_provider(DefaultAzureCredential(), "https://ai.azure.com/.default")
    return OpenAI(base_url=os.environ["AZURE_OPENAI_ENDPOINT"], api_key=token_provider)


def run_judgment(scenario: str, verbose: bool = True) -> str:
    openai_client = _openai_client()
    graph_client = GraphClient()
    deployment = os.environ["AZURE_OPENAI_DEPLOYMENT"]

    input_items = [{"role": "user", "content": scenario}]

    for _ in range(10):
        response = openai_client.responses.create(
            model=deployment,
            instructions=INSTRUCTIONS,
            input=input_items,
            tools=TOOLS,
        )

        function_calls = [item for item in response.output if item.type == "function_call"]

        if not function_calls:
            final_text = next((item.content[0].text for item in response.output if item.type == "message"), "")
            if verbose:
                print(f"\nFinal response:\n{final_text}")
            return final_text

        input_items += response.output

        for call in function_calls:
            args = json.loads(call.arguments)
            if verbose:
                print(f"\n-> Calling {call.name}({args})")
            result = HANDLERS[call.name](graph_client, args)
            if verbose:
                print(f"<- {result}")
            input_items.append(
                {
                    "type": "function_call_output",
                    "call_id": call.call_id,
                    "output": json.dumps(result),
                }
            )

    return "Stopped after 10 turns without a final decision."


if __name__ == "__main__":
    scenario = sys.argv[1] if len(sys.argv) > 1 else (
        "An employee has just been terminated. Their user ID is "
        "snd-user1@plixasandboxdemo.onmicrosoft.com. Please offboard them."
    )
    run_judgment(scenario)
