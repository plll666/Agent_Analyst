"""Версии требований и прогоны против настоящего Postgres."""

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories import projects, runs
from tests.integration.conftest import case_document

pytestmark = pytest.mark.integration


async def _project_with_model(
    session: AsyncSession, owner_id: uuid.UUID
) -> tuple[uuid.UUID, uuid.UUID]:
    project = await projects.create(session, owner_id=owner_id, name="Модуль заявок")
    model = await runs.create_model_version(
        session,
        project.id,
        version=1,
        source="agent",
        document=case_document(),
        schema_hash="a" * 64,
        validation_status="VALID",
    )
    return project.id, model.id


async def test_versions_are_continuous(session: AsyncSession, owner_id: uuid.UUID) -> None:
    project = await projects.create(session, owner_id=owner_id, name="Заявки")

    for text_value in ("первая", "вторая", "третья"):
        await projects.add_requirement_version(session, project.id, raw_text=text_value)

    versions = list(reversed(await projects.list_requirements(session, project.id, owner_id)))
    assert [item.version for item in versions] == [1, 2, 3]


async def test_versions_are_immutable_and_returned_descending(
    session: AsyncSession, owner_id: uuid.UUID
) -> None:
    project = await projects.create(session, owner_id=owner_id, name="Заявки")
    await projects.add_requirement_version(session, project.id, raw_text="первая")
    await projects.add_requirement_version(session, project.id, raw_text="вторая")

    listed = await projects.list_requirements(session, project.id, owner_id)

    assert [item.version for item in listed] == [2, 1]
    assert [item.raw_text for item in listed] == ["вторая", "первая"]


async def test_only_latest_version_is_current(session: AsyncSession, owner_id: uuid.UUID) -> None:
    project = await projects.create(session, owner_id=owner_id, name="Заявки")
    await projects.add_requirement_version(session, project.id, raw_text="первая")
    latest = await projects.add_requirement_version(session, project.id, raw_text="вторая")

    listed = await projects.list_requirements(session, project.id, owner_id)
    current = [item for item in listed if item.is_current]

    assert latest is not None
    assert latest.is_current is True
    assert len(current) == 1
    assert current[0].version == 2


async def test_requirement_of_stranger_is_invisible(
    session: AsyncSession, owner_id: uuid.UUID, stranger_id: uuid.UUID
) -> None:
    project = await projects.create(session, owner_id=owner_id, name="Заявки")
    added = await projects.add_requirement_version(session, project.id, raw_text="текст")
    assert added is not None

    assert await projects.get_requirement_for_owner(session, added.id, stranger_id) is None
    assert await projects.get_requirement_for_owner(session, added.id, owner_id) is not None
    assert await projects.list_requirements(session, project.id, stranger_id) == []


async def test_requirement_of_unknown_project_returns_none(session: AsyncSession) -> None:
    added = await projects.add_requirement_version(session, uuid.uuid4(), raw_text="текст")

    assert added is None


async def test_pending_verification_has_empty_summary(
    session: AsyncSession, owner_id: uuid.UUID
) -> None:
    project_id, model_id = await _project_with_model(session, owner_id)

    created = await runs.create_pending_verification(
        session, project_id=project_id, model_version_id=model_id, engine="TLC"
    )

    assert created.status == "PENDING"
    assert created.business_summary == ""
    assert created.property_id is None
    assert created.counterexample is None


async def test_latest_model_version_is_the_highest(
    session: AsyncSession, owner_id: uuid.UUID
) -> None:
    project = await projects.create(session, owner_id=owner_id, name="Заявки")
    for version in (1, 2, 3):
        await runs.create_model_version(
            session,
            project.id,
            version=version,
            source="agent",
            document=case_document(),
            schema_hash=str(version) * 64,
            validation_status="VALID",
        )

    latest = await runs.latest_model_version(session, project.id, owner_id)

    assert latest is not None
    assert latest.version == 3


