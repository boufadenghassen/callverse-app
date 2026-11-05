"""Train the supervised complaint model.

Usage from services/agents:
  python -m complaints_agent.train_model labeled.csv complaints_model.joblib
"""
import json
import sys

from .ml_model import train


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("Usage: python -m complaints_agent.train_model labeled.csv model.joblib")
    metrics = train(sys.argv[1], sys.argv[2])
    print(json.dumps({
        "accuracy": metrics["accuracy"],
        "macroF1": metrics["macroF1"],
        "classes": metrics["classes"],
        "testSamples": metrics["testSamples"],
    }, indent=2))


if __name__ == "__main__":
    main()
