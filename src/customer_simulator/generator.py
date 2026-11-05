"""Générateur de profils : varie les 6 personas pour éviter les clones."""
import json
import os
import random
from pathlib import Path
from .schemas import PersonaTemplate, Profile, EmotionState, Scenario

DATA = Path(__file__).resolve().parents[2] / "data"

PAST_EVENTS = [
    "Réclamation sur une facture il y a 3 mois (résolue)",
    "Coupure de service de 2 jours l'an dernier",
    "A changé de forfait il y a 8 mois",
    "A déjà appelé 2 fois pour le même problème ce mois-ci",
    "Retard de paiement ponctuel",
    "Client fidèle, aucun incident récent",
    "A souscrit une option TV l'année dernière",
]


def load_personas() -> dict[str, PersonaTemplate]:
    raw = json.loads((DATA / "personas.json").read_text(encoding="utf-8"))
    return {p["id"]: PersonaTemplate(**p) for p in raw}


def load_intents() -> dict[str, str]:
    return json.loads((DATA / "intents.json").read_text(encoding="utf-8"))


def pick_persona(sc: Scenario, personas: dict[str, PersonaTemplate], rng: random.Random) -> PersonaTemplate:
    if sc.persona_id:
        return personas[sc.persona_id]
    pool = [p for p in personas.values()
            if (sc.language is None or p.language == sc.language)
            and (sc.gender is None or p.gender == sc.gender)]
    if sc.language is None:  # tirage libre : seulement les langues activées (derja désactivé pour l'instant)
        allowed = set(os.getenv("ENABLED_LANGUAGES", "fr,en").split(","))
        pool = [p for p in pool if p.language in allowed] or pool
    return rng.choice(pool)


def generate_profile(sc: Scenario) -> tuple[Profile, EmotionState]:
    rng = random.Random(sc.seed)
    personas, intents = load_personas(), load_intents()
    tpl = pick_persona(sc, personas, rng)

    main = sc.problem_type or rng.choice(tpl.typical_intents)
    if main not in intents:
        raise ValueError(f"problem_type inconnu: {main}. Choix: {list(intents)}")
    chosen = [main]
    if sc.difficulty >= 3:
        extra = [i for i in tpl.typical_intents if i != main]
        if extra:
            chosen.append(rng.choice(extra))
    hidden = "cancel_contract" if (sc.difficulty >= 4 and main != "cancel_contract") else None

    billed = rng.randint(45, 190)
    details = {
        "numéro de ligne": f"{rng.choice([2, 5, 9])}{rng.randint(0, 9)} {rng.randint(100, 999)} {rng.randint(100, 999)}",
        "référence de facture": f"F{rng.randint(100000, 999999)}",
        "montant facturé": f"{billed} DT",
        "montant habituel": f"{billed - rng.randint(15, 40)} DT",
        "adresse": rng.choice(["Ariana", "La Marsa", "Sfax", "Sousse", "Bizerte", "Tunis centre", "Nabeul"]),
    }
    profile = Profile(
        persona_id=tpl.id, name=rng.choice(tpl.names), age=rng.randint(*tpl.age_range),
        gender=tpl.gender, language=tpl.language, segment=rng.choice(tpl.segments),
        seniority_years=rng.randint(0, 12), history=rng.sample(PAST_EVENTS, k=rng.randint(1, 3)),
        intents=chosen, hidden_intent=hidden,
        speaking_style=tpl.speaking_style, examples=tpl.examples, details=details,
    )

    base, d = tpl.base_emotion, (sc.difficulty - 3) * 0.06
    emo = EmotionState(
        patience=base["patience"] - d + rng.uniform(-0.08, 0.08),
        frustration=base["frustration"] + d + rng.uniform(-0.08, 0.08),
        trust=base["trust"] - d + rng.uniform(-0.08, 0.08),
        urgency=base["urgency"] + rng.uniform(-0.08, 0.08),
    ).clamp()
    return profile, emo
