"""HTTP endpoints of the Scenario Gen agent. Mounted by main.py under /scenario-gen."""
from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException, Query

from .config import Settings
from .schemas import (
    BatchRequest,
    GenerateRequest,
    MutateRequest,
    ProgressReport,
    ProgressRequest,
    RampRequest,
    ReplayRequest,
    SimScenario,
    TrainingPlan,
    TrainingPlanRequest,
    TrainingScenario,
    WebScenario,
)
from .service import BadRequest, ScenarioService
from .store import ScenarioNotFound

router = APIRouter(prefix="/scenario-gen", tags=["scenario-gen"])


@lru_cache
def get_service() -> ScenarioService:
    return ScenarioService.from_settings(Settings.from_env())


def _guard(call):
    """Turn service errors into HTTP errors."""
    try:
        return call()
    except ScenarioNotFound as error:
        raise HTTPException(404, f"scenario {error} not found") from error
    except BadRequest as error:
        raise HTTPException(422, str(error)) from error


@router.get("/health")
def health(service: ScenarioService = Depends(get_service)) -> dict:
    return {"status": "ok", "intents": len(service.catalog.intents), "stored_scenarios": len(service.store)}


@router.get("/catalog")
def catalog(service: ScenarioService = Depends(get_service)) -> dict:
    """The template library: intents, complications, skills, languages."""
    return service.catalog_summary()


@router.post("/scenarios/generate", response_model=TrainingScenario)
def generate(req: GenerateRequest | None = None, service: ScenarioService = Depends(get_service)):
    """Build one scenario. An empty body gives a fully random one."""
    return _guard(lambda: service.generate(req or GenerateRequest()))


@router.post("/scenarios/batch", response_model=list[TrainingScenario])
def batch(req: BatchRequest | None = None, service: ScenarioService = Depends(get_service)):
    return _guard(lambda: service.batch(req or BatchRequest()))


@router.post("/scenarios/ramp", response_model=list[TrainingScenario])
def ramp(req: RampRequest | None = None, service: ScenarioService = Depends(get_service)):
    """The same situation at increasing difficulty (the difficulty ramp)."""
    return _guard(lambda: service.ramp(req or RampRequest()))


@router.get("/scenarios", response_model=list[TrainingScenario])
def list_scenarios(
    kind: str | None = None,
    intent: str | None = None,
    language: str | None = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    service: ScenarioService = Depends(get_service),
):
    return service.store.find(kind=kind, intent=intent, language=language, limit=limit, offset=offset)


@router.get("/scenarios/{scenario_id}", response_model=TrainingScenario)
def get_scenario(scenario_id: str, service: ScenarioService = Depends(get_service)):
    return _guard(lambda: service.get(scenario_id))


@router.delete("/scenarios/{scenario_id}", status_code=204)
def delete_scenario(scenario_id: str, service: ScenarioService = Depends(get_service)):
    _guard(lambda: service.delete(scenario_id))


@router.get("/scenarios/{scenario_id}/sim", response_model=SimScenario)
def get_sim_payload(scenario_id: str, service: ScenarioService = Depends(get_service)):
    """Exactly what the Customer Sim reads (its `Scenario` model)."""
    return _guard(lambda: service.get(scenario_id).sim)


@router.get("/scenarios/{scenario_id}/lineage", response_model=list[TrainingScenario])
def lineage(scenario_id: str, service: ScenarioService = Depends(get_service)):
    return _guard(lambda: service.lineage(scenario_id))


@router.post("/scenarios/{scenario_id}/replay", response_model=TrainingScenario)
def replay(scenario_id: str, req: ReplayRequest | None = None, service: ScenarioService = Depends(get_service)):
    return _guard(lambda: service.replay(scenario_id, (req or ReplayRequest()).reseed))


@router.post("/scenarios/{scenario_id}/mutate", response_model=TrainingScenario)
def mutate(scenario_id: str, req: MutateRequest, service: ScenarioService = Depends(get_service)):
    """What-if: change difficulty, language, intent, complications... and get a new scenario."""
    return _guard(lambda: service.mutate(scenario_id, req))


@router.post("/training-plan", response_model=TrainingPlan)
def training_plan(req: TrainingPlanRequest, service: ScenarioService = Depends(get_service)):
    """Quality Analyst weaknesses in, a plan of practice scenarios out."""
    return _guard(lambda: service.plan(req))


@router.post("/progress", response_model=ProgressReport)
def progress(req: ProgressRequest, service: ScenarioService = Depends(get_service)):
    """Compare two QA reports to see whether the training worked."""
    return service.progress(req)


# ---------------------------------------------------------------------------
# Adapter for the web app contract: GET /training/scenarios → Scenario[]
# The web app (training.njk, HttpAgentGateway) expects five flat fields:
#   { id, title, profile, difficulty, origin }
# Our TrainingScenario is richer; this route maps the relevant fields.
# ---------------------------------------------------------------------------
_DIFFICULTY_LABELS = {1: "Easy", 2: "Easy", 3: "Medium", 4: "Hard", 5: "Hard"}
_SEGMENT_LABELS = {
    "new": "New", "loyal": "Loyal", "dissatisfied": "Unsatisfied",
    "premium": "Premium", "at_risk": "At risk",
}
_ORIGIN_LABELS = {
    "generated": "Template library", "ramp": "Difficulty ramp",
    "replay": "Replay", "mutation": "What-if mutation", "adaptive": "QA weakness",
}

training_router = APIRouter(prefix="/training", tags=["training"])


@training_router.get("/scenarios")
def training_scenarios(service: ScenarioService = Depends(get_service)) -> list[WebScenario]:
    """The contract with the web app: flat scenario cards for the training page."""
    return [
        WebScenario(
            id=s.id,
            title=s.title,
            profile=_SEGMENT_LABELS.get(s.spec.segment, s.spec.segment.title()),
            difficulty=_DIFFICULTY_LABELS.get(s.spec.difficulty, "Medium"),
            origin=_ORIGIN_LABELS.get(s.kind, s.kind.title()),
        )
        for s in service.store.find(limit=100)
    ]
