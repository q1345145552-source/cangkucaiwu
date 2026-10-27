# Third-round local acceptance

Only synthetic isolated local databases. No production configuration, dotenv, startup lifespan, network service or credentials.

Run from `/private/tmp/permissions-round3-env` with explicit `ROUND3_DATABASE_URL=postgresql+asyncpg://round3@127.0.0.1:65369/round3` and the absolute path to `acceptance.py`. It refuses other hosts/database names and resets only this synthetic schema. `fixtures.py` uses real app/JWT and actual database; synthetic passwords are not login credentials. The test records complete before/after table differences, status, request and key response data. Injected failures replace only the final write/audit step, never authentication.

`run_round2_regression.py` reruns original round-two acceptance against a separate synthetic `round2` database on the same isolated cluster, redirecting evidence into round-three docs. Original round-one/two evidence is preserved. Authorized additions: one real independent verification before ordinary approval, two linked-fund administrator capability checks. No valid amount assertions removed.

`run_related_regression.py` records actual commands and exit codes for current and detached Git-history baseline. It runs from each backend directory and configures local PGlite. Historical failures and new-authority old-flow failures remain visible; no skip/xfail or fake approvals. `collect_regressions.py` stores both complete assertion records and classification; names alone do not prove equivalence.

`browser_identities.py`, `browser_proxy.cjs`, `browser_acceptance.cjs` operate only local synthetic services on 65370/65371/65372. Frontend build comes from an explicit copied source tree with independent local dependencies. Playwright aborts external requests; output is role/menu evidence, not proof of backend security.

`route_inventory.py` inventories real registered routes without startup. `collect_delivery.py` copies evidence, lists uncovered routes, and records source hashes. Never interpret a historical successful unauthorized request as a target acceptance success.
