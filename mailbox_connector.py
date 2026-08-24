import os
import sys
import time

from dotenv import load_dotenv

sys.path.insert(0, "src")

import judgment
from graph_client import GraphClient

load_dotenv()

POLL_INTERVAL_SECONDS = 60


def _mail_client() -> GraphClient:
    return GraphClient(
        tenant_id=os.environ["MAIL_TENANT_ID"],
        client_id=os.environ["MAIL_CLIENT_ID"],
        client_secret=os.environ["MAIL_CLIENT_SECRET"],
    )


def fetch_unread_messages(client: GraphClient, mailbox: str) -> list[dict]:
    result = client.get(
        f"/users/{mailbox}/messages",
        params={
            "$filter": "isRead eq false",
            "$orderby": "receivedDateTime asc",
            "$select": "id,subject,bodyPreview,from,receivedDateTime",
            "$top": 10,
        },
    )
    return result.get("value", [])


def mark_as_read(client: GraphClient, mailbox: str, message_id: str) -> None:
    client.patch(f"/users/{mailbox}/messages/{message_id}", {"isRead": True})


def poll_once(verbose: bool = True) -> int:
    """Check the mailbox once for unread messages, run each through the
    judgment engine, and mark handled ones read. Returns how many were processed."""
    mailbox = os.environ["MAIL_MAILBOX"]
    client = _mail_client()
    messages = fetch_unread_messages(client, mailbox)

    for msg in messages:
        sender = msg.get("from", {}).get("emailAddress", {}).get("address", "unknown sender")
        subject = msg.get("subject", "")
        body = msg.get("bodyPreview", "")
        scenario = f"Email from {sender}, subject '{subject}': {body}"

        if verbose:
            print(f"\n=== New message from {sender}: {subject} ===")

        try:
            judgment.run_judgment(scenario, verbose=verbose)
        except Exception as exc:
            print(f"Error processing message {msg['id']}, leaving unread for retry: {exc}")
            continue

        # Only mark read after a successful run - escalating is a normal,
        # successful outcome; an exception means something needs a look.
        mark_as_read(client, mailbox, msg["id"])

    return len(messages)


def run_forever() -> None:
    print(f"Watching {os.environ['MAIL_MAILBOX']} every {POLL_INTERVAL_SECONDS}s. Ctrl+C to stop.")
    while True:
        poll_once()
        time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--once":
        count = poll_once()
        print(f"\nProcessed {count} message(s).")
    else:
        run_forever()
