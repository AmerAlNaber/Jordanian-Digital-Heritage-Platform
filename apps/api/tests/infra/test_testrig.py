"""The testing rig's deployment files (ADR-0010): overlay, edge configuration and bootstrap."""

from __future__ import annotations

import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[4]
COMPOSE = ROOT / "docker-compose.yml"
OVERLAY = ROOT / "infra/compose/compose.testrig.yaml"
CADDY = ROOT / "infra/compose/caddy"


def test_overlay_is_valid_yaml_that_only_overrides_known_services() -> None:
    base = yaml.safe_load(COMPOSE.read_text("utf-8"))["services"]
    overlay = yaml.safe_load(OVERLAY.read_text("utf-8"))["services"]
    unknown = set(overlay) - set(base) - {"testrig-users"}
    assert not unknown, unknown
    assert overlay["testrig-users"]["profiles"] == ["testrig"]
    assert overlay["testrig-users"]["image"] == "jdhp-keycloak:local"


def test_overlay_publishes_the_edge_only_and_routes_codes_to_the_mail_catcher() -> None:
    overlay = yaml.safe_load(OVERLAY.read_text("utf-8"))["services"]
    published = {svc: cfg.get("ports") for svc, cfg in overlay.items() if cfg.get("ports")}
    assert set(published) == {"caddy"}, published
    assert sorted(published["caddy"]) == ["443:443", "80:80"]
    for svc in ("api", "worker"):
        env = overlay[svc]["environment"]
        assert env["JDHP_ENV"] == "testrig"
        assert env["JDHP_SMS_PROVIDER"] == "email"
        assert env["JDHP_SMTP_HOST"] == "mailpit"
    assert overlay["mailpit"]["environment"]["MP_WEBROOT"] == "/mail/"


def test_the_rig_caddyfile_protects_the_inbox_and_the_console_with_basic_auth() -> None:
    text = (CADDY / "Caddyfile.testrig").read_text("utf-8")
    for path in ("/mail/*", "/auth/admin/*", "/auth/realms/master/*"):
        block = text[text.index(f"handle {path}") :]
        block = block[: block.index("}\n\t}") + 4]
        assert "basic_auth" in block, path
        assert "{$JDHP_TESTRIG_INBOX_HASH}" in block, path
    assert "import jdhp_routes" in text
    assert text.count("import /etc/caddy/routes.caddy") == 1


def test_every_caddyfile_shares_the_same_routes() -> None:
    routes = (CADDY / "routes.caddy").read_text("utf-8")
    assert routes.lstrip("#").strip().startswith("The platform")
    assert "(jdhp_routes) {" in routes
    for name in ("Caddyfile", "Caddyfile.testrig"):
        text = (CADDY / name).read_text("utf-8")
        assert "import /etc/caddy/routes.caddy" in text
        assert "import jdhp_routes" in text
        assert "reverse_proxy web:3000" not in text  # routes live in one place
    base = yaml.safe_load(COMPOSE.read_text("utf-8"))["services"]["caddy"]["volumes"]
    assert any(v.startswith("./infra/compose/caddy/routes.caddy:") for v in base)


def test_bootstrap_and_account_scripts_parse_and_never_print_secrets() -> None:
    for script in (
        ROOT / "deploy/testrig/bootstrap.sh",
        ROOT / "infra/compose/keycloak/testrig-users.sh",
    ):
        subprocess.run(["bash", "-n", str(script)], check=True)  # noqa: S603, S607
        text = script.read_text("utf-8")
        assert "set -euo pipefail" in text
        assert "echo $JDHP_TESTRIG_USER_PASSWORD" not in text
        assert 'echo "$JDHP_TESTRIG_USER_PASSWORD"' not in text
    bootstrap = (ROOT / "deploy/testrig/bootstrap.sh").read_text("utf-8")
    assert "umask 077" in bootstrap
    assert "chmod 600 .env" in bootstrap
    assert "sed 's/\\$/$$/g'" in bootstrap  # bcrypt hash escaped for Compose interpolation
