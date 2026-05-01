# Changelog

All notable changes to Blufire are tracked here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project
follows [SemVer](https://semver.org/).

## [Unreleased]

### Security (WS7 deployment hardening)
- `install.sh` now uses `git clone` instead of `cp -a $REPO_ROOT/.` for the
  initial source sync. Prevents the operator's working-tree artifacts (`.env`,
  `data/`, `logs/`, `.venv/`, `__pycache__/`) from leaking into
  `/opt/blufire/source` on first install.
- `blufire-leadgen.service` adds: `UMask=0077`, `RestrictSUIDSGID=true`,
  `RestrictRealtime=true`, `ProtectClock=true`, `ProtectHostname=true`,
  `ProtectKernelLogs=true`, `ProtectProc=invisible`, `ProcSubset=pid`, and
  explicit empty `CapabilityBoundingSet=` / `AmbientCapabilities=`.
  `systemd-analyze security` reports overall exposure **2.8 / 10** (systemd
  default is ~9.6).
- `uninstall.sh` `rm -rf` paths now use `${VAR:?}` defense-in-depth in case
  `$TENANT_ID` were ever unset (already validated, but cheap belt-and-braces).
- Deferred to a future minor: `pip install --require-hashes` with a generated
  lockfile, and `SystemCallFilter=@system-service` (needs runtime testing).

### Added (post-review hardening, in response to independent audit)
- `Settings.tenant.timezone` validated against `zoneinfo.ZoneInfo` at config-load
  time; bad timezone names fail loudly instead of silently defaulting to UTC.
- `Settings` rejects configs that have `prospect_searches` defined but no
  `outreach.webhook.gmail_draft_url` — prevents the daily-leadgen flow from
  failing silently at runtime.
- `LLMOutputError` now includes both head and tail of the offending output
  (≤500 chars each side) so the failure mode near the truncation boundary is
  visible.
- New tests: timezone validation, webhook validation gate, escaped-backslash
  JSON parsing, consent evidence hashing with `datetime` and `Decimal` values.

### Changed (post-review)
- `daily_lead_gen` prompt suppresses empty Apollo enrichment fields instead of
  emitting `Industry: ` / `Revenue: ` etc.
- `cli.main()` uses `load_settings()` directly instead of an inline
  `__import__("yaml")` call.

### Added
- `src/blufire/` package (settings, http, llm, integrations, compliance,
  runtime, agents, cli) — the new foundation for the resaleable autopilot.
- Per-install configuration via `config.yaml` + `.env` (no more `/root/.env`).
- Compliance layer: SQLite-backed suppression list, daily/per-domain send caps,
  HMAC-signed unsubscribe tokens, consent log, CAN-SPAM/CASL footer, RFC 8058
  `List-Unsubscribe` + `List-Unsubscribe-Post` headers.
- Structured JSON logging with secret redaction (Bearer tokens + secret-shaped
  field names).
- Idempotent `install.sh` + `uninstall.sh`, systemd timer + service template
  (replaces `setup_cron.sh`), logrotate config, dedicated `blufire` system user.
- `blufire` CLI: `leadgen run`, `outreach run`, `pipeline run`, `suppress
  add/import/check`, `unsubscribe-server`, `doctor`.
- pytest suite + GitHub Actions CI matrix (lint, typecheck, test, security).
- Phase 2 seed: `runtime/{tool,capability,context,agent_runner}.py`.

### Changed
- All HTTP traffic funnels through `blufire.http.build_session()` with retries,
  back-off, timeouts, and per-service circuit breakers.
- Apollo API key now travels in the `X-Api-Key` header (not the JSON body).
- Pagination is correct everywhere (HubSpot `paging.next.after`, Apollo `page`).
- Robust `extract_json` replaces the four `find('{')` / `rfind('}')` blocks
  scattered across `crm_pipeline.py`, `email_outreach.py`, `daily_lead_gen.py`,
  `send_outreach.py`.
- Anthropic calls use explicit `httpx.Timeout` and tenacity retry on transient
  errors.
- `ruflo/orchestrator.py` plumbs every agent through `RunContext` and uses the
  shared LLM client.
- `ruflo/scripts/{daily_lead_gen,send_outreach}.py` are now thin entrypoints
  delegating to the new agent modules.

### Removed
- `deploy.sh` (replaced by `install.sh`); the hardcoded DigitalOcean IP
  `143.198.139.48` is gone.
- `src/hubspot.py` (dead code, never imported).
- `ruflo/scripts/setup_cron.sh` (replaced by systemd timer).
- `ruflo/scripts/generate_agents.py` (the YAML-boilerplate generator).
- Hardcoded sender identity ("Steve Russell, Bluewave Strategic Resources"),
  hardcoded Make.com webhook URL, hardcoded DFW prospect search criteria, and
  hardcoded model strings — all moved to `config.yaml`.
- The `/root/.env` load path.
- Three duplicate copies of `hubspot_headers()` (now one client class).
- `__import__("time").time()` → plain `import time`.

### Security
- SMTP authentication failures no longer leak the Gmail app password into
  exception tracebacks.
- Systemd unit runs as `blufire`, not root; hardened with
  `ProtectSystem=strict`, `MemoryDenyWriteExecute`, etc.
- Unsubscribe tokens are HMAC-SHA256 signed; tampered or expired tokens reject.
