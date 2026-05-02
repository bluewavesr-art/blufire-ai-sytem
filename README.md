# Blufire

Resaleable sales/marketing autopilot. One install per agency tenant; bring your
own HubSpot, Apollo, Gmail, and Anthropic keys. Cold outreach is gated by a
compliance layer (suppression list, daily caps, signed unsubscribe links,
CAN-SPAM/CASL footers).

## What's in the box (Phase 1, `v1.0.0`)

| Flow | Entry point | What it does |
|------|-------------|--------------|
| Daily lead-gen | `blufire leadgen run --scope daily` (or systemd timer) | Apollo prospect search → HubSpot dedup → Claude draft → outbound webhook (Make.com or your own). Compliance-gated. |
| Outreach | `blufire outreach run --campaign "..."` | Pulls HubSpot contacts, drafts via Claude, sends via SMTP. `--dry-run` skips sending. |
| CRM pipeline | `blufire pipeline run [--auto-tasks]` | Pulls deals, asks Claude for stale/risky deals + recommended actions, optionally creates HubSpot tasks. |
| Suppression | `blufire suppress add\|import\|check` | Manage the DNC list. |
| Unsubscribe HTTP server | `blufire unsubscribe-server` (optional extra) | Hosts `/u/<token>` so recipients can opt out. |
| Doctor | `blufire doctor` | Validates secrets + config + paths without exposing values. |

The 147-agent YAML hierarchy under `ruflo/agents/` is **scaffolding** in v1 —
loaded at startup but not yet wired to real tools. Phase 2 (`v2.0.0`) builds the
real swarm runtime, MCP tool integration, observability v2, and licensing. See
the audit plan for details.

## Install (single tenant)

```bash
sudo BLUFIRE_TENANT_ID=acme-agency bash install.sh \
    --config-from /tmp/acme.yaml \
    --env-from /tmp/acme.env \
    --non-interactive
```

The installer:
- Creates a system user `blufire` (no shell, no home).
- Lays down `/etc/blufire/<tenant>.yaml` and `<tenant>.env` (mode `0640`,
  `root:blufire`).
- Creates `/var/lib/blufire/<tenant>` for SQLite (suppression, send log,
  consent log) and `/var/log/blufire/<tenant>` for logs.
- Sets up a hardened systemd timer (`blufire-leadgen@<tenant>.timer`).
- Installs logrotate.

Re-running is idempotent. Use `uninstall.sh` to remove a tenant; data and
config are preserved unless you confirm deletion.

## Configure

Start from `config.example.yaml` and `.env.example`. The config file holds
sender identity, prospect search criteria, send caps, send window, and
compliance settings. The `.env` holds secrets only. The two files compose via
`${VAR}` interpolation.

CAN-SPAM requires a working physical mailing address — `sender.physical_address`
in `config.yaml` is enforced (≥ 10 characters).

## Operate

Tail logs:
```bash
sudo journalctl -u "blufire-leadgen@acme-agency.timer" -f
```

Run an ad-hoc dry-run outreach:
```bash
sudo -u blufire BLUFIRE_CONFIG=/etc/blufire/acme-agency.yaml \
    /opt/blufire/venv/bin/blufire outreach run \
    --campaign "Follow-up to webinar attendees" --dry-run
```

Add a recipient to the DNC:
```bash
sudo -u blufire BLUFIRE_CONFIG=/etc/blufire/acme-agency.yaml \
    /opt/blufire/venv/bin/blufire suppress add alice@example.com --reason "user request"
```

## Develop

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest -ra --cov=src/blufire --cov=ruflo --cov-fail-under=70
ruff check . && ruff format --check .
mypy src/blufire
bandit -r src
```

## Roadmap

See the bundled audit plan and `CHANGELOG.md`. Phase 2 (`v2.0.0`) lands real
tool/capability registry, Celery-backed orchestration, OpenTelemetry tracing,
JWT licensing, and prunes the 147-agent scaffolding to ~25 functional agents.
