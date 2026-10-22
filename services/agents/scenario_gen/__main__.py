"""Command line, handy for demos and for checking the integration.

  python -m scenario_gen generate --count 3 --difficulty 4 --language fr --seed 7
  python -m scenario_gen sim --count 2                     # only the payload the Customer Sim reads
  python -m scenario_gen check-intents path/to/intents.json
"""
import argparse
import json
import sys

from .catalog import Catalog, compare_with_sim_intents
from .config import Settings
from .schemas import BatchRequest, GenerateRequest
from .service import BadRequest, ScenarioService


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="scenario_gen")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("generate", "sim"):
        p = sub.add_parser(name)
        p.add_argument("--count", type=int, default=1)
        p.add_argument("--difficulty", type=int)
        p.add_argument("--language", choices=["en", "fr", "derja"])
        p.add_argument("--intent")
        p.add_argument("--mode", choices=["standard", "multi_event", "rare_event"], default="standard")
        p.add_argument("--seed", type=int)
        p.add_argument("--enrich", action="store_true", help="use the LLM (needs OPENROUTER_API_KEY)")
    check = sub.add_parser("check-intents")
    check.add_argument("path", help="the Customer Sim's intents.json")
    args = parser.parse_args(argv)

    if args.command == "check-intents":
        report = compare_with_sim_intents(Catalog.load(), args.path)
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 1 if report["ours_unknown_to_sim"] else 0

    service = ScenarioService.from_settings(Settings.from_env())
    try:
        if args.count == 1:
            scenarios = [
                service.generate(
                    GenerateRequest(
                        intent=args.intent,
                        difficulty=args.difficulty,
                        language=args.language,
                        mode=args.mode,
                        seed=args.seed,
                        enrich=args.enrich,
                    )
                )
            ]
        else:
            scenarios = service.batch(
                BatchRequest(
                    count=args.count,
                    difficulty_min=args.difficulty or 1,
                    difficulty_max=args.difficulty or 5,
                    languages=[args.language] if args.language else None,
                    mode=args.mode,
                    seed=args.seed,
                    enrich=args.enrich,
                )
            )
    except BadRequest as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    for scenario in scenarios:
        payload = scenario.sim if args.command == "sim" else scenario
        print(payload.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
