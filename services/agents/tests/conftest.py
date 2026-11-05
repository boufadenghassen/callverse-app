import importlib.util
import os
from pathlib import Path

import pytest

os.environ["LOCAL_LLM"] = "0"       # the tests never depend on a model running on this machine; the ones about it put a fake in its place

from scenario_gen.catalog import Catalog
from scenario_gen.generator import ScenarioGenerator
from scenario_gen.service import ScenarioService
from scenario_gen.store import ScenarioStore

FIXTURE = Path(__file__).parent / "fixtures" / "customer_sim_schemas.py"


@pytest.fixture(scope="session")
def sim_schemas():
    """The Customer Sim's schema file, copied verbatim. If its owner changes it, update the fixture and rerun."""
    spec = importlib.util.spec_from_file_location("customer_sim_schemas", FIXTURE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def catalog() -> Catalog:
    return Catalog.load()


@pytest.fixture
def generator(catalog) -> ScenarioGenerator:
    return ScenarioGenerator(catalog)


@pytest.fixture
def service(catalog) -> ScenarioService:
    return ScenarioService(catalog, ScenarioStore(), llm=None)
