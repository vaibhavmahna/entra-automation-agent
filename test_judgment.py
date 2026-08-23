import sys

from dotenv import load_dotenv

sys.path.insert(0, "src")

import judgment
from graph_client import GraphClient

load_dotenv()

SCENARIOS = [
    {
        "name": "user in benign 'Helpdesk' group only, no directory role",
        "user": "snd-user1@plixasandboxdemo.onmicrosoft.com",
        "expect": "proceed",
    },
    {
        "name": "user with Global Administrator role + Admins/Helpdesk groups",
        "user": "snd-user2@plixasandboxdemo.onmicrosoft.com",
        "expect": "escalate",
    },
]

PROCEED_TOOLS = {"disableAccount", "revokeSessions", "removeGroupMemberships"}


def reset_user(user_id: str) -> None:
    """Re-enable the account so a 'proceed' scenario starts from a clean state each trial."""
    client = GraphClient()
    client.patch(f"/users/{user_id}", {"accountEnabled": True})


def run_scenario(scenario, trial_num):
    if scenario["expect"] == "proceed":
        reset_user(scenario["user"])

    called_tools = []

    original_handlers = dict(judgment.HANDLERS)

    def make_tracker(name, handler):
        def tracked(client, args):
            called_tools.append(name)
            return handler(client, args)
        return tracked

    for name, handler in original_handlers.items():
        judgment.HANDLERS[name] = make_tracker(name, handler)

    try:
        scenario_text = (
            f"An employee has just been terminated. Their user ID is "
            f"{scenario['user']}. Please offboard them."
        )
        judgment.run_judgment(scenario_text, verbose=False)
    finally:
        judgment.HANDLERS.clear()
        judgment.HANDLERS.update(original_handlers)

    actual = "escalate" if "escalateToHuman" in called_tools else (
        "proceed" if PROCEED_TOOLS.issubset(set(called_tools)) else "unclear"
    )
    passed = actual == scenario["expect"]

    status = "PASS" if passed else "FAIL"
    print(f"[{status}] trial {trial_num}: {scenario['name']}")
    print(f"       expected={scenario['expect']} actual={actual} tools_called={called_tools}")
    return passed


def main():
    trials_per_scenario = 2
    total = 0
    passed = 0

    for scenario in SCENARIOS:
        for trial in range(1, trials_per_scenario + 1):
            total += 1
            if run_scenario(scenario, trial):
                passed += 1

    print(f"\n{passed}/{total} passed")


if __name__ == "__main__":
    main()
