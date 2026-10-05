"""Render the Keycloak realm template with the environment, for import at start.

Runs in the API image as a one-shot Compose service, because the Keycloak image carries no
shell tooling beyond bash. Every placeholder must resolve; the result must still be valid JSON.
"""

from __future__ import annotations

import json
import os
import pathlib
import sys

DEFAULTS = {
    "KC_SSL_REQUIRED": "external",
    "KC_SMTP_HOST": "mailpit",
    "KC_SMTP_PORT": "1025",
    "KC_SMTP_FROM": "noreply@localhost",
}
REQUIRED = ("KC_FRONTEND_URL", "KC_WEB_CLIENT_SECRET", "KC_STAFF_CLIENT_SECRET")


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        sys.stderr.write("usage: render-realm.py <template.json> <output.json>\n")
        return 2
    template = pathlib.Path(argv[1]).read_text("utf-8")
    values = {name: os.environ.get(name) or DEFAULTS.get(name) for name in (*REQUIRED, *DEFAULTS)}
    missing = [name for name, value in values.items() if not value]
    if missing:
        sys.stderr.write(f"missing environment: {', '.join(missing)}\n")
        return 1
    rendered = template
    for name, value in values.items():
        rendered = rendered.replace("${" + name + "}", json.dumps(value)[1:-1])
    json.loads(rendered)  # fail loudly before Keycloak would
    out = pathlib.Path(argv[2])
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(rendered, "utf-8")
    sys.stdout.write(f"rendered {out}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
