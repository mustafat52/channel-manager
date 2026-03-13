"""
migrate_token.py
----------------
One-time script to convert token.pickle → gmail_token.json.

Run this ONCE before switching to the new gmail_client.py:
    python migrate_token.py

It reads your existing token.pickle and writes gmail_token.json
in the same directory. After confirming the worker works with the
new file, you can delete token.pickle.
"""

import os
import pickle
from google.oauth2.credentials import Credentials

PICKLE_PATH = os.environ.get("OLD_TOKEN_PATH", "token.pickle")
JSON_PATH   = os.environ.get("GMAIL_TOKEN_PATH", "gmail_token.json")

if not os.path.exists(PICKLE_PATH):
    print(f"ERROR: {PICKLE_PATH} not found. Nothing to migrate.")
    exit(1)

print(f"Reading {PICKLE_PATH}...")
with open(PICKLE_PATH, "rb") as f:
    creds = pickle.load(f)

if not isinstance(creds, Credentials):
    print("ERROR: token.pickle does not contain a Credentials object.")
    exit(1)

print(f"Writing {JSON_PATH}...")
with open(JSON_PATH, "w") as f:
    f.write(creds.to_json())

os.chmod(JSON_PATH, 0o600)
print(f"Done. Token saved to {JSON_PATH} with permissions 600.")
print(f"Verify the worker works, then delete {PICKLE_PATH}.")