#!/usr/bin/env python3
"""Blufire DFW Contractor Prospector — 11–50 employee specialty trades w/ MarTech.

Targets owner/CEO contacts at construction & specialty-trade contractors in
the Dallas-Fort Worth metro that have any marketing technology in their stack.
Apollo search → MarTech filter → HubSpot dedup → qualifying score → Claude
draft → Gmail draft via Make.com webhook.

Runs weekdays 6:30 AM via cron (see setup_cron.sh). No emails send without
Steve's approval — everything lands in Drafts.
"""

import os
import time
from datetime import datetime
from dotenv import load_dotenv

from _lead_helpers import (
    apollo_search_people,
    hubspot_contact_exists,
    hubspot_create_contact,
    hubspot_ensure_property,
    claude_draft_email,
    make_gmail_draft,
    person_to_hubspot_properties,
)

load_dotenv("/root/.env")

HUBSPOT_KEY = os.getenv("HUBSPOT_API_KEY")
ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY")
APOLLO_KEY = os.getenv("APOLLO_API_KEY")
DRAFT_WEBHOOK_URL = "https://hook.us2.make.com/5dmfd2o0fgtzr193adsylp6dzy1yri87"

QUAL_SCORE_PROPERTY = "blufire_qual_score"

DFW_LOCATIONS = [
    "Dallas, Texas, United States",
    "Fort Worth, Texas, United States",
    "Plano, Texas, United States",
    "Arlington, Texas, United States",
    "Irving, Texas, United States",
    "Frisco, Texas, United States",
    "McKinney, Texas, United States",
    "Garland, Texas, United States",
    "Richardson, Texas, United States",
    "Denton, Texas, United States",
]

PERSON_TITLES = ["Owner", "CEO", "President", "Founder", "Co-Founder", "Managing Partner"]

# Apollo employee-range buckets covering 11–50.
EMPLOYEE_RANGES = ["11,20", "21,50"]

# Keyword tag → human-readable trade label. We page through each trade
# separately so a single dominant trade can't crowd out the others.
TRADE_SEARCHES = [
    {"label": "Roofing", "tags": ["roofing", "roofer"]},
    {"label": "HVAC", "tags": ["hvac", "heating", "air conditioning"]},
    {"label": "Plumbing", "tags": ["plumbing", "plumber"]},
    {"label": "Electrical", "tags": ["electrical contractor", "electrician"]},
    {"label": "Concrete & Masonry", "tags": ["concrete", "masonry"]},
    {"label": "Fencing", "tags": ["fencing", "fence"]},
    {"label": "Landscaping", "tags": ["landscaping", "landscape"]},
    {"label": "General Contractor", "tags": ["general contractor", "construction"]},
]

# Apollo technology UIDs covering the major MarTech categories. Apollo accepts
# technology slugs (e.g. "google_analytics") in `currently_using_any_of_technology_uids`.
# On Basic plans this filter is silently ignored; we treat the response's
# `current_technologies` field as the source of truth and filter client-side too.
MARTECH_UIDS = [
    "google_analytics", "google_tag_manager", "google_ads",
    "facebook_pixel", "facebook_advertiser",
    "hubspot", "mailchimp", "constant_contact", "klaviyo", "activecampaign",
    "marketo", "pardot", "salesforce_marketing_cloud",
    "hotjar", "crazy_egg", "optimizely",
    "wordpress", "wix", "squarespace",
    "shopify", "bigcommerce",
    "intercom", "drift", "zendesk_chat",
    "semrush", "ahrefs", "moz",
]

# Substrings that indicate a marketing technology is present. Used as the
# fallback filter when Apollo's tech-stack filter isn't honored on the plan.
MARTECH_KEYWORDS = [
    "google analytics", "google tag manager", "google ads", "google adwords",
    "facebook pixel", "facebook advertis", "meta pixel",
    "hubspot", "mailchimp", "constant contact", "klaviyo", "activecampaign",
    "marketo", "pardot", "salesforce marketing",
    "hotjar", "crazy egg", "optimizely",
    "wordpress", "wix", "squarespace",
    "shopify", "bigcommerce",
    "intercom", "drift", "zendesk chat",
    "semrush", "ahrefs", "moz",
    "tiktok pixel", "linkedin insight", "twitter pixel",
    "active campaign", "convertkit", "drip", "ontraport",
]

PER_PAGE = 25
MAX_PAGES_PER_TRADE = 3

