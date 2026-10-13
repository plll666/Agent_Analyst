"""Acceptance tests for Task 2: trace parsing, check_behavior, DB persistence."""

import uuid

import pytest

from app.database.models import ModelVersion, Project, Verification
from app.worker.db import (
    create_engine_and_sessionmaker,
    get_verification_model,
    save_verification_result,
)
from app.worker.model_checker import compile_to_tla, run_tlc

MODEL_VIOLATION = {
    "variables": [
        {
            "name": "status",
            "type": "enum",
            "values": ["Created", "Approved", "Cancelled", "Executed"],
        },
        {"name": "approved", "type": "boolean"},
        {"name": "cancelled", "type": "boolean"},
    ],
    "initial": {"status": "Created", "approved": False, "cancelled": False},
    "transitions": [
        {
            "name": "Approve",
            "guard": {"eq": [{"var": "status"}, "Created"]},
            "effects": [
                {"set": ["status", "Approved"]},
                {"set": ["approved", True]},
            ],
        },
        {
            "name": "Cancel",
            "guard": {"in": [{"var": "status"}, ["Created", "Approved"]]},
            "effects": [
                {"set": ["status", "Cancelled"]},
                {"set": ["cancelled", True]},
            ],
        },
        {
            "name": "Execute",
            "guard": {"eq": [{"var": "approved"}, True]},
            "effects": [{"set": ["status", "Executed"]}],
        },
    ],
    "properties": [
        {
            "id": "P1",
            "type": "forbidden_state",
            "expression": {
                "and": [
                    {"eq": [{"var": "status"}, "Executed"]},
                    {"eq": [{"var": "cancelled"}, True]},
                ]
            },
        }
    ],
}


MODEL_HOLDS = {
    "variables": [
        {
            "name": "status",
            "type": "enum",
            "values": ["Created", "Approved", "Cancelled", "Executed"],
        },
        {"name": "approved", "type": "boolean"},
        {"name": "cancelled", "type": "boolean"},
    ],
    "initial": {"status": "Created", "approved": False, "cancelled": False},
    "transitions": [
        {
            "name": "Approve",
            "guard": {"eq": [{"var": "status"}, "Created"]},
            "effects": [
                {"set": ["status", "Approved"]},
                {"set": ["approved", True]},
            ],
        },
        {
            "name": "Cancel",
            "guard": {"in": [{"var": "status"}, ["Created", "Approved"]]},
            "effects": [
                {"set": ["status", "Cancelled"]},
                {"set": ["cancelled", True]},
                {"set": ["approved", False]},
            ],
        },
        {
            "name": "Execute",
            "guard": {"eq": [{"var": "approved"}, True]},
            "effects": [{"set": ["status", "Executed"]}],
        },
    ],
    "properties": [
        {
            "id": "P1",
            "type": "forbidden_state",
            "expression": {
                "and": [
                    {"eq": [{"var": "status"}, "Executed"]},
                    {"eq": [{"var": "cancelled"}, True]},
                ]
            },
        }
    ],
}


@pytest.mark.integration
async def test_compile_tla_violation_model():
    """Test TLA compilation for violation model."""
    tla, cfg = compile_to_tla(MODEL_VIOLATION)
    assert "VARIABLES status, approved, cancelled" in tla
    assert 'status = "Created"' in tla
    assert "Approve ==" in tla
    assert "INVARIANT P1 ==" in cfg
    assert '~(status = "Executed" /\\ cancelled = TRUE)' in cfg


@pytest.mark.integration
async def test_compile_tla_holds_model():
    """Test TLA compilation for holds model."""
    tla, cfg = compile_to_tla(MODEL_HOLDS)
    assert "Cancel ==" in tla
    assert "approved' = FALSE" in tla


