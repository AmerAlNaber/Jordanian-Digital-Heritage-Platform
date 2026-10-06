#!/usr/bin/env bash
# Bring up the testing rig on a fresh Ubuntu 24.04 server (ADR-0010, docs/operations/testing-rig.md).
#
#   sudo bash deploy/testrig/bootstrap.sh --host heritage-test.example.org
#   sudo bash deploy/testrig/bootstrap.sh --host 203-0-113-10.sslip.io --branch main
#
# What it does, in order: installs Docker when missing, clones or updates the repository, writes
# .env with generated secrets, sets the public hostname and the testing-rig variables, builds the
# images, starts the stack, waits for the edge to answer, ingests the fictional seed library and
# creates one tester account per role. It prints where the credentials are; it never prints them.
#
# Re-running is safe: it keeps .env, updates the checkout, rebuilds and restarts.
set -euo pipefail

HOST=""; BRANCH="main"; REPO_URL="${JDHP_REPO_URL:-https://github.com/AmerAlNaber/Jordanian-Digital-Heritage-Platform.git}"
TARGET="${JDHP_TESTRIG_DIR:-/opt/jdhp}"; SKIP_SEED=0
while [ $# -gt 0 ]; do
  case "$1" in
    --host) HOST="$2"; shift 2 ;;
    --branch) BRANCH="$2"; shift 2 ;;
    --repo) REPO_URL="$2"; shift 2 ;;
    --dir) TARGET="$2"; shift 2 ;;
    --skip-seed) SKIP_SEED=1; shift ;;
    -h|--help) sed -n '2,12p' "$0"; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done
[ -n "$HOST" ] || { echo "--host is required: a DNS name that points at this server" >&2; exit 2; }
[ "$(id -u)" = "0" ] || { echo "run as root (sudo)" >&2; exit 2; }

log() { printf '\n==> %s\n' "$*"; }

log "Docker"
if ! command -v docker >/dev/null 2>&1; then
  apt-get update -q
  apt-get install -y -q ca-certificates curl git gnupg
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc
  . /etc/os-release
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu ${VERSION_CODENAME} stable" > /etc/apt/sources.list.d/docker.list
  apt-get update -q
  apt-get install -y -q docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
fi
command -v git >/dev/null 2>&1 || apt-get install -y -q git
docker compose version >/dev/null

log "Kernel setting OpenSearch needs"
sysctl -w vm.max_map_count=262144 >/dev/null
grep -qs '^vm.max_map_count' /etc/sysctl.conf || echo 'vm.max_map_count=262144' >> /etc/sysctl.conf

log "Repository at $TARGET (branch $BRANCH)"
if [ -d "$TARGET/.git" ]; then
  git -C "$TARGET" fetch -q origin "$BRANCH"
  git -C "$TARGET" checkout -q "$BRANCH"
  git -C "$TARGET" pull -q --ff-only origin "$BRANCH"
else
  git clone -q --branch "$BRANCH" "$REPO_URL" "$TARGET"
fi
cd "$TARGET"

log "Configuration"
if [ ! -e .env ]; then
  sh infra/compose/make-env.sh
fi
set_var() { # set_var KEY VALUE: replace or append KEY=VALUE in .env
  local key="$1" value="$2"
  if grep -q "^${key}=" .env; then
    python3 - "$key" "$value" <<'PY'
import sys, re, pathlib
key, value = sys.argv[1], sys.argv[2]
p = pathlib.Path(".env"); text = p.read_text()
text = re.sub(rf"^{re.escape(key)}=.*$", lambda m: f"{key}={value}", text, flags=re.M)
p.write_text(text)
PY
  else
    printf '%s=%s\n' "$key" "$value" >> .env
  fi
}
set_var JDHP_ENV testrig
set_var JDHP_PUBLIC_HOST "$HOST"
set_var JDHP_PUBLIC_BASE_URL "https://$HOST"
set_var JDHP_API_BASE_URL "https://$HOST/api"
set_var JDHP_SMS_PROVIDER email
set_var KC_SSL_REQUIRED external
if ! grep -q '^JDHP_TESTRIG_INBOX_HASH=' .env || grep -q '^JDHP_TESTRIG_INBOX_HASH=$' .env; then
  inbox_password="$(openssl rand -base64 18 | tr -d '/+=' | cut -c1-20)"
  # Compose reads .env with $-interpolation, so every $ of the bcrypt hash is doubled.
  inbox_hash="$(docker run --rm caddy:2.9-alpine caddy hash-password --plaintext "$inbox_password" | sed 's/\$/$$/g')"
  set_var JDHP_TESTRIG_INBOX_USER tester
  set_var JDHP_TESTRIG_INBOX_HASH "$inbox_hash"
  umask 077; printf 'inbox user: tester\ninbox password: %s\n' "$inbox_password" > "$TARGET/.testrig-inbox-credentials"
fi
grep -q '^JDHP_TESTRIG_USER_PASSWORD=' .env || set_var JDHP_TESTRIG_USER_PASSWORD "$(openssl rand -base64 18 | tr -d '/+=' | cut -c1-20)"
chmod 600 .env

export COMPOSE_FILE="docker-compose.yml:infra/compose/compose.testrig.yaml"
log "Images"
docker compose build --pull
log "Stack"
docker compose up -d --remove-orphans
log "Waiting for the edge"
for i in $(seq 1 90); do
  code="$(curl -sk -o /dev/null -w '%{http_code}' "https://$HOST/ar" || true)"
  [ "$code" = "200" ] && break
  sleep 5
done
echo "edge answered with HTTP ${code:-none}"
if [ "$SKIP_SEED" = "0" ]; then
  log "Seed library"
  docker compose run --rm seed
fi
log "Tester accounts"
docker compose --profile testrig run --rm testrig-users

cat <<SUMMARY

Testing rig is up.
  Site:         https://$HOST/ar   (English: /en)
  Test inbox:   https://$HOST/mail/   (basic auth; credentials in $TARGET/.testrig-inbox-credentials)
  Identity:     https://$HOST/auth/admin/   (same basic auth, then KEYCLOAK_ADMIN from .env)
  Accounts:     member@$HOST, curator@$HOST, reviewer@$HOST, rights-officer@$HOST, platform-admin@$HOST
                password: JDHP_TESTRIG_USER_PASSWORD in $TARGET/.env
  Logs:         cd $TARGET && COMPOSE_FILE=$COMPOSE_FILE docker compose logs -f
  Update:       sudo bash $TARGET/deploy/testrig/bootstrap.sh --host $HOST --branch $BRANCH --skip-seed
SUMMARY
