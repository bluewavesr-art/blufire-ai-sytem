"""HubSpot API integration module."""

import os

from dotenv import load_dotenv

load_dotenv()

HUBSPOT_API_KEY = os.getenv("HUBSPOT_API_KEY")

if not HUBSPOT_API_KEY:
    raise EnvironmentError("HUBSPOT_API_KEY is not set. Check your .env file.")


def get_headers():
    """Return authorization headers for HubSpot API requests."""
    return {
        "Authorization": f"Bearer {HUBSPOT_API_KEY}",
        "Content-Type": "application/json",
    }
