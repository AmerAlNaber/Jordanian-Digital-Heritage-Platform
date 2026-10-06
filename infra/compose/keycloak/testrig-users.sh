#!/usr/bin/env bash
# Testing rig only (ADR-0010): one account per role so testers can sign in without registering.
# Every account is marked verified; staff accounts still enrol a one-time code on first sign-in,
# and the platform admin a hardware key, exactly as real staff would (SEC-3).
# Never run against a stack that holds real content.
set -euo pipefail
: "${JDHP_TESTRIG_USER_PASSWORD:?set JDHP_TESTRIG_USER_PASSWORD}"
: "${KEYCLOAK_ADMIN:?}"; : "${KEYCLOAK_ADMIN_PASSWORD:?}"
domain="${JDHP_PUBLIC_HOST:-testrig.local}"
KC=/opt/keycloak/bin/kcadm.sh
$KC config credentials --server http://localhost:8080/auth --realm master --user "$KEYCLOAK_ADMIN" --password "$KEYCLOAK_ADMIN_PASSWORD"
for role in member verified_researcher curator reviewer rights_officer platform_admin; do
  email="${role//_/-}@${domain}"
  if ! $KC get users -r jdhp -q "email=$email" -q exact=true | grep -q '"id"'; then
    $KC create users -r jdhp -s "username=$email" -s "email=$email" -s enabled=true -s emailVerified=true \
      -s "firstName=Test" -s "lastName=${role//_/ }" -s 'attributes.phoneNumberVerified=["true"]'
    $KC set-password -r jdhp --username "$email" --new-password "$JDHP_TESTRIG_USER_PASSWORD"
    $KC add-roles -r jdhp --uusername "$email" --rolename "$role"
    echo "created $email ($role)"
  else
    echo "exists  $email ($role)"
  fi
done
echo "testing-rig accounts ready; the password is JDHP_TESTRIG_USER_PASSWORD in .env"
