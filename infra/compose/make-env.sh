#!/usr/bin/env sh
# Write .env from .env.example, replacing every placeholder value with a random secret.
# Idempotent: refuses to overwrite an existing .env unless --force is given (SEC-19).
set -eu
cd "$(dirname "$0")/../.."
if [ -e .env ] && [ "${1:-}" != "--force" ]; then
  echo ".env exists; pass --force to regenerate it" >&2
  exit 1
fi
random() { openssl rand -hex 24; }
: > .env.tmp
while IFS= read -r line || [ -n "$line" ]; do
  case "$line" in
    *=change-me*)
      key=${line%%=*}
      comment=""
      case "$line" in *"#"*) comment="  #${line#*#}" ;; esac
      printf '%s=%s%s\n' "$key" "$(random)" "$comment" >> .env.tmp
      ;;
    *) printf '%s\n' "$line" >> .env.tmp ;;
  esac
done < .env.example
mv .env.tmp .env
chmod 600 .env
echo "wrote .env with generated secrets"
