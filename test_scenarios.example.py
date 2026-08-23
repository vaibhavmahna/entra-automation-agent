# Copy this file to test_scenarios.py (gitignored) and fill in real
# identifiers from your own tenant. test_scenarios.py is never committed -
# it's specific to whichever tenant you're testing against.

SCENARIOS = [
    {
        "name": "offboarding: benign group only, no directory role",
        "type": "offboarding",
        "user": "clean-user@yourtenant.onmicrosoft.com",
        "expect": "proceed",
        "proceed_tools": {"disableAccount", "revokeSessions", "removeGroupMemberships"},
    },
    {
        "name": "offboarding: Global Administrator role",
        "type": "offboarding",
        "user": "admin-user@yourtenant.onmicrosoft.com",
        "expect": "escalate",
    },
    {
        "name": "access request: benign group",
        "type": "access_request",
        "user": "clean-user@yourtenant.onmicrosoft.com",
        "group": "SomeBenignGroup",
        "expect": "proceed",
        "proceed_tools": {"requestAccess"},
    },
    {
        "name": "access request: sensitive-sounding group",
        "type": "access_request",
        "user": "clean-user@yourtenant.onmicrosoft.com",
        "group": "Admins",
        "expect": "escalate",
    },
]
