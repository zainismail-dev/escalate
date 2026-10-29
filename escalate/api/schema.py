"""Print the API's OpenAPI schema (it is not served unless API_DOCS=true).

uv run python -m escalate.api.schema > openapi.json
"""

import json

from escalate.api.main import create_app

if __name__ == "__main__":
    print(json.dumps(create_app(startup=False).openapi(), indent=2))
