# Deploying Blufire for Backyard Builders (Fort Worth, TX)

Storm-damage fencing campaign targeting B2B property managers, HOAs, and
facilities directors across the DFW metro. ~10 prospects/day, M-F, 06:00
CST. Drafts land in a Google Sheet for the team to review and send manually
from Backyard's own Gmail. **No SMTP send, no Make.com.**

---

## 1. Prerequisites

- A Google account that owns the Google Sheet ("Backyard Builders Outreach"
  or whatever you've named it). The sheet must contain two worksheets:
  - **`Leads`** — header row 1 with these columns in this order:
    `email | first_name | last_name | company | title | phone | address | city | state | status | notes | created_at`
    Operators may add extra columns to the right of `created_at`, but must
    not rename or reorder the listed ones.
  - **`Drafts`** — header row 1 with these columns in this order:
    `created_at | to | subject | body | list_unsubscribe | status`
- A Google Cloud project where you can create a service account.
- An Apollo.io account with API access.
- An Anthropic API key.
- SSH access to the existing VPS droplet (or wherever you want Blufire to
  run).

## 2. Create the Google Cloud service account

1. https://console.cloud.google.com/iam-admin/serviceaccounts → **Create
   service account**. Name it something like `blufire-backyard`.
2. Grant it the role **Service Account User** (no broader permissions
   needed — sheet access is granted per-sheet in the next step).
3. After creating, click into the account → **Keys** tab → **Add Key →
   Create new key → JSON**. A `.json` file downloads. Keep it private —
   anyone with that file can read/write any sheet shared with the account.
4. Copy the service-account email (looks like
   `blufire-backyard@your-project.iam.gserviceaccount.com`).
5. Open the Google Sheet → **Share** → paste the service-account email →
   set permission to **Editor** → uncheck "Notify people" → Share.
6. Enable the **Google Sheets API** for the project at
   https://console.cloud.google.com/apis/library/sheets.googleapis.com
   (and the **Google Drive API** at
   https://console.cloud.google.com/apis/library/drive.googleapis.com —
   gspread needs read-only Drive scope to look up sheets by URL).

## 3. Customize the tenant config

Copy the templates and fill in placeholders:

```bash
cp packaging/tenants/backyard-builders.yaml.example /tmp/backyard.yaml
cp packaging/tenants/backyard-builders.env.example /tmp/backyard.env
cp packaging/tenants/backyard-builders.system-prompt.txt /tmp/backyard.system-prompt.txt
```

Edit `/tmp/backyard.yaml`:
- `sender.name` — e.g. `"Mike at Backyard Builders"`
- `sender.email` — Backyard's actual address (this just goes in the footer
  / Reply-To context for the LLM; we never send via SMTP)
- `sender.physical_address` — full mailing address (CAN-SPAM requirement)
- `gsheets.spreadsheet_url` — the full Google Sheet URL
- Confirm `prospect_searches` titles/locations/industries match the ICP
  (the template targets DFW property managers + HOAs)
- Adjust `outreach.daily_send_cap` if you want more/fewer than 10/day

Edit `/tmp/backyard.env`:
- `ANTHROPIC_API_KEY` — sk-ant-...
- `APOLLO_API_KEY` — Backyard's Apollo key
- `GSHEETS_CREDENTIALS_PATH` — path on the VPS where you'll drop the
  service-account JSON (e.g. `/etc/blufire/backyard-builders.gsheets.json`)

(Re-)review `/tmp/backyard.system-prompt.txt` — this is the prompt the LLM
uses to write each email. Edit the storm-damage angle, tone, or CTA if the
campaign brief shifts.

## 4. Install on the VPS

SSH into the droplet, then:

```bash
# Get the Blufire source onto the box (if not already there).
git clone <repo-url> /tmp/blufire-src
cd /tmp/blufire-src

# Run the installer with the tenant ID set.
sudo BLUFIRE_TENANT_ID=backyard-builders bash install.sh \
    --config-from /tmp/backyard.yaml \
    --env-from /tmp/backyard.env \
    --non-interactive

# Drop the service-account JSON in place (mode 0640 root:blufire).
sudo install -m 0640 -o root -g blufire \
    /tmp/backyard.gsheets.json \
    /etc/blufire/backyard-builders.gsheets.json

# Drop the system prompt in place.
sudo install -m 0640 -o root -g blufire \
    /tmp/backyard.system-prompt.txt \
    /etc/blufire/backyard-builders.system-prompt.txt

# Override the systemd timer so it runs at 06:00 CST instead of 06:00 UTC.
sudo mkdir -p /etc/systemd/system/blufire-leadgen@backyard-builders.timer.d
sudo install -m 0644 \
    packaging/systemd/blufire-leadgen-backyard.timer.example \
    /etc/systemd/system/blufire-leadgen@backyard-builders.timer.d/override.conf
sudo systemctl daemon-reload
sudo systemctl restart blufire-leadgen@backyard-builders.timer
```

Then install the gsheets extra into the venv:

```bash
sudo /opt/blufire/venv/bin/pip install 'blufire[gsheets] @ /opt/blufire/source'
```

## 5. Verify

```bash
# Health check — every required secret + path resolved?
sudo -u blufire \
    BLUFIRE_CONFIG=/etc/blufire/backyard-builders.yaml \
    /opt/blufire/venv/bin/blufire doctor

# Dry run — drafts get appended to Drafts worksheet, no Apollo charge?
# Actually wait — dry-run still hits Apollo. Use a small limit instead:
sudo -u blufire \
    BLUFIRE_CONFIG=/etc/blufire/backyard-builders.yaml \
    /opt/blufire/venv/bin/blufire leadgen run \
        --scope daily --via-capability

# Then check:
#   - Leads worksheet got new rows
#   - Drafts worksheet got drafts
#   - /var/log/blufire/backyard-builders/blufire.log shows
#     daily_leadgen_done with reasonable counters

# Check the timer is enabled and scheduled correctly.
sudo systemctl status blufire-leadgen@backyard-builders.timer
sudo systemctl list-timers blufire-leadgen@backyard-builders.timer
```

## 6. Daily operations

- Backyard reviews the **Drafts** worksheet each morning. For each row
  they want to send: copy `subject` and `body` into a new Gmail
  composition, send from their account, then update the row's `status`
  cell from `draft` → `sent` (or `skipped` if they pass on it).
- The **Leads** worksheet is the source-of-truth for dedup. Once a row
  exists there, the next day's daily-leadgen run won't re-add or
  re-draft for that email.
- If a recipient asks to be removed, add their email to the suppression
  list:
  ```bash
  sudo -u blufire \
      BLUFIRE_CONFIG=/etc/blufire/backyard-builders.yaml \
      /opt/blufire/venv/bin/blufire suppress add \
          --email someone@example.com --reason replied-stop
  ```
- To pause the daily cron without uninstalling:
  ```bash
  sudo systemctl stop blufire-leadgen@backyard-builders.timer
  sudo systemctl disable blufire-leadgen@backyard-builders.timer
  ```

## 7. Tearing down

```bash
sudo BLUFIRE_TENANT_ID=backyard-builders bash uninstall.sh --keep-data
# --keep-data preserves /var/lib/blufire/backyard-builders, which holds
# the suppression list and consent log. CAN-SPAM requires retaining
# unsubscribe records — don't delete this without a documented reason.
```
