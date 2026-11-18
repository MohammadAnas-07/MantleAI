"""Write the API's OpenAPI schema as JSON, for the frontend's generated types.

No server, no database: it only imports the app. Keys are sorted so the file diffs cleanly.

    python scripts/export_openapi.py ../frontend/src/lib/api/openapi.json
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.main import app  # noqa: E402


def main() -> None:
    text = json.dumps(app.openapi(), indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    if len(sys.argv) > 1:
        Path(sys.argv[1]).write_text(text, encoding="utf-8", newline="\n")
    else:
        sys.stdout.write(text)


if __name__ == "__main__":
    main()
