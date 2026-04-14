---
name: Blufire Autopilot Platform
description: Blufire Marketing's MCP-native lead fulfillment platform — HeyReach → Clay MCP → Claude scoring → Gmail approval → HeyReach REST API. White-label, first client is Zitronen Consulting. Renamed from zitronen-autopilot to blufire-autopilot.
type: project
---

## Operator
Blufire Marketing — owns the platform and reseller relationship.

## First Client
Zitronen Consulting — bookkeeping firm in Round Rock, TX. Will be cloned as a separate deployment once the core platform is tested.

## Architecture (MCP-native, NO Make.com, NO Slack)
```
HeyReach webhook → Clay MCP enrichment → Claude ICP scoring → Gmail approval → HeyReach REST API → AccountGroove (pending)
```

**Why:** Platform is white-label. All client-specific values (ICP, branding, credentials) live in .env and client.config.js. Agent prefix `bf-` = Blufire core. Future client deployments will get their own prefix.

## Integration Methods
| Service | Method | Status |
|---------|--------|--------|
| Clay | MCP (live, tested) | Ready |
| HeyReach | REST API (key in .env) | Ready |
| Gmail | MCP (approval emails) | Working — swap to M365 later |
| AccountGroove | HTTP API | Blocked — meeting 2026-03-27 (Friday) |
| Make.com | NOT USED | Eliminated |
| Slack | NOT USED | Steve doesn't use Slack |

## Ruflo Workflow
- **Workflow ID:** `workflow-1774362015989-1pzhke` (blufire-fulfillment)
- **Status:** ready

## Agent Assignments (bf- prefix)

| Agent ID | Type | Domain | Task |
|----------|------|--------|------|
| `bf-clay-enrichment` | research | data-enrichment | Clay MCP enrichment |
| `bf-claude-scoring` | analysis | lead-qualification | ICP scoring (1-10) |
| `bf-email-approval` | messaging | communications | Gmail approval to Steve |
| `bf-heyreach-control` | integration | outreach | HeyReach REST API sequence control |

## Codebase
- **Project folder:** `~/blufire-autopilot/` (renamed from zitronen-autopilot)
- **Agent modules:** `agents/enrichment/` (index.js, clay-mcp.js, icp-scorer.js, email-approval.js, heyreach-control.js)
- **Architecture:** Node.js ESM, white-label, webhook-driven
- **Email approval now white-labeled:** `buildApprovalEmail()` takes `clientName` param

## Key Details
- **Approval:** Gmail MCP → steve@blufiremarketing.com (M365 later)
- **HeyReach API key:** in `blufire-autopilot/.env` as `HEYREACH_API_KEY`
- **On approve:** Continue HeyReach sequence, (future: sync to AccountGroove)
- **On reject:** Tag "Not Now" in HeyReach, pause 30 days

## Blockers
- AccountGroove API access — meeting Friday 2026-03-27
- M365 MCP not connected yet (using Gmail for now)
- HEYREACH_CAMPAIGN_ID env var needs to be set

## Live Test (2026-03-24)
- Clay MCP enrichment tested on Savage Brands (savagebrands.com) — all data points returned
- ICP scoring tested — scored 4/10 (correct: agency, not owner-operated, no intent signals)
- Approval email drafted via Gmail MCP to steve@blufiremarketing.com
