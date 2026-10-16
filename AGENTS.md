# AGENTS.md

`hsbc-tradetrack-mcp` is a FastMCP server exposing HSBC TradeTrack lists from HSBC's public no-login endpoints. Before touching anything that calls HSBC or shapes tool output, read [`docs/hsbc-api.md`](docs/hsbc-api.md) for endpoints, field semantics and refresh times.

## Scope

The server is a stateless data source: it fetches live lists from HSBC and historical snapshots from the `data` branch, normalizes them, and returns them. Scheduling, strategy, signals and order execution belong to the agents that call it. The only state is an in-memory cache per request that expires at the response's `nextRefreshTime`.

History lives on the orphan `data` branch as `<US|HK>/<YYYY-MM-DD>.jsonl`, appended by `.github/workflows/collect.yml` running `scripts/collect.py`. The server reads it through `raw.githubusercontent.com`, which needs no token and has no GitHub API rate limit. Keep collected data raw; interpretation belongs in server code.

## Tool contract

The tool schema (names, parameters, output fields, their meaning and units) is the public API:

- Removing or renaming a tool, parameter or output field, or changing a field's meaning or units, is **breaking**: PR title gets `!`.
- Adding an optional parameter or output field is `feat`.
- Adapting to an upstream HSBC change with the schema unchanged is `fix`.

A snapshot test of `tools/list` turns red on any schema change; update the snapshot in the same PR and label the PR accordingly.

Every tool:

- declares `readOnlyHint`, `openWorldHint` and `idempotentHint` as `True`;
- returns Pydantic models, so FastMCP emits `outputSchema` and structured content;
- reports upstream failures as `ToolError` with a message an agent can act on (for example "HSBC returned 500, likely maintenance; retry after nextRefreshTime");
- sets a timeout on every HTTP call and sends `User-Agent: hsbc-tradetrack-mcp/<version> (+https://github.com/BukeLy/hsbc-tradetrack-mcp)`.

Logs go to stderr; stdout carries the MCP stdio protocol.

## Tests

Unit tests run offline: inject HTTP responses with `httpx.MockTransport` and use synthetic fixtures. Live HSBC behaviour is covered by the collector, whose scheduled runs fail when the upstream API changes.

## Pull requests and releases

- Squash merge only. The PR title becomes the commit on `main`, so it must be a Conventional Commit: `type(scope)!: subject`, English, imperative, lowercase subject, at most 72 characters. Types: `feat` `fix` `perf` `refactor` `docs` `test` `build` `ci` `chore` `revert`. Optional scopes: `tools` `client` `data` `deps` `deps-dev` `ci`.
- Fill in `.github/pull_request_template.md`; "How verified" shows a real call or the Horizon preview URL.
- release-please owns `CHANGELOG.md` and every version string (`pyproject.toml`, `uv.lock`, `server.json`). Merging its Release PR tags `vX.Y.Z`, publishes to PyPI with trusted publishing, then to the MCP Registry.
- Every push to `main` redeploys the public Horizon (FastMCP Cloud) instance, so `main` stays deployable.

## Workflows

Third-party actions are pinned by commit SHA with the version in a trailing comment. Workflows start from `permissions: {}` and grant per job; checkouts use `persist-credentials: false`. zizmor runs in CI.

## Keep the repo small

Add community files (CONTRIBUTING, CODE_OF_CONDUCT, issue templates, CODEOWNERS), pre-commit hooks, a type checker, CLA/DCO or supply-chain scorecards only when a real need appears. The CI is the gate.