AGENT_SYSTEM_PROMPT = """You are the Blufire Email Outreach Agent. You write cold outreach emails for Steve Russell at Blufire Marketing.

STRICT RULES:
- NEVER use "Quick question" as a subject line. Ever.
- NEVER sound like a template or mass email.
- NEVER use "I came across", "I wanted to reach out", "hope this finds you well", "just reaching out", or "I'd love to".
- Write like Steve personally researched this person and their business.
- Reference specific details from the enrichment data: company size, revenue range, industry specifics, their role, the marketing tools they're already using.
- Be direct about what Blufire does and why it matters to THEIR specific situation.
- Keep it under 100 words. Short paragraphs. No fluff.
- The ask: a 20-minute call this week.
- Sound like a peer who runs a business, not a salesperson.
- Each email must be genuinely unique — vary the structure, opening, and angle.
- Sign off as Steve Russell, Blufire Marketing, steve@blufiremarketing.com

QUALIFYING SCORE GUIDANCE (provided in prospect data):
- 75+ : high-fit, take a direct ROI angle ("here's what we'd do in your first 30 days")
- 50–74 : warm, lead with a specific observation about their stack/size
- < 50 : softer, curiosity-driven angle

ABOUT BLUFIRE:
Blufire Marketing helps DFW contractors and specialty-trade businesses scale through:
- Google Business Profile optimization and local SEO that actually ranks
- Paid search & social tuned for trade businesses (we've moved CPLs from $80 to $22 for HVAC)
- AI-powered lead nurture and follow-up automation that closes the gap between lead and booked job
- CRM and reporting that ties marketing spend back to revenue
Steve has real results: clients getting 3-5x more leads within 90 days.

Return ONLY a JSON object with "subject" and "body" keys. The body should use <br> for line breaks. No markdown, no backticks, no explanation."""


def detect_martech(org):
    """Return list of detected MarTech tools from an Apollo organization payload."""
    found = []

    techs = org.get("current_technologies") or org.get("technologies") or []
    for t in techs:
        if isinstance(t, dict):
            name = (t.get("name") or t.get("uid") or "").lower()
        else:
            name = str(t).lower()
        if not name:
            continue
        for kw in MARTECH_KEYWORDS:
            if kw in name:
                found.append(name)
                break

    cats = org.get("technology_categories") or []
    for c in cats:
        cl = str(c).lower()
        if "marketing" in cl or "analytics" in cl or "advertising" in cl or "email" in cl:
            found.append(f"category:{cl}")

    seen = set()
    deduped = []
    for f in found:
        if f not in seen:
            seen.add(f)
            deduped.append(f)
    return deduped


def qualifying_score(org, martech_hits):
    """0–100 score per the rubric agreed with Steve."""
    score = 0

    employees = org.get("estimated_num_employees") or 0
    try:
        employees = int(employees)
    except (TypeError, ValueError):
        employees = 0
    if 11 <= employees <= 20:
        score += 20
    elif 21 <= employees <= 35:
        score += 35
    elif 36 <= employees <= 50:
        score += 30

    if martech_hits:
        score += 30

    revenue = org.get("annual_revenue") or 0
    try:
        revenue = float(revenue)
    except (TypeError, ValueError):
        revenue = 0
    if 1_000_000 <= revenue < 10_000_000:
        score += 15
    elif revenue >= 10_000_000:
        score += 10

    if org.get("website_url"):
        score += 5
    if org.get("phone") or org.get("primary_phone"):
        score += 5

    return min(score, 100)


def build_prospect_info(person, org, score, martech_hits):
    return (
        f"Name: {person.get('first_name', '')} {person.get('last_name', '')}\n"
        f"Email: {person.get('email', '')}\n"
        f"Title: {person.get('title', '')}\n"
        f"Headline: {person.get('headline', '')}\n"
        f"City: {person.get('city', '')}, {person.get('state', '')}\n"
        f"LinkedIn: {person.get('linkedin_url', '')}\n"
        f"\n--- COMPANY ---\n"
        f"Company: {org.get('name', '')}\n"
        f"Industry: {org.get('industry', '')}\n"
        f"Employees: {org.get('estimated_num_employees', '')}\n"
        f"Revenue: {org.get('annual_revenue_printed', '')}\n"
        f"Description: {org.get('short_description', '')}\n"
        f"Website: {org.get('website_url', '')}\n"
        f"Founded: {org.get('founded_year', '')}\n"
        f"HQ: {org.get('city', '')}, {org.get('state', '')}\n"
        f"\n--- BLUFIRE QUALIFYING DATA ---\n"
        f"Qualifying Score: {score}/100\n"
        f"Marketing Tech Detected: {', '.join(martech_hits) if martech_hits else 'none confirmed'}\n"
    )


