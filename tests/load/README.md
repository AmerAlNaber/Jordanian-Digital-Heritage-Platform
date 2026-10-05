# Load tests

k6 scripts for the reader and search. Targets come from the performance section of `SPEC.md`: 500 concurrent readers at 50 tiles per second each, search at 20 queries per second. Written in Phase 1 (reader) and Phase 2 (search); the scripts run against staging, never production.

```sh
k6 run reader.js --vus 500 --duration 10m
k6 run search.js --vus 50 --duration 10m
```
