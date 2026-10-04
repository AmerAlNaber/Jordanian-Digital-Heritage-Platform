# Search relevance set

The 100-query regression set (SRCH-7). Each line of `queries.jsonl` is one query with the pages that must appear in the first ten results, written by curators against the seed book and, later, the catalog. The set runs in CI from Phase 2 and blocks a release on regression against the previous release.

```json
{"id": "q001", "query": "سُمَيْرة", "language": "ar", "expected": ["w8…/p1", "w8…/p3"]}
```

Queries are curated by hand; nothing in this set is generated.
