#!/bin/bash
# Set up daily cron jobs for Blufire Ruflo agents

VENV="/opt/blufire-venv/bin/python3"
REPO="/opt/blufire-ai-system"

# Daily lead gen at 6:00 AM CT (before the 7 AM briefing)
(crontab -l 2>/dev/null | grep -v "daily_lead_gen"; echo "0 6 * * * cd $REPO && $VENV ruflo/scripts/daily_lead_gen.py >> /var/log/blufire-leadgen.log 2>&1") | crontab -

# DFW contractor prospector (11–50 emp + MarTech) at 6:30 AM CT, weekdays only
(crontab -l 2>/dev/null | grep -v "apollo_dfw_contractors"; echo "30 6 * * 1-5 cd $REPO && $VENV ruflo/scripts/apollo_dfw_contractors.py >> /var/log/blufire-dfw-contractors.log 2>&1") | crontab -

echo "Cron jobs set:"
echo "  daily_lead_gen.py            — 6:00 AM daily"
echo "  apollo_dfw_contractors.py    — 6:30 AM weekdays (Mon–Fri)"
echo ""
echo "Current crontab:"
crontab -l
echo ""
echo "Logs:"
echo "  tail -f /var/log/blufire-leadgen.log"
echo "  tail -f /var/log/blufire-dfw-contractors.log"
