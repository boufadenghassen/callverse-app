"""Optional LLM enrichment through OpenRouter.

The generator never needs it: templates are the source of truth. The LLM only rewrites two texts
(the customer's situation card and the trainer brief) to add variety. Any problem (no key, network
error, bad answer) returns None and the caller keeps the template text.

The model output is treated as data: we only keep two plain strings, cut to a safe length.
"""
import json
import logging
import re

import httpx

from .config import Settings
from .schemas import TrainingScenario

log = logging.getLogger("scenario_gen.llm")

LANGUAGE_NAMES = {
    "en": "English",
    "fr": "French",
    "derja": "Tunisian Arabic (derja), written in Arabic script, natural spoken style",
}
MAX_CARD = 600
MAX_BRIEF = 900

SYSTEM_PROMPT = (
    "You write training scenario cards for telecom call-centre advisors. "
    "Answer with one JSON object and nothing else, with exactly two string fields: "
    '"customer_card" (2 to 3 sentences, written to the customer in the second person, describing the situation '
    "they live, in the requested language) and "
    '"trainer_brief" (2 to 3 sentences in English telling the trainee what to practise). '
    "Use only invented details, never real names or numbers. Keep the facts of the scenario unchanged."
)


class LLMClient:
    def __init__(self, settings: Settings, transport: httpx.BaseTransport | None = None):
        self.settings = settings
        self._transport = transport

    @property
    def available(self) -> bool:
        return bool(self.settings.openrouter_api_key)

    def enrich(self, scenario: TrainingScenario) -> TrainingScenario | None:
        """Return a copy with rewritten texts, or None if enrichment was not possible."""
        if not self.available:
            return None
        payload = {
            "model": self.settings.openrouter_model,
            "temperature": 0.8,
            "max_tokens": 500,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": self._user_prompt(scenario)},
            ],
        }
        headers = {
            "Authorization": f"Bearer {self.settings.openrouter_api_key}",
            "Content-Type": "application/json",
            "X-Title": "orqestra scenario generator",
        }
        try:
            with httpx.Client(timeout=self.settings.llm_timeout, transport=self._transport) as client:
                response = client.post(
                    f"{self.settings.openrouter_base_url.rstrip('/')}/chat/completions", json=payload, headers=headers
                )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            parsed = parse_json_object(content)
            card = clean_text(parsed.get("customer_card"), MAX_CARD)
            brief = clean_text(parsed.get("trainer_brief"), MAX_BRIEF)
            if not card or not brief:
                raise ValueError("missing customer_card or trainer_brief")
        except Exception as error:  # noqa: BLE001 - any failure falls back to templates
            log.warning("LLM enrichment failed (%s): %s", type(error).__name__, error)
            return None
        return scenario.model_copy(update={"customer_card": card, "trainer_brief": brief, "enrichment": "llm"})

    @staticmethod
    def _user_prompt(scenario: TrainingScenario) -> str:
        spec = scenario.spec
        return json.dumps(
            {
                "language": LANGUAGE_NAMES[spec.language],
                "situation": scenario.customer_card,
                "category": scenario.category,
                "difficulty_1_to_5": spec.difficulty,
                "customer_segment": spec.segment,
                "customer_opening_emotion": scenario.opening_emotion,
                "complications": scenario.complications,
                "skills_trained": scenario.skills,
            },
            ensure_ascii=False,
        )


def parse_json_object(text: str) -> dict:
    """Accept a bare JSON object or one wrapped in a code fence or in extra words."""
    text = text.strip()
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            raise ValueError("no JSON object in the answer") from None
        value = json.loads(match.group(0))
    if not isinstance(value, dict):
        raise ValueError("answer is not a JSON object")
    return value


def clean_text(value, limit: int) -> str:
    if not isinstance(value, str):
        return ""
    text = "".join(ch for ch in value if ch == "\n" or ch >= " ").strip()
    return text[:limit]
