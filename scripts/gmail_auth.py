"""One-time Gmail API connection (scope gmail.send only). Stores the token Fernet-encrypted.

uv run python scripts/gmail_auth.py path/to/client_secret.json
"""

import sys

from google_auth_oauthlib.flow import InstalledAppFlow

from escalate.channels.email_gmail import SCOPES, TOKEN_PATH, save_token


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    flow = InstalledAppFlow.from_client_secrets_file(sys.argv[1], SCOPES)
    creds = flow.run_local_server(port=0)
    save_token(creds.to_json())
    print(f"Saved encrypted token to {TOKEN_PATH}. Set EMAIL_MODE=gmail_api in .env.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
