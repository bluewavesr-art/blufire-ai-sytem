# Deploying Blufire for Backyard Builders (Fort Worth, TX)

Storm-damage fencing campaign targeting B2B property managers, HOAs, and
facilities directors across the DFW metro. **Source = Google Places**
(local commercial businesses), not Apollo. **Email enrichment = website
scraping** (`mailto:` links + obvious `info@` patterns). Prospects with
no findable email get routed to a Call List worksheet so the team can
phone them.

~10 prospects/day, M–F, 06:00 CST. Drafts land in a Google Sheet for
the team to review and send manually from Backyard's own Gmail. **No
SMTP send, no Make.com.**

---

## 1. Prerequisites

- A Google account that owns the Google Sheet ("Backyard Builders Outreach"
  or whatever you've named it). The sheet must contain three worksheets:
  - **`Leads`** — header row 1 with these columns in this order:
    `email | first_name | last_name | company | title | phone | address | city | state | status | notes | created_at`
  - **`Drafts`** — header row 1: `created_at | to | subject | body | list_unsubscribe | status`
  - **`Call List`** — header row 1: `created_at | company | phone | address | city | state | website | talking_points | status`

  Operators may add extra columns to the right of the listed ones, but
  must not rename or reorder them.

- A Google Cloud project where you can:
  - Enable the **Places API** (and **Drive API** + **Sheets API** if not
    already enabled for the existing service account)
  - Create an API key (for Places)
  - Create a service account (for Sheets)

- An Anthropic API key.
- SSH access to the existing VPS droplet.

## 2. Set up Google Cloud

### 2a. Enable APIs

In the same project (https://console.cloud.google.com/apis/library):
- **Places API** — for prospect discovery
- **Google Sheets API** — for writing leads / drafts / call list
- **Google Drive API** — gspread needs read-only Drive scope to look up
  sheets by URL

### 2b. Create the Places API key

1. https://console.cloud.google.com/apis/credentials → **Create
   credentials → API key**
2. Copy the key, then immediately click **Edit** on the new key:
   - Set **Application restrictions → IP addresses** → add the VPS's
     outbound IP. (You can leave this open for testing and lock it down
     after the first successful run.)
   - Set **API restrictions → Restrict key** → check only **Places API**
3. Save the key value — this is `GPLACES_API_KEY`.

### 2c. Create the Sheets service account

1. https://console.cloud.google.com/iam-admin/serviceaccounts → **Create
   service account**. Name it `blufire-backyard`.
2. After creating → **Keys** tab → **Add Key → Create new key → JSON**.
   A `.json` file downloads. Keep it private.
3. Copy the service-account email (looks like
   `blufire-backyard@<project>.iam.gserviceaccount.com`).
4. Open the Google Sheet → **Share** → paste the SA email → set to
   **Editor** → uncheck "Notify people" → Share.

## 3. Customize the tenant config

Copy the templates and fill in placeholders:

```bash
cp packaging/tenants/backyard-builders.yaml.example /tmp/backyard.yaml
cp packaging/tenants/backyard-builders.env.example /tmp/backyard.env
cp packaging/tenants/backyard-builders.system-prompt.txt /tmp/backyard.system-prompt.txt
```

Edit `/tmp/backyard.yaml`:
- `sender.name`, `sender.email`, `sender.physical_address` (CAN-SPAM)
- `gsheets.spreadsheet_url` — the full Google Sheet URL
- Confirm `prospect_searches` titles + locations match the ICP (the
  template targets DFW property managers, HOAs, and apartment complexes)

Edit `/tmp/backyard.env`:
- `ANTHROPIC_API_KEY` — sk-ant-...
- `GPLACES_API_KEY` — from step 2b
- `GSHEETS_CREDENTIALS_PATH=/etc/blufire/backyard-builders.gsheets.json`

Review `/tmp/backyard.system-prompt.txt` — this is the prompt the LLM
uses to write each email. Edit the storm-damage angle, tone, or CTA if
the campaign brief shifts.

## 4. Install on the VPS

```bash
# Get the latest Blufire source.
cd /opt/blufire/source && sudo git pull origin master

# Install the gsheets + places extras into the venv.
sudo /opt/blufire/venv/bin/pip install \
    'gspread==6.1.4' 'google-auth==2.36.0' \
    'googlemaps==4.10.0' 'beautifulsoup4==4.12.3'

# Run the installer with the tenant ID set.
sudo BLUFIRE_TENANT_ID=backyard-builders bash install.sh \
    --config-from /tmp/backyard.yaml \
    --env-from /tmp/backyard.env \
    --non-interactive

# Drop the GCP service-account JSON in place (mode 0640 root:blufire).
# scp the JSON file from your laptop first.
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
    /opt/blufire/source/packaging/systemd/blufire-leadgen-backyard.timer.example \
    /etc/systemd/system/blufire-leadgen@backyard-builders.timer.d/override.conf
sudo systemctl daemon-reload
sudo systemctl restart blufire-leadgen@backyard-builders.timer
```

## 5. Verify

```bash
# Health check — every required secret + path resolved?
sudo -u blufire \
    BLUFIRE_CONFIG=/etc/blufire/backyard-builders.yaml \
    /opt/blufire/venv/bin/blufire doctor

# Smoke test with cap=1 first to control Places + Anthropic charges.
# Edit the yaml and set outreach.daily_send_cap: 1 temporarily.
sudo nano /etc/blufire/backyard-builders.yaml

sudo -u blufire \
    BLUFIRE_CONFIG=/etc/blufire/backyard-builders.yaml \
    /opt/blufire/venv/bin/blufire leadgen run \
        --scope daily --via-capability

# Verify by looking at the sheet:
#   - 1 row should appear in EITHER the Leads + Drafts worksheets
#     (if email was found) OR the Call List worksheet (if not)
#   - tail /var/log/blufire/backyard-builders/blufire.log shows
#     daily_leadgen_done with reasonable counters

# Bump cap back to 10 for production.
sudo nano /etc/blufire/backyard-builders.yaml   # outreach.daily_send_cap: 10

# Confirm timer is enabled.
sudo systemctl status blufire-leadgen@backyard-builders.timer
sudo systemctl list-timers blufire-leadgen@backyard-builders.timer
```

## 6. Daily operations

**Email path (Drafts worksheet):**
- Each morning ~8am CST, open the Drafts worksheet.
- For each row with `status=draft`:
  - Read the subject + body. **Edit if anything feels off** — common
    edits: company name spellings, removing anything that sounds AI-
    generated.
  - Copy `subject` and `body` into a new Gmail compose window.
  - Send from Backyard's account.
  - Update the row's `status` cell from `draft` → `sent` (or `skipped`
    if you pass on it).
- Replies land in Backyard's normal Gmail inbox.

**Phone path (Call List worksheet):**
- Same morning, scan the Call List for new `to-call` rows.
- Each row has company name, phone, address, and a one-line talking-
  points hint.
- Make the calls. Update `status` to `called` / `scheduled` / `dead` /
  `voicemail` as you go.

**Suppression handling:**
- If a recipient asks to be removed from email outreach:
  ```bash
  sudo -u blufire \
      BLUFIRE_CONFIG=/etc/blufire/backyard-builders.yaml \
      /opt/blufire/venv/bin/blufire suppress add \
          --email someone@example.com --reason replied-stop
  ```
- The Leads worksheet is the source-of-truth for dedup. Once a row is
  there, the next day's run won't re-add or re-draft for that email.

**Pause the daily cron without uninstalling:**
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

## What can go wrong (in rough order of likelihood)

1. **Service-account JSON path mismatch.** `GSHEETS_CREDENTIALS_PATH`
   in `.env` doesn't match where you actually dropped the file. `doctor`
   catches this.
2. **Sheet not shared with the SA email.** Symptom: `GSheetsError:
   spreadsheet not found / not shared`. Re-share the sheet.
3. **Worksheet column header typo.** `gspread` errors when columns don't
   match. Re-paste the header rows from this README exactly.
4. **Places API quota / billing not enabled.** Symptom: 403 from the
   Places API. Enable billing on the GCP project.
5. **Places returns 0 results.** ICP filters too narrow — loosen
   `person_titles` or expand `locations`. Try the search manually in
   Google Maps first; if you can't find businesses there, the API won't
   either.
6. **Email enrichment finds garbage.** The website scraper has a
   blocklist (`gmail.com`, `wordpress.com`, social media domains, etc.)
   but no scraper is perfect. Check the Drafts worksheet for obviously-
   wrong recipients before sending.
7. **CST timer fires at the wrong time.** systemd unit caches.
   `systemctl restart` after editing the override file.
