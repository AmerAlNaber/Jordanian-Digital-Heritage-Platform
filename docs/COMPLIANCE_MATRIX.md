# Compliance matrix

Status: skeleton created in Phase 0. The matrix is completed in Phase 3 (accounts, verification, payments) when personal data processing begins, and reviewed before the pilot goes live.

Scope: Jordan Personal Data Protection Law No. 24 of 2023 (SEC-28), GDPR and UK GDPR for users in the EU and UK (SEC-29), and the retention rules in the compliance section of `SPEC.md` (SEC-27, SEC-30, SEC-31).

## Data categories

| Category | Examples | Lawful basis | Retention | Store | Encryption | Access | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Account | email, phone, display name, locale | contract | life of account, then 30 days | PostgreSQL `user` (RLS) | at rest (volume) | self, support | Phase 3 |
| Verification documents | identity document images | legal obligation / consent | deleted automatically after the decision (ACC-3) | object storage, dedicated bucket | per-object key (SEC-23) | rights officer only | Phase 3 |
| Payments | gateway reference, amount, status; never card data | contract | 7 years (fiscal) | PostgreSQL `payment` | at rest | finance role | Phase 3 |
| Reading activity | reader sessions, tile requests | legitimate interest (rights protection) | 90 days raw, aggregates kept | PostgreSQL, OpenSearch | at rest | staff (aggregated) | Phase 1 |
| Audit trail | every authorization decision and privileged action | legal obligation | 7 years (SEC-27) | PostgreSQL `audit_event`, hash-chained | at rest | auditors | Phase 0 (implemented) |
| Search logs | anonymised queries | legitimate interest | 13 months | OpenSearch | at rest | search team | Phase 2 |

## Rights and procedures

| Right | Mechanism | Status |
| --- | --- | --- |
| Access and portability | self-service export (ACC-5) | Phase 3 |
| Rectification | profile editor (ACC-5) | Phase 3 |
| Erasure | account deletion respecting legal retention of audit records (ACC-5) | Phase 3 |
| Objection to marketing | consent toggle, marketing only (SEC-28) | Phase 3 |
| Breach notification | runbook in `docs/operations/` (SEC-28, SEC-29) | Phase 3 |

## Records of processing

To be completed with the data protection officer contact, the processors (payment gateway, SMS provider, email provider, cloud storage) and the international transfer basis for preservation copies.
