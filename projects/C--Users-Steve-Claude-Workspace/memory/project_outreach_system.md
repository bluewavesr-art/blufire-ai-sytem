---
name: Blufire Outreach System Architecture
description: Current state of the 3-vertical outreach system — Make scenarios, Ruflo agents, gaps, and what needs Steve's manual action
type: project
---

3-vertical outreach system targeting 10 verified emails/day per vertical.

**Why:** Steve needs a repeatable, resellable outreach system that runs from VPS, managed through Ruflo, self-heals via MEDIC.

**How to apply:** When touching outreach, Make scenarios, Ruflo agents, or the MEDIC watchdog — refer to this map.

## Make Scenarios (us2.make.com, Team 69529, Folder 222683)

| Scenario | ID | Schedule | Status |
|---|---|---|---|
| Outreach Orchestrator — Roofers | 4650985 | Daily 8:00 AM CT | ACTIVE ✅ |
| Outreach Orchestrator — Fencing & Outdoor | 4742561 | Daily 8:10 AM CT | ACTIVE ✅ |
| Outreach Orchestrator — Video Production | 4742574 | Daily 8:20 AM CT | ACTIVE ✅ |
| MEDIC_01_Watchdog | 4724234 | Daily 9:00 AM CT | INACTIVE — needs Gmail reconnect in UI |

## How Each Outreach Scenario Works
1. HubSpot pull: contacts where lifecyclestage=lead, hs_lead_status=NEW, HAS email (limit 20)
2. Iterator
3. Filter: valid email format (regex) AND company/industry matches vertical keywords
4. Claude (claude-sonnet-4-6): writes personalized <100 word email, vertical-specific prompt
5. Gmail send (account 703022)
6. HubSpot update: lead status → IN_PROGRESS

## Vertical Keyword Filters (Make-level, on Claude module)
- **Roofers**: company contains roof/construction/exterior/storm OR industry contains roofing
- **Fencing**: company contains fence/outdoor/patio/deck/landscap OR industry contains fence
- **Video Production**: company contains video/film/media/production/photo OR industry contains media

## Ruflo Agents (blufire-outbound domain)
- the-scout-roofing — coordinator, task: task-1776177197816 (pull 10 verified roofers/day from Apollo)
- fencing-queen-scout — coordinator, task: task-1776177199210 (pull 10 verified fence leads/day)
- blufire-medic — monitor agent, spawned 2026-04-14

## Critical Gaps (not yet built)
1. **MEDIC_01_Watchdog needs manual Gmail reconnect** — open scenario 4724234 in Make, click Gmail module, reselect connection, activate
2. **No fence/video leads in HubSpot** — Make scenarios exist but will send 0 emails until Apollo lists are built for these verticals. Steve needs to create Apollo lists for fence contractors and video production companies in DFW.
3. **No real email verification gate** — current filter is regex format check only (catches obviously bad formats). Full verification requires Clay email verification column → HubSpot `email_verified` custom property → Make filter on that property. Not yet configured.
4. **Video production vertical has no prospect source** — need Apollo list or alternative source for DFW video production companies.

## Connection IDs (Make)
- HubSpot: __IMTCONN__ 6960348
- Gmail: account 703022

## MEDIC Watchdog Design Note
Current watchdog sends daily health check emails for 7 active scenarios. This is polling-based (daily check), not event-driven. The proper pattern is error handler routes on each monitored scenario that POST to a webhook → alert email. This is the next version to build.
