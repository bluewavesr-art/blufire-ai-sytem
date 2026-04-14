# Blufire Marketing — Ruflo Agent System
### 37 Agents | 9 Departments | Built March 25, 2026

---

## INSTALLATION (2 minutes)

1. **Copy this entire folder into your project root:**
   ```
   cp -r blufire-agents/.claude/agents /your-project/.claude/agents
   ```
   Or if you want them globally available in Claude Code:
   ```
   cp -r blufire-agents /path/to/your/claude/home/.claude/agents
   ```

2. **Verify Ruflo is installed:**
   ```
   npx ruflo --version
   ```
   If not installed:
   ```
   npm install -g ruflo
   npx ruflo init --wizard
   ```

3. **Check agents are loaded:**
   ```
   npx ruflo agent list
   ```

4. **Initialize the Hive Mind with the Dispatcher as Queen:**
   ```
   npx ruflo hive-mind init
   npx ruflo swarm init --topology hierarchical --max-agents 12 --name "blufire-ops"
   ```

---

## AGENT DIRECTORY

### 00 — Infrastructure (Load First)
| Agent | File | Role |
|-------|------|------|
| The Dispatcher | `00-medic/the-dispatcher.md` | Master router — all work flows through here |
| The Medic | `00-medic/the-medic.md` | System health monitor for Make.com |

### 01 — Outbound Sales
| Agent | File | Role |
|-------|------|------|
| Roofing Queen | `01-outbound/roofing-queen.md` | Outbound sales supervisor |
| The Scout | `01-outbound/the-scout.md` | Prospect research & Clay enrichment |
| The Connector | `01-outbound/the-connector.md` | LinkedIn connection requests |
| The Messenger | `01-outbound/the-messenger.md` | LinkedIn DM sequences |
| The Mailer | `01-outbound/the-mailer.md` | Cold email sequences |
| The Caller | `01-outbound/the-caller.md` | RVM & SMS outreach |

### 02 — Social Media
| Agent | File | Role |
|-------|------|------|
| Social Media Supervisor | `02-social/social-media-supervisor.md` | Manages all 6 channel agents |
| LinkedIn Agent | `02-social/linkedin-agent.md` | Blufire LinkedIn |
| GBP Agent | `02-social/gbp-agent.md` | Google Business Profiles (both companies) |
| Instagram Agent | `02-social/instagram-agent.md` | Global Roofing Instagram |
| Facebook Agent | `02-social/facebook-agent.md` | Blufire Facebook |
| TikTok Agent | `02-social/tiktok-agent.md` | Global Roofing TikTok |
| YouTube Agent | `02-social/youtube-agent.md` | Blufire YouTube |

### 03 — Customer Service
| Agent | File | Role |
|-------|------|------|
| CS Supervisor | `03-customer-service/cs-supervisor.md` | Support ticket routing |
| CS Investigator | `03-customer-service/cs-investigator.md` | Data pulls & case files |
| CS Billing Agent | `03-customer-service/cs-billing-agent.md` | Payment & invoice support |
| CS Product Agent | `03-customer-service/cs-product-agent.md` | Service delivery support |

### 04 — Web Department
| Agent | File | Role |
|-------|------|------|
| Web Department Director | `04-web/web-department-director.md` | Website project management |
| Webflow Agent | `04-web/webflow-agent.md` | Webflow builds |
| Lovable Agent | `04-web/lovable-agent.md` | React/Lovable builds (Global Roofing) |
| Code Agent | `04-web/code-agent.md` | Custom code and APIs |
| SEO Agent | `04-web/seo-agent.md` | Keyword research & on-page SEO |
| QA Agent | `04-web/qa-agent.md` | Pre-launch quality assurance |

### 05 — AI Department
| Agent | File | Role |
|-------|------|------|
| AI Solutions Director | `05-ai/ai-solutions-director.md` | AI project scoping & pricing |
| AI Build Agent | `05-ai/ai-build-agent.md` | Make.com & Vapi.ai builds |
| AI Delivery Agent | `05-ai/ai-delivery-agent.md` | Client onboarding & documentation |

### 06 — Sales Department
| Agent | File | Role |
|-------|------|------|
| Sales Director | `06-sales/sales-director.md` | Daily briefing & pipeline oversight |
| Proposal Agent | `06-sales/sales-proposal-agent.md` | Custom proposal creation |
| Pipeline Agent | `06-sales/sales-pipeline-agent.md` | Deal velocity monitoring |

### 07 — Revenue Intelligence
| Agent | File | Role |
|-------|------|------|
| Revenue Intelligence Agent | `07-revenue/revenue-intelligence-agent.md` | Weekly P&L & revenue reports |

### 08 — Video Production
| Agent | File | Role |
|-------|------|------|
| Video Director Agent | `08-video/video-director-agent.md` | Production operations |
| Production Coordinator | `08-video/video-production-coordinator.md` | Pre-production & scheduling |
| Post-Production Agent | `08-video/video-post-production-agent.md` | Editing & delivery |

### 09 — Creative Production
| Agent | File | Role |
|-------|------|------|
| Creative Director Agent | `09-creative/creative-director-agent.md` | Brand asset oversight |
| Asset Producer Agent | `09-creative/asset-producer-agent.md` | Canva & Firefly asset creation |

---

## DAILY AUTOMATION (Make.com — Already Live)

These run automatically without Ruflo:
- **Every 15 min**: Watchdog (ID: 4523751) monitors all scenarios
- **Every morning**: Daily Sales Briefing (ID: 4523782)
- **Every Monday**: Social Monday Draft (ID: 4523816)
- **Every Monday**: Revenue Report (ID: 4523786)
- **On trigger**: Outreach Orchestrator (ID: 4437555) — Clay → HubSpot → Heyreach → Outlook

Ruflo agents enhance this system by adding intelligence — they write the content, make routing decisions, and handle exceptions.

---

## MASTER WEBHOOK URLS (Keep These Safe)

| Purpose | URL |
|---------|-----|
| Medic Registrar (register every new endpoint here) | https://hook.us2.make.com/eln4ulmmrktpxf8hxgnhey1y4ugx3h9y |
| Health Log (every agent logs here) | https://hook.us2.make.com/7ihq8gm3hfslwbg50j7qbgvs2hrnv69n |
| Fixer (trigger auto-repair) | https://hook.us2.make.com/h45g5ey1oic38mehnr62be01clwo5ry7 |
| CS Support Email | https://hook.us2.make.com/k8xufsrfzt324gsnkb7sswuqonedtqiw |
| Sales Closed Won Router | https://hook.us2.make.com/anpchh1ed2kuayewiu9ehtx7y29yf56m |
| Web New Project | https://hook.us2.make.com/g6avbft7g7cd0s1hcr2ga1upcg3snw3t |
| AI New Implementation | https://hook.us2.make.com/lqkzida6lyy4zcqscplk3276gpk1wi4b |
| Post-Proposal Follow-up | https://hook.us2.make.com/v93y2xp4c3tmbo9c25psd4sjg9lpgsus |

---

*Blufire Marketing | Steve Russell, CEO | 817.366.4170 | Fort Worth, TX*
*Built by Claude | March 25, 2026*
