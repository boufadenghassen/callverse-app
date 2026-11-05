"""The complaint agent (Amine): triage, escalation risk, early warning, deadlines, root causes and what worked."""
from pathlib import Path

_POLICY_PATH = Path(__file__).resolve().parents[1] / "knowledge" / "complaints.json"
