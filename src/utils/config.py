"""Centralized configuration loader for Blufire AI System."""

import os
from dotenv import load_dotenv

load_dotenv("/root/.env")
load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))

HUBSPOT_API_KEY = os.getenv("HUBSPOT_API_KEY")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
GMAIL_USER = os.getenv("GMAIL_USER", "bluewavesr@gmail.com")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD")
APOLLO_API_KEY = os.getenv("APOLLO_API_KEY")
