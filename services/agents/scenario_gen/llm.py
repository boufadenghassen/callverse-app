"""Optional LLM enrichment, through OpenRouter when a key is set, otherwise through the local model (local_llm.py).

The generator never needs it: templates are the source of truth. The LLM only rewrites two texts
(the customer's situation card and the trainer brief) to add variety. Any problem (no key, network
error, bad answer) returns None and the caller keeps the template text.

The model output is treated as data: we only keep two plain strings, cut to a safe length.
"""
import json
import logging
import re

import httpx

try:
    import local_llm
except ImportError:
    local_llm = None

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
MAX_SUMMARY = 500
MAX_ACTION = 240

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
        return bool(self.settings.openrouter_api_key) or bool(local_llm and local_llm.enabled())

    def enrich(self, scenario: TrainingScenario) -> TrainingScenario | None:
        """Return a copy with rewritten texts, or None if enrichment was not possible."""
        if not self.available:
            return None
        if not self.settings.openrouter_api_key:
            return self._local(scenario)
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

    def coach_plan(self, plan, weaknesses):
        """Add model-written coaching guidance and scenario copy to a safe generated plan.

        The generator remains authoritative for IDs, skills, difficulty and simulator payloads.
        The model can only supply bounded presentation text.
        """
        if not self.available:
            return None
        payload = {
            "weaknesses": [item.model_dump() for item in weaknesses],
            "focus": [item.model_dump() for item in plan.focus],
            "scenarios": [
                {
                    "id": scenario.id,
                    "title": scenario.title,
                    "skills": scenario.skills,
                    "difficulty": scenario.spec.difficulty,
                    "customer_card": scenario.customer_card,
                    "trainer_brief": scenario.trainer_brief,
                    "success_criteria": scenario.success_criteria,
                }
                for scenario in plan.scenarios
            ],
        }
        system = (
            "You are a call-centre training coach. Answer with one JSON object and nothing else. "
            'Use exactly these fields: "summary" (one string), "actions" (an array of 2 to 5 short strings), '
            '"scenarios" (an array with one object per input scenario, each containing its exact "id", '
            '"customer_card" (2 to 3 sentences), "trainer_brief" (2 to 3 sentences), and '
            '"success_criteria" (an array of 2 to 4 short strings)). '
            "Keep the scenario facts, skills and difficulty unchanged. Use invented details only. "
            "Do not add or remove scenario IDs."
        )
        if self.settings.openrouter_api_key:
            try:
                with httpx.Client(timeout=self.settings.llm_timeout, transport=self._transport) as client:
                    response = client.post(
                        f"{self.settings.openrouter_base_url.rstrip('/')}/chat/completions",
                        json={
                            "model": self.settings.openrouter_model,
                            "temperature": 0.6,
                            "max_tokens": 2200,
                            "messages": [
                                {"role": "system", "content": system},
                                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
                            ],
                        },
                        headers={"Authorization": "******", "Content-Type": "application/json", "X-Title": "orqestra training coach"},
                    )
                response.raise_for_status()
                return self._validate_coach_plan(parse_json_object(response.json()["choices"][0]["message"]["content"]), plan)
            except Exception as error:  # noqa: BLE001 - text generation must not break deterministic training
                log.warning("Coach plan generation failed (%s): %s", type(error).__name__, error)
                return None
        if local_llm is None:
            return None
        parsed = local_llm.chat_json(system, json.dumps(payload, ensure_ascii=False), temperature=0.6, max_tokens=2200)
        return self._validate_coach_plan(parsed, plan) if parsed else None

    @staticmethod
    def _validate_coach_plan(parsed, plan):
        if not isinstance(parsed, dict):
            return None
        summary = clean_text(parsed.get("summary"), MAX_SUMMARY)
        raw_actions = parsed.get("actions")
        if not isinstance(raw_actions, list):
            return None
        actions = [clean_text(item, MAX_ACTION) for item in raw_actions]
        rows = parsed.get("scenarios")
        expected = {scenario.id: scenario for scenario in plan.scenarios}
        if not summary or not actions or any(not item for item in actions) or not 2 <= len(actions) <= 5 or not isinstance(rows, list):
            return None
        updates = {}
        for row in rows:
            if not isinstance(row, dict) or row.get("id") not in expected:
                return None
            card = clean_text(row.get("customer_card"), MAX_CARD)
            brief = clean_text(row.get("trainer_brief"), MAX_BRIEF)
            raw_criteria = row.get("success_criteria")
            if not isinstance(raw_criteria, list):
                return None
            criteria = [clean_text(item, 180) for item in raw_criteria]
            if not card or not brief or any(not item for item in criteria) or not 2 <= len(criteria) <= 4:
                return None
            updates[row["id"]] = expected[row["id"]].model_copy(
                update={
                    "customer_card": card,
                    "trainer_brief": brief,
                    "success_criteria": criteria,
                    "enrichment": "llm",
                }
            )
        if set(updates) != set(expected):
            return None
        return summary, actions, [updates[scenario.id] for scenario in plan.scenarios]

    def _local(self, scenario: TrainingScenario) -> TrainingScenario | None:
        if local_llm is None:
            return None
        parsed = local_llm.chat_json(SYSTEM_PROMPT, self._user_prompt(scenario), temperature=0.7, max_tokens=300)
        card, brief = clean_text((parsed or {}).get("customer_card"), MAX_CARD), clean_text((parsed or {}).get("trainer_brief"), MAX_BRIEF)
        if not card or not brief:
            log.warning("Local enrichment gave no usable answer")
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