@pytest.mark.integration
async def test_run_tlc_violation_returns_property_violated():
    """Test TLC returns PROPERTY_VIOLATED with counterexample for violation model."""
    tla, cfg = compile_to_tla(MODEL_VIOLATION)
    result = run_tlc(tla, cfg)

    assert result["status"] == "PROPERTY_VIOLATED"
    assert result["engine"] == "TLC"
    assert result["counterexample"] is not None
    assert "steps" in result["counterexample"]
    steps = result["counterexample"]["steps"]
    assert len(steps) == 4

    assert steps[0]["number"] == 0
    assert steps[0]["transition"] is None
    assert steps[0]["state"]["status"] == "Created"
    assert steps[0]["state"]["approved"] is False
    assert steps[0]["state"]["cancelled"] is False

    assert steps[1]["number"] == 1
    assert steps[1]["transition"] == "Approve"
    assert steps[1]["state"]["status"] == "Approved"
    assert steps[1]["state"]["approved"] is True

    assert steps[2]["number"] == 2
    assert steps[2]["transition"] == "Cancel"
    assert steps[2]["state"]["status"] == "Cancelled"
    assert steps[2]["state"]["cancelled"] is True

    assert steps[3]["number"] == 3
    assert steps[3]["transition"] == "Execute"
    assert steps[3]["state"]["status"] == "Executed"
    assert steps[3]["state"]["cancelled"] is True


@pytest.mark.integration
async def test_run_tlc_holds_returns_property_holds():
    """Test TLC returns PROPERTY_HOLDS for fixed model."""
    tla, cfg = compile_to_tla(MODEL_HOLDS)
    result = run_tlc(tla, cfg)

    assert result["status"] == "PROPERTY_HOLDS"
    assert result["engine"] == "TLC"
    assert result["counterexample"] is None


@pytest.mark.integration
async def test_db_persist_verification_result():
    """Test saving verification result to database."""
    engine, sessionmaker = create_engine_and_sessionmaker()

    async with sessionmaker() as session:
        project = Project(id=uuid.uuid4(), owner_id=uuid.uuid4(), name="Test Project")
        session.add(project)

        model_version = ModelVersion(
            id=uuid.uuid4(),
            project_id=project.id,
            version=1,
            source="manual",
            document=MODEL_VIOLATION,
            schema_hash="test_hash",
            validation_status="valid",
        )
        session.add(model_version)

        verification = Verification(
            id=uuid.uuid4(),
            project_id=project.id,
            model_version_id=model_version.id,
            status="PENDING",
            engine="TLC",
            business_summary="",
        )
        session.add(verification)
        await session.commit()

        verification_id = str(verification.id)

    result = {
        "status": "PROPERTY_VIOLATED",
        "engine": "TLC",
        "engine_version": "TLC 1.7.4",
        "counterexample": {"steps": [{"number": 0, "state": {"status": "Created"}}]},
        "statistics": {"states_generated": 10, "distinct_states": 5, "depth": 3},
        "duration_ms": 123,
        "error_detail": None,
        "business_summary": "",
    }

    await save_verification_result(sessionmaker, verification_id, result)

    async with sessionmaker() as session:
        saved = await session.get(Verification, uuid.UUID(verification_id))
        assert saved is not None
        assert saved.status == "PROPERTY_VIOLATED"
        assert saved.engine == "TLC"
        assert saved.counterexample is not None
        assert saved.statistics["states_generated"] == 10
        assert saved.duration_ms == 123

    await engine.dispose()


@pytest.mark.integration
async def test_get_verification_model():
    """Test loading model for verification."""
    engine, sessionmaker = create_engine_and_sessionmaker()

    async with sessionmaker() as session:
        project = Project(id=uuid.uuid4(), owner_id=uuid.uuid4(), name="Test Project 2")
        session.add(project)

        model_version = ModelVersion(
            id=uuid.uuid4(),
            project_id=project.id,
            version=1,
            source="manual",
            document=MODEL_VIOLATION,
            schema_hash="test_hash_2",
            validation_status="valid",
        )
        session.add(model_version)

        verification = Verification(
            id=uuid.uuid4(),
            project_id=project.id,
            model_version_id=model_version.id,
            status="PENDING",
            engine="TLC",
            business_summary="",
        )
        session.add(verification)
        await session.commit()

        verification_id = str(verification.id)

    model_data = await get_verification_model(sessionmaker, verification_id)
    assert model_data is not None
    assert model_data["verification_id"] == verification_id
    assert model_data["document"] == MODEL_VIOLATION

    await engine.dispose()


@pytest.mark.integration
async def test_get_verification_model_not_found():
    """Test loading model for non-existent verification."""
    engine, sessionmaker = create_engine_and_sessionmaker()

    model_data = await get_verification_model(sessionmaker, str(uuid.uuid4()))
    assert model_data is None

    await engine.dispose()
