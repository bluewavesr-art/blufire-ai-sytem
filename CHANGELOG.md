# Changelog

All notable changes to Blufire are tracked here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project
follows [SemVer](https://semver.org/).

## [Unreleased]

### Added (Phase 2 step 3: daily_lead_gen orchestrator + email.create_draft contract)
- New tool contract `email.create_draft` (separate from `email.send_smtp`):
  creates a draft for human review rather than sending immediately. First
  implementation `email_make_webhook.py` posts to a Make.com webhook that
  builds a Gmail draft.
- New `EmailConfig.draft_provider` settings field (Literal: `make_webhook,
  gmail_api, outlook_api, ghl`, default `make_webhook`). Independent from
  `email.provider` so a tenant can use Mailgun for sends and a webhook for
  drafts simultaneously.
- New LLM tool `llm.draft_outreach_email_from_prospect` — different from
  `llm.draft_outreach_email` because the input is a rich Apollo enrichment
  record rather than a sparse HubSpot contact dict.
- `runtime/orchestrators/daily_lead_gen.py` — capability-driven runner that
  searches multiple `ProspectSearch` configs in sequence with intra-run
  dedup, applies all four cheap filters (no-email / dedup / suppression /
  send-cap) before any Claude call, then drafts + posts to webhook for
  human review. List-Unsubscribe header intentionally omitted from drafts
  (it belongs on the actual outbound message the human eventually sends).
- `DAILY_LEADGEN_CAPABILITY` + `DAILY_LEADGEN_BLUEPRINT` in `bootstrap.py`
  with the new `EMAIL_DRAFT_PROVIDERS` dispatch table.
- CLI: `blufire leadgen run --scope daily --via-capability` now exercises
  the new path.

### Added (Phase 2 step 2: lead_generation + crm_pipeline orchestrators)
- 6 new CRM tool contracts in `runtime/tools/crm.py`: `crm.search_contacts`,
  `crm.create_contact`, `crm.list_deals`, `crm.update_deal`, `crm.create_deal`,
  `crm.create_task`. Each is provider-agnostic; HubSpot impls in
  `runtime/tools/crm_hubspot.py`.
- `runtime/tools/prospect.py` — provider-agnostic prospect-search contract,
  with `runtime/tools/prospect_apollo.py` as the first implementation.
- `runtime/tools/llm.py` — `llm.score_prospect` and `llm.analyze_pipeline`
  tools wrapping the existing Phase 1 helpers with strict pydantic outputs.
- `runtime/orchestrators/lead_generation.py` — capability-driven runner that
  searches a prospect provider, scores fit with the LLM, dedups against the
  CRM, and creates new contacts. Returns the same shape the Phase 1 module
  returns plus an explicit counters dict.
- `runtime/orchestrators/crm_pipeline.py` — capability-driven runner that
  lists CRM deals, asks the LLM for an analysis, and (optionally) creates
  one CRM task per recommended action. Task-create failures are logged
  per-deal but do not fail the run.
- `settings.prospect.provider` (Literal: `apollo, zoominfo, lusha`, default
  `apollo`). `bootstrap.py` adds `PROSPECT_PROVIDERS` dispatch table mirroring
  the CRM/email pattern.
- New CLI flags: `blufire leadgen run --scope ad-hoc --via-capability` and
  `blufire pipeline run --via-capability`.

### Added (Phase 2 step 1: capability-driven runtime)
- `runtime/tools/` — nine concrete `Tool` implementations with pydantic
  input/output schemas (compliance × 5, crm × 2, email × 1, llm × 1).
- `runtime/bootstrap.py` — idempotent `bootstrap(settings)` that registers
  every built-in tool plus the `email_outreach.send` capability.
- `runtime/orchestrators/email_outreach.py` — capability-driven runner that
  mirrors the Phase 1 logic but routes every external call through the
  registry. Compliance gating stays in deterministic Python.
- `cli` — `blufire outreach run --via-capability` exercises the new path.

### Added (Phase 2 step 1.5: pluggable CRM / email backends)
- `settings.crm.provider` (default `"hubspot"`) and `settings.email.provider`
  (default `"gmail"`). Validated against a Literal of known providers
  (`hubspot, jobber, acculynx, servicetitan, ghl` and
  `gmail, mailgun, sendgrid, ses, ghl`). Unrecognized providers are rejected
  at config-parse time.
- Tool *contracts* (`crm.list_contacts`, `crm.log_email`, `email.send_smtp`)
  live in `runtime/tools/{crm,email}.py` as pydantic schemas. Concrete
  *implementations* live in sibling modules (`crm_hubspot.py`, `email_gmail.py`).
  Each provider module exposes a `register(tools)` function.
- `bootstrap.py` dispatches on `settings.{crm,email}.provider` via a flat
  table (`CRM_PROVIDERS`, `EMAIL_PROVIDERS`). Adding a new provider =
  one new module + one line in the dispatch table.
- Adding GHL (or any other future provider) to settings now produces a
  clear `ProviderNotImplemented` error pointing at the missing module
  rather than a runtime AttributeError.

### Fixed
- `tests/unit/test_send_caps.py` — daily-cap and per-domain-cap tests no
  longer fail outside business hours / on weekends. The default 08:00–17:00
  Mon–Fri send window was leaking into cap tests; now those tests use an
  always-open window and the dedicated send-window test stays.

## [1.0.0] - 2026-05-01

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
