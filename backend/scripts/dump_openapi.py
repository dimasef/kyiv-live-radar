"""Write the FastAPI OpenAPI schema to `openapi.json` at the repo root.

That file is the hand-off between the two languages: the backend produces it,
`frontend/npm run gen:types` turns it into `frontend/src/api-types.ts`. Keeping
it committed means neither CI job has to run the other language's toolchain —
each one regenerates its own artifact and fails if the result differs from what
was committed, so a schema change that never reached the frontend types is a
build failure instead of a runtime surprise.

    .venv/bin/python scripts/dump_openapi.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.main import app  # noqa: E402

OUT = Path(__file__).resolve().parent.parent.parent / "openapi.json"


def main() -> None:
    # sort_keys so the file is diff-stable across runs (FastAPI's dict order is
    # route-registration order, which shuffles when modules get reorganised).
    OUT.write_text(json.dumps(app.openapi(), indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