async def test_save_result_writes_every_field(session: AsyncSession, owner_id: uuid.UUID) -> None:
    project_id, model_id = await _project_with_model(session, owner_id)
    pending = await runs.create_pending_verification(
        session, project_id=project_id, model_version_id=model_id, engine="TLC"
    )

    saved = await runs.save_result(
        session,
        pending.id,
        status="PROPERTY_VIOLATED",
        engine="TLC",
        business_summary="Найден контрпример: Created → Cancel.",
        property_id="P1",
        engine_version="1.7.4",
        statistics={"states_generated": 162, "distinct_states": 37, "depth": 8},
        counterexample={"steps": [{"number": 0, "state": {"status": "Created"}}]},
        related_requirements=[{"paragraph_ref": "p3", "quote": "Заявка"}],
        duration_ms=812,
        error_detail=None,
        hypothesis="нет условия, запрещающего Cancel",
        question="должен ли Cancel сбрасывать признак?",
    )
    await session.commit()

    assert saved is not None
    stored = await runs.get_verification(session, pending.id)
    assert stored is not None
    assert stored.status == "PROPERTY_VIOLATED"
    assert stored.property_id == "P1"
    assert stored.engine_version == "1.7.4"
    assert stored.duration_ms == 812
    assert stored.statistics is not None
    assert stored.statistics["distinct_states"] == 37
    assert stored.counterexample is not None
    assert stored.related_requirements is not None
    assert stored.related_requirements[0]["paragraph_ref"] == "p3"
    assert stored.hypothesis == "нет условия, запрещающего Cancel"
    assert stored.question == "должен ли Cancel сбрасывать признак?"


async def test_model_auto_edited_stays_false(session: AsyncSession, owner_id: uuid.UUID) -> None:
    project_id, model_id = await _project_with_model(session, owner_id)
    pending = await runs.create_pending_verification(
        session, project_id=project_id, model_version_id=model_id, engine="TLC"
    )
    await runs.save_result(
        session,
        pending.id,
        status="PROPERTY_HOLDS",
        engine="TLC",
        business_summary="Нарушений не найдено.",
    )
    await session.commit()

    stored = await runs.get_verification(session, pending.id)

    assert stored is not None
    assert stored.model_auto_edited is False


async def test_database_rejects_auto_edit(session: AsyncSession, owner_id: uuid.UUID) -> None:
    """CHECK в БД — вторая линия: даже прямой UPDATE не пройдёт."""
    from sqlalchemy import text

    project_id, model_id = await _project_with_model(session, owner_id)
    pending = await runs.create_pending_verification(
        session, project_id=project_id, model_version_id=model_id, engine="TLC"
    )
    await session.commit()

    with pytest.raises(Exception, match="ck_verifications_model_auto_edited"):
        await session.execute(
            text("UPDATE verifications SET model_auto_edited = true WHERE id = :id"),
            {"id": pending.id},
        )


async def test_save_result_for_unknown_verification(session: AsyncSession) -> None:
    saved = await runs.save_result(
        session,
        uuid.uuid4(),
        status="ENGINE_ERROR",
        engine="TLC",
        business_summary="Прогон не найден.",
    )

    assert saved is None


async def test_verifications_are_scoped_to_owner(
    session: AsyncSession, owner_id: uuid.UUID, stranger_id: uuid.UUID
) -> None:
    project_id, model_id = await _project_with_model(session, owner_id)
    await runs.create_pending_verification(
        session, project_id=project_id, model_version_id=model_id, engine="TLC"
    )

    mine = await runs.list_verifications(session, project_id, owner_id)
    theirs = await runs.list_verifications(session, project_id, stranger_id)

    assert len(mine) == 1
    assert theirs == []
    assert await runs.get_verification_for_owner(session, mine[0].id, stranger_id) is None


async def test_models_are_scoped_to_owner(
    session: AsyncSession, owner_id: uuid.UUID, stranger_id: uuid.UUID
) -> None:
    project_id, _ = await _project_with_model(session, owner_id)

    mine = await runs.list_models_for_owner(session, project_id, owner_id)
    theirs = await runs.list_models_for_owner(session, project_id, stranger_id)

    assert len(mine) == 1
    assert theirs == []
    assert await runs.latest_model_version(session, project_id, stranger_id) is None


async def test_model_document_survives_round_trip(
    session: AsyncSession, owner_id: uuid.UUID
) -> None:
    project_id, model_id = await _project_with_model(session, owner_id)
    await session.commit()

    latest = await runs.latest_model_version(session, project_id, owner_id)

    assert latest is not None
    assert latest.id == model_id
    assert latest.document["variables"][0]["name"] == "status"
    assert latest.document["transitions"][0]["guard"] == {"eq": [{"var": "status"}, "Created"]}


async def test_artifact_is_stored(session: AsyncSession, owner_id: uuid.UUID) -> None:
    project_id, model_id = await _project_with_model(session, owner_id)
    pending = await runs.create_pending_verification(
        session, project_id=project_id, model_version_id=model_id, engine="TLC"
    )

    artifact = await runs.create_artifact(
        session,
        project_id=project_id,
        kind="tla",
        storage_uri="s3://agent-analyst-artifacts/model.tla",
        sha256="b" * 64,
        size_bytes=2048,
        model_version_id=model_id,
        verification_id=pending.id,
    )

    assert artifact.kind == "tla"
    assert artifact.verification_id == pending.id
    assert artifact.size_bytes == 2048
