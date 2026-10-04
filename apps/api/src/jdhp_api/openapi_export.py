"""Write the OpenAPI document to a file: ``python -m jdhp_api.openapi_export out.json``.

Every public API change bumps the version and regenerates ``packages/schemas`` from this file.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from jdhp_api.main import openapi_document


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        sys.stderr.write("usage: python -m jdhp_api.openapi_export <output.json>\n")
        return 2
    output = Path(argv[1])
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(openapi_document(), indent=2, ensure_ascii=False) + "\n", "utf-8")
    sys.stdout.write(f"wrote {output}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
