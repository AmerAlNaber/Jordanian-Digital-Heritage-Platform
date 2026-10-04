# Local stack

The whole platform runs from one `docker compose up`. This is also the pilot deployment shape (`infra/compose/compose.pilot.yaml`).

## First start

```sh
make setup                      # Python (uv) and Node (pnpm) dependencies
infra/compose/make-env.sh       # writes .env from .env.example with random secrets
make up                         # builds images, starts every service, ingests the seed book
```

The platform answers on <http://localhost:8080>: the web application at `/ar` and `/en`, the API under `/api`, Keycloak under `/auth`. Mailpit shows outgoing mail on <http://localhost:8025>.

## What `make up` does

1. `docker compose up -d --build` starts Caddy, the web application, the API and its internal admin app, the Celery worker and beat, Keycloak (realm imported from `infra/keycloak`), Cerbos (policies mounted read-only), PostgreSQL with pgvector, OpenSearch with the Arabic analyzer templates, Redis, MinIO with locked buckets, Cantaloupe behind the authorizing delegate, and Mailpit.
2. `docker compose run --rm seed` renders the fictional 40-page book, uploads it to the intake bucket, registers the batch and the catalog record as the seed curator, and enqueues the ingest pipeline. The worker validates every master, writes the preservation copy, METS and checksums, generates derivatives, runs the mock OCR, indexes the pages and computes embeddings.

## Checking health

```sh
docker compose ps                                   # every service healthy or running
docker compose exec -T postgres psql -U postgres -d jdhp -c "select code, state from intake_batch"
curl -s localhost:8080/api/works | jq .total        # 1 once the seed book is published
```

## Resetting

```sh
make down                       # stops the stack and removes the volumes
```

Object-locked buckets keep their objects for the retention period even on `make down`; the MinIO volume is removed with the stack, which is the intended local behaviour.
