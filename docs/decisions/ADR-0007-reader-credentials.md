# ADR-0007: Reader credentials and class grants

Status: accepted (2026-10-05)

## Context

`docs/ARCHITECTURE.md` (sections 6.3, 6.4 and 8.1) describes two reader credentials and leaves their formats open: a grant token "signed compact token, format open (PASETO or JWT with EdDSA)" and a tile token "HMAC-SHA256 over session id, work, expiry, key id". It also requires a per-session forensic key stored encrypted on the session row (SEC-11). `SPEC.md` gives Open works to everyone and Registered works to signed-in members "instantly", while the print quota and the device limit live on a grant (ACS-2, RDR-4). Phase 1 needed these settled before the reader and the tile gateway could be built.

## Decisions

1. **Grant token: a JWT signed with Ed25519 (`EdDSA`) by PyJWT, which the API already depends on.** The signing key pair is derived with HKDF-SHA256 from the environment's token signing key (`info = "jdhp grant token v1"`), and the token header carries a `kid` computed from the public key, so rotating the environment secret rotates the key and old tokens are refused by `kid` before any signature check. Claims bind the token to the reader session (`sid`, the session's public name), the principal (`sub`), the work (`wrk`), the grant (`gid`) and the device fingerprint hash (`dev`); lifetime is `JDHP_GRANT_TOKEN_TTL_SECONDS`, at most ten minutes, refreshed by the heartbeat. PASETO would have added a dependency for no gain here: both ends are platform processes and the JWT is never accepted from a third party.
2. **Tile token: `t1.<kid>.<session>.<expiry>.<signature>`**, where the signature is HMAC-SHA256 under a key derived with HKDF from the same environment secret (`info = "jdhp tile token v1"`), compared in constant time, lifetime `JDHP_TILE_TOKEN_TTL_SECONDS` (at most five minutes). The session name in the token is what the gateway looks up; the work is checked against the session row, not trusted from the URL.
3. **Forensic session key: HKDF-SHA256 of the forensic master key and the session row id**, stored on the row sealed with AES-GCM under a key derived from the field encryption key. The key itself never sits in clear in the database; the detector (ADR-0006) re-derives it from the master key and the session id.
4. **Device binding is a SHA-256 hash of the browser-supplied fingerprint.** The fingerprint never reaches storage or a token in clear. The device limit counts distinct hashes among the grant's active sessions.
5. **Class grants.** A signed-in member who opens an Open or Registered work receives a grant with `source = access_class`, `JDHP_REGISTERED_GRANT_DAYS` of validity, `JDHP_DEFAULT_DEVICE_LIMIT` devices and `JDHP_PRINT_QUOTA_DEFAULT_PAGES` pages of print quota, created on first use and reused while active. Anonymous visitors read Open works without a grant and without print. Paid and Restricted works need a grant from a request, a payment or a licence (Phase 2). Revoking a grant ends its reader sessions and deletes their cached decisions at once (SEC-5).
6. **Public names, never row ids.** Grants and reader sessions carry opaque NOID-style names (`g8…`, `s8…`) like works and collections, and those are the only identifiers the API returns or accepts (INT-7).
7. **Reader rows are read and written under the system context.** The browser calls reader endpoints without a Keycloak token, so the request's own row-level security context is anonymous; the verified grant token, bound to one session, is the authorization, and the Cerbos `reader_session` policy allows `heartbeat` and `end` only when the loader has verified it. Staff list and revoke by role.

## Consequences

- One environment secret per purpose family keeps `.env.example` short; rotation is a secret change plus a redeploy, and in-flight readers re-open their sessions.
- The tile gateway (task 18) verifies tile tokens with the same `TileTokenSigner` and reads decisions from the same Redis keys, so it needs no database write path.
- `GrantSource` gains `access_class` (migration 0003); existing grants are unaffected.
- The forensic detector and the watermark library are decided in ADR-0006.