def search_trade(trade):
    """Page through Apollo for a single trade, return list of (person, org)."""
    results = []
    for page in range(1, MAX_PAGES_PER_TRADE + 1):
        payload = {
            "person_titles": PERSON_TITLES,
            "q_organization_keyword_tags": trade["tags"],
            "person_locations": DFW_LOCATIONS,
            "organization_num_employees_ranges": EMPLOYEE_RANGES,
            "currently_using_any_of_technology_uids": MARTECH_UIDS,
            "page": page,
            "per_page": PER_PAGE,
        }
        people, _orgs = apollo_search_people(APOLLO_KEY, payload)
        if not people:
            break
        results.extend(people)
        if len(people) < PER_PAGE:
            break
        time.sleep(1)
    return results


def main():
    today = datetime.now().strftime("%A, %B %d, %Y")
    print("=" * 64)
    print(f"  BLUFIRE DFW CONTRACTOR PROSPECTOR — {today}")
    print("  Apollo (11–50 emp + MarTech) → HubSpot → Score → Claude → Gmail")
    print("=" * 64)

    if not (HUBSPOT_KEY and ANTHROPIC_KEY and APOLLO_KEY):
        print("  ERROR: Missing one of HUBSPOT_API_KEY / ANTHROPIC_API_KEY / APOLLO_API_KEY")
        return

    hubspot_ensure_property(
        HUBSPOT_KEY,
        QUAL_SCORE_PROPERTY,
        "Blufire Qualifying Score",
    )

    candidates = []
    for trade in TRADE_SEARCHES:
        print(f"\n  Searching: {trade['label']}...")
        people = search_trade(trade)
        print(f"    Apollo returned {len(people)} candidates")
        for person in people:
            candidates.append((trade["label"], person))
        time.sleep(1)

    print(f"\n{'=' * 64}")
    print(f"  Filtering {len(candidates)} candidates against MarTech + dedup")
    print(f"{'=' * 64}\n")

    new_prospects = []
    seen_emails = set()

    for trade_label, person in candidates:
        email = person.get("email")
        if not email or email in seen_emails:
            continue
        seen_emails.add(email)

        org = person.get("organization") or {}
        employees = org.get("estimated_num_employees") or 0
        try:
            employees = int(employees)
        except (TypeError, ValueError):
            employees = 0
        if not (11 <= employees <= 50):
            continue

        martech_hits = detect_martech(org)
        if not martech_hits:
            continue

        if hubspot_contact_exists(HUBSPOT_KEY, email):
            continue

        score = qualifying_score(org, martech_hits)
        new_prospects.append({
            "trade": trade_label,
            "person": person,
            "org": org,
            "score": score,
            "martech": martech_hits,
        })

    new_prospects.sort(key=lambda p: p["score"], reverse=True)

    print(f"  {len(new_prospects)} qualified new prospects after filtering\n")
    if not new_prospects:
        print("  No new qualified prospects today.")
        return

    drafted = 0
    failed = 0

    for i, prospect in enumerate(new_prospects, 1):
        person = prospect["person"]
        org = prospect["org"]
        score = prospect["score"]
        martech = prospect["martech"]
        email = person["email"]
        name = f"{person.get('first_name', '')} {person.get('last_name', '')}".strip()

        print(f"  [{i}/{len(new_prospects)}] {name} — {org.get('name', '')} "
              f"({prospect['trade']}, {org.get('estimated_num_employees', '?')} emp, score {score})")

        properties = person_to_hubspot_properties(person, extra={QUAL_SCORE_PROPERTY: score})
        print("    HubSpot...", end=" ", flush=True)
        hs_contact = hubspot_create_contact(HUBSPOT_KEY, properties)
        if hs_contact:
            print(f"OK — ID {hs_contact['id']}")
        else:
            print("skipped/exists")

        print("    Claude...", end=" ", flush=True)
        try:
            email_data = claude_draft_email(
                ANTHROPIC_KEY,
                AGENT_SYSTEM_PROMPT,
                build_prospect_info(person, org, score, martech),
            )
            subject = email_data["subject"]
            body = email_data["body"]
            print(f"OK — \"{subject}\"")
        except Exception as e:
            print(f"ERROR: {e}")
            failed += 1
            continue

        print("    Gmail draft...", end=" ", flush=True)
        if make_gmail_draft(DRAFT_WEBHOOK_URL, email, subject, body):
            print("DRAFT CREATED")
            drafted += 1
        else:
            print("FAILED")
            failed += 1

        time.sleep(2)
        print()

    print(f"{'=' * 64}")
    print(f"  DONE: {drafted} drafts created, {failed} failed")
    print(f"  Review in Gmail Drafts. Top score today: "
          f"{new_prospects[0]['score'] if new_prospects else 0}")
    print(f"{'=' * 64}")


if __name__ == "__main__":
    main()
