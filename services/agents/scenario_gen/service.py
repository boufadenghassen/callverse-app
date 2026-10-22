"""The Scenario Gen agent: one object that the API router, the CLI and the tests all use."""
import random
import secrets

from .adaptive import build_plan, compare_progress
from .catalog import Catalog, CatalogError, intent_keys_from_file
from .config import Settings
from .generator import ScenarioGenerator, derive_seed, MAX_SEED
from .llm import LLMClient
from .mutations import MutationError, apply_ops, random_ops
from .schemas import (
    BatchRequest,
    GenerateRequest,
    MutateRequest,
    ProgressReport,
    ProgressRequest,
    RampRequest,
    TrainingPlan,
    TrainingPlanRequest,
    TrainingScenario,
)
from .store import ScenarioStore

__all__ = ["ScenarioService", "BadRequest"]


class BadRequest(ValueError):
    """The request cannot be served (unknown intent, impossible mutation...). Maps to HTTP 422."""


class ScenarioService:
    def __init__(
        self,
        catalog: Catalog | None = None,
        store: ScenarioStore | None = None,
        llm: LLMClient | None = None,
    ):
        self.catalog = catalog or Catalog.load()
        self.store = store if store is not None else ScenarioStore()
        self.llm = llm
        self.generator = ScenarioGenerator(self.catalog)

    @classmethod
    def from_settings(cls, settings: Settings) -> "ScenarioService":
        catalog = Catalog.load()
        if settings.sim_intents_path:
            catalog.restrict_intents(intent_keys_from_file(settings.sim_intents_path))
        return cls(catalog, ScenarioStore(settings.store_path), LLMClient(settings))

    # ------------------------------------------------------------------ generation
    def generate(self, req: GenerateRequest) -> TrainingScenario:
        seed = req.seed if req.seed is not None else secrets.randbelow(MAX_SEED)
        try:
            spec = self.generator.new_spec(req, seed)
            scenario = self.generator.assemble(spec, kind="generated")
        except CatalogError as error:
            raise BadRequest(str(error)) from error
        return self._finish(scenario, req.enrich, req.advisor_id)

    def batch(self, req: BatchRequest) -> list[TrainingScenario]:
        if req.difficulty_max < req.difficulty_min:
            raise BadRequest("difficulty_max must be greater than or equal to difficulty_min")
        base = req.seed if req.seed is not None else secrets.randbelow(MAX_SEED)
        rng = random.Random(base)
        languages = req.languages or self.catalog.languages
        unused: list[str] = []
        out: list[TrainingScenario] = []
        for i in range(req.count):
            seed = derive_seed(base, "batch", i)
            difficulty = rng.randint(req.difficulty_min, req.difficulty_max)
            if not unused:  # every intent appears once before any repeats
                unused = sorted(self.catalog.intents)
            weights = [1.0 / (1 + abs(self.catalog.intents[k].base_difficulty - difficulty)) for k in unused]
            intent = rng.choices(unused, weights=weights)[0]
            unused.remove(intent)
            item = GenerateRequest(
                intent=intent,
                difficulty=difficulty,
                language=languages[i % len(languages)],
                mode=req.mode,
                seed=seed,
            )
            try:
                scenario = self.generator.assemble(self.generator.new_spec(item, seed), kind="generated")
            except CatalogError as error:
                raise BadRequest(str(error)) from error
            out.append(self._finish(scenario, req.enrich))
        return out

    def ramp(self, req: RampRequest) -> list[TrainingScenario]:
        seed = req.seed if req.seed is not None else secrets.randbelow(MAX_SEED)
        try:
            specs = self.generator.ramp_specs(req, seed)
        except CatalogError as error:
            raise BadRequest(str(error)) from error
        return [self._finish(self.generator.assemble(spec, kind="ramp"), False) for spec in specs]

    # ------------------------------------------------------------------ replay and what-if
    def get(self, scenario_id: str) -> TrainingScenario:
        return self.store.get(scenario_id)

    def delete(self, scenario_id: str) -> None:
        self.store.delete(scenario_id)

    def replay(self, scenario_id: str, reseed: bool = False) -> TrainingScenario:
        original = self.store.get(scenario_id)
        if not reseed:
            return original  # identical scenario, identical seed
        spec = original.spec.model_copy(update={"seed": derive_seed(original.spec.seed, "replay", len(self.store))})
        spec = self.generator.normalize_spec(spec, random.Random(spec.seed))
        scenario = self.generator.assemble(spec, kind="replay", parent_id=original.id, mutation_log=["reseed"])
        return self._finish(scenario, False, self._owner(original))

    def mutate(self, scenario_id: str, req: MutateRequest) -> TrainingScenario:
        original = self.store.get(scenario_id)
        if not req.ops and not req.random:
            raise BadRequest("give at least one operation in 'ops', or set 'random' to true")
        rng = random.Random(req.seed if req.seed is not None else secrets.randbelow(MAX_SEED))
        ops = list(req.ops)
        if req.random:
            ops += random_ops(original.spec, self.generator, rng)
        try:
            spec, log = apply_ops(original.spec, ops, self.generator, rng)
            scenario = self.generator.assemble(spec, kind="mutation", parent_id=original.id, mutation_log=log)
        except (MutationError, CatalogError) as error:
            raise BadRequest(str(error)) from error
        return self._finish(scenario, req.enrich, self._owner(original))

    def lineage(self, scenario_id: str) -> list[TrainingScenario]:
        return self.store.lineage(scenario_id)

    # ------------------------------------------------------------------ adaptive training
    def plan(self, req: TrainingPlanRequest) -> TrainingPlan:
        try:
            plan = build_plan(req, self.generator)
        except CatalogError as error:
            raise BadRequest(str(error)) from error
        owned: list[TrainingScenario] = []
        for scenario in plan.scenarios:
            owned.append(scenario.model_copy(update={
                "sim_extensions": {**scenario.sim_extensions, "advisor_id": req.advisor_id},
            }))
        plan = plan.model_copy(update={"scenarios": owned})
        for scenario in owned:
            self.store.save(scenario)
        return plan

    def progress(self, req: ProgressRequest) -> ProgressReport:
        return compare_progress(req.before, req.after)

    # ------------------------------------------------------------------ catalog for UIs
    def catalog_summary(self) -> dict:
        cat = self.catalog
        return {
            "languages": cat.languages,
            "segments": cat.segments,
            "skills": cat.skills,
            "intents": [
                {
                    "key": i.key,
                    "title": i.title,
                    "category": i.category,
                    "base_difficulty": i.base_difficulty,
                    "opening_emotion": i.opening_emotion,
                    "skills": list(i.skills),
                }
                for i in cat.intents.values()
            ],
            "events": [
                {"key": e.key, "rare": e.rare, "text": e.text, "stresses": list(e.stresses)}
                for e in cat.events.values()
            ],
            "llm_available": bool(self.llm and self.llm.available),
        }

    # ------------------------------------------------------------------ internals
    @staticmethod
    def _owner(scenario: TrainingScenario) -> str | None:
        owner = scenario.sim_extensions.get("advisor_id")
        return owner if isinstance(owner, str) and owner else None

    def _finish(self, scenario: TrainingScenario, enrich: bool, advisor_id: str | None = None) -> TrainingScenario:
        if advisor_id:
            scenario = scenario.model_copy(update={
                "sim_extensions": {**scenario.sim_extensions, "advisor_id": advisor_id},
            })
        if enrich:
            if self.llm is None or not self.llm.available:
                scenario = scenario.model_copy(
                    update={"notes": scenario.notes + ["LLM enrichment skipped: no OPENROUTER_API_KEY, templates used."]}
                )
            else:
                enriched = self.llm.enrich(scenario)
                if enriched is None:
                    scenario = scenario.model_copy(
                        update={"notes": scenario.notes + ["LLM enrichment failed, templates used."]}
                    )
                else:
                    scenario = enriched
        return self.store.save(scenario)
