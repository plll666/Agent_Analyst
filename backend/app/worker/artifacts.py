"""Хранилище артефактов прогона: ``.tla``, ``.cfg`` и сырой вывод TLC.

В dev-режиме это локальный каталог, как и предусмотрено для файлов в
``ARCHITECTURE.md`` §10.1; в докере тот же каталог монтируется томом. Ключи
``storage_uri``, ``sha256`` и ``size_bytes`` — ровно те, что ждёт таблица
``artifacts``, поэтому слой БД получает готовые значения и ничего не досчитывает.

Ссылку в БД ставит фоновая задача. Здесь только файлы и их метаданные: запись
требует ``project_id`` и ``model_version_id``, которых у движка нет.

Модель может нести несколько свойств, и спецификация у каждого своя — определение
проверяемого свойства входит в ``.tla``. Поэтому один прогон это один каталог, а
файлы внутри различаются именем свойства.
"""

from __future__ import annotations

import hashlib
import os
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

_KIND_SPEC = "tla_spec"
_KIND_CONFIG = "tlc_config"
_KIND_OUTPUT = "tlc_output"
_FILENAMES = {
    _KIND_SPEC: "{property}.tla",
    _KIND_CONFIG: "{property}.cfg",
    _KIND_OUTPUT: "{property}.out",
}
_DEFAULT_ROOT = "var/artifacts"


@dataclass(frozen=True, slots=True)
class RunArtifacts:
    """Файлы одного свойства: спецификация, конфигурация и вывод движка."""

    property_id: str
    spec: str
    cfg: str
    output: str


@dataclass(frozen=True, slots=True)
class StoredArtifact:
    """Файл на диске и то, что о нём записывается в таблицу ``artifacts``."""

    kind: str
    storage_uri: str
    sha256: str
    size_bytes: int


class LocalArtifactStore:
    """Каталог артефактов на локальной файловой системе."""

    def __init__(self, root: Path) -> None:
        self._root = root

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> LocalArtifactStore:
        """Каталог из ``ARTIFACTS_DIR``; по умолчанию — ``var/artifacts``.

        Args:
            env: Источник переменных; по умолчанию — окружение процесса.

        Returns:
            Хранилище, указывающее на каталог из настроек.
        """
        source = os.environ if env is None else env
        return cls(Path(source.get("ARTIFACTS_DIR", _DEFAULT_ROOT)))

    @property
    def root(self) -> Path:
        """Корень хранилища: его полезно знать тестам и диагностике."""
        return self._root

    def save_run(self, verification_id: str, runs: Sequence[RunArtifacts]) -> list[StoredArtifact]:
        """Сохранить всё, что относится к одному прогону.

        Args:
            verification_id: Идентификатор строки ``verifications``.
            runs: Файлы по каждому проверенному свойству.

        Returns:
            Метаданные сохранённых файлов, готовые к записи в ``artifacts``.
        """
        target = self._root / verification_id
        target.mkdir(parents=True, exist_ok=True)
        return [stored for run in runs for stored in self._write(target, run.property_id, run)]

    def _write(self, directory: Path, property_id: str, run: RunArtifacts) -> list[StoredArtifact]:
        """Записать три файла одного свойства в каталог прогона.

        Args:
            directory: Каталог прогона.
            property_id: Имя файла для этого свойства.
            run: Тексты спецификации, конфигурации и вывода.

        Returns:
            Метаданные записанных файлов.
        """
        payloads = {
            _KIND_SPEC: run.spec,
            _KIND_CONFIG: run.cfg,
            _KIND_OUTPUT: run.output,
        }
        stored: list[StoredArtifact] = []
        for kind, content in payloads.items():
            payload = content.encode("utf-8")
            name = _FILENAMES[kind].format(property=property_id)
            (directory / name).write_bytes(payload)
            stored.append(
                StoredArtifact(
                    kind=kind,
                    storage_uri=(directory / name).as_posix(),
                    sha256=hashlib.sha256(payload).hexdigest(),
                    size_bytes=len(payload),
                )
            )
        return stored
