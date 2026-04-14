#!/bin/bash
# Set up daily cron jobs for Blufire Ruflo agents

VENV="/opt/blufire-venv/bin/python3"
REPO="/opt/blufire-ai-system"

# Daily lead gen at 6:00 AM CT (before the 7 AM briefing)
(crontab -l 2>/dev/null | grep -v "daily_lead_gen"; echo "0 6 * * * cd $REPO && $VENV ruflo/scripts/daily_lead_gen.py >> /var/log/blufire-leadgen.log 2>&1") | crontab -

echo "Cron job set: daily_lead_gen.py runs at 6:00 AM daily"
echo ""
echo "Current crontab:"
crontab -l
echo ""
echo "Logs: tail -f /var/log/blufire-leadgen.log"
