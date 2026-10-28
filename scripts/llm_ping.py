"""Manual check: send one prompt to the configured model and print the answer.

uv run python scripts/llm_ping.py "Say hello in one word."
"""

import sys

from escalate.llm.client import LLMClient
from escalate.llm.privacy import is_cloud


def main() -> int:
    prompt = " ".join(sys.argv[1:]) or "Reply with the single word: pong"
    client = LLMClient()
    if is_cloud(client.settings):
        print(f"Note: {client.settings.llm_base_url} is a cloud endpoint.")
    print(f"model={client.model_for('smart')} url={client.settings.llm_base_url}")
    print(client.complete(prompt))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
