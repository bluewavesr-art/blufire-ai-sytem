#!/bin/bash
# ============================================================
# BLUFIRE DAILY AUTOMATION RUNNER
# Run this from Claude Code every morning to kick off the
# daily Blufire agent operations
# Usage: bash DAILY_RUN.sh
# ============================================================

echo ""
echo "🔥 Blufire Daily Automation — $(date '+%A, %B %d, %Y')"
echo "======================================================"
echo ""

# Register run with Medic Health Log
curl -s -X POST "https://hook.us2.make.com/7ihq8gm3hfslwbg50j7qbgvs2hrnv69n" \
  -H "Content-Type: application/json" \
  -d "{\"source\": \"DAILY_RUN_SCRIPT\", \"event\": \"daily_automation_started\", \"timestamp\": \"$(date -u +%Y-%m-%dT%H:%M:%S)\", \"status\": \"OK\"}" \
  > /dev/null 2>&1

echo "✅ Medic health log updated"
echo ""
echo "📋 TODAY'S AGENDA:"
echo "   — HubSpot daily sync fires at 8AM (Make.com scenario 4497223)"
echo "   — Sales briefing fires at 8AM (Make.com scenario 4523782)"
echo "   — Watchdog runs every 15 min (Make.com scenario 4523751)"
echo ""
echo "🎯 TO SPAWN THE ROOFING QUEEN OUTBOUND SWARM:"
echo "   npx ruflo swarm init --topology hierarchical --name blufire-outbound"
echo "   npx ruflo hive-mind spawn 'Run daily DFW roofing contractor outbound' --queen-type strategic"
echo ""
echo "🔍 TO RUN PROSPECT INTELLIGENCE:"
echo "   npx ruflo agent spawn --name the-scout 'Enrich top 10 new HubSpot contacts with Clay data and intent scores'"
echo ""
echo "📊 TO GET PIPELINE BRIEFING:"
echo "   npx ruflo agent spawn --name sales-director 'Pull HubSpot pipeline status and give me today\''s action list'"
echo ""
echo "🌐 TO CHECK SYSTEM HEALTH:"
echo "   npx ruflo agent spawn --name the-medic 'Run a full system health check on all active Make.com scenarios'"
echo ""
echo "Ready. Run any of the commands above in Claude Code to activate agents."
