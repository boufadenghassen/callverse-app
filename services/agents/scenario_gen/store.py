"""Scenario history: what was generated, so it can be replayed, mutated and traced.

Memory by default. With SCENARIO_STORE_PATH it also appends to a JSON-lines file and reloads it at start-up.
"""
import threading
from pathlib import Path

from .schemas import TrainingScenario


class ScenarioNotFound(KeyError):
    pass


class ScenarioStore:
    def __init__(self, path: str | Path | None = None):
        self._items: dict[str, TrainingScenario] = {}
        self._lock = threading.Lock()
        self._path = Path(path) if path else None
        if self._path and self._path.is_file():
            for line in self._path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    scenario = TrainingScenario.model_validate_json(line)
                    self._items[scenario.id] = scenario

    def save(self, scenario: TrainingScenario) -> TrainingScenario:
        with self._lock:
            is_new = scenario.id not in self._items
            self._items[scenario.id] = scenario
            if self._path and is_new:
                self._path.parent.mkdir(parents=True, exist_ok=True)
                with self._path.open("a", encoding="utf-8") as handle:
                    handle.write(scenario.model_dump_json() + "\n")
        return scenario

    def get(self, scenario_id: str) -> TrainingScenario:
        with self._lock:
            try:
                return self._items[scenario_id]
            except KeyError:
                raise ScenarioNotFound(scenario_id) from None

    def delete(self, scenario_id: str) -> None:
        with self._lock:
            if scenario_id not in self._items:
                raise ScenarioNotFound(scenario_id)
            del self._items[scenario_id]
            if self._path:
                self._path.write_text(
                    "".join(item.model_dump_json() + "\n" for item in self._items.values()),
                    encoding="utf-8",
                )

    def find(
        self,
        kind: str | None = None,
        intent: str | None = None,
        language: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[TrainingScenario]:
        with self._lock:
            items = list(self._items.values())
        if kind:
            items = [s for s in items if s.kind == kind]
        if intent:
            items = [s for s in items if s.spec.intent == intent]
        if language:
            items = [s for s in items if s.spec.language == language]
        return items[offset : offset + limit]

    def lineage(self, scenario_id: str) -> list[TrainingScenario]:
        """The scenario and its ancestors, oldest first."""
        chain: list[TrainingScenario] = []
        seen: set[str] = set()
        current: str | None = scenario_id
        while current and current not in seen:
            seen.add(current)
            scenario = self.get(current)
            chain.append(scenario)
            current = scenario.parent_id if scenario.parent_id in self._items else None
        return list(reversed(chain))

    def __len__(self) -> int:
        return len(self._items)
