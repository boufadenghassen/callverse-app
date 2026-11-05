"""Shared by every test folder under services/agents: the tests check the rules, so the trained intent model is off unless a test turns it on."""
import os

os.environ.setdefault("ADVISOR_INTENT_MODEL", "0")
