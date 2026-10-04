# Operations

Runbooks and drills for running the platform. Written as each capability ships; every runbook names the alert that triggers it, the first five minutes, and how to verify recovery.

| Runbook | Trigger | Phase |
| --- | --- | --- |
| [Local stack](local-stack.md) | development and pilot on Docker Compose | 0 |
| Fixity failure | `fixity_failed` incident, work frozen (SEC-26) | 1 |
| Policy engine unavailable | API answering `503 policy_engine_unavailable` | 1 |
| Session revocation lag | revocation not visible within 60 seconds (SEC-5) | 1 |
| Restore drill | quarterly, from the previous night's backup (SEC-24) | 4 |
| Break-glass access | use of the emergency role (SEC-9) | 4 |
| Data breach | suspected disclosure of personal data (SEC-28, SEC-29) | 3 |
