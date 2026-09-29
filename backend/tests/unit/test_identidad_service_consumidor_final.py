"""Change 07, tarea 2.3: el setter de `identidad/service.py` que fija
`permite_consumidor_final` y `cliente_consumidor_final_id` de la organización
(`design.md` D4, ADR-029, `03` §4).

Vive en `identidad` y no en `clientes` porque la fila es de ese módulo:
`clientes` alcanza a `identidad` únicamente por su `service.py`, con el mismo
contrato de import-linter que ya existe para `configuracion`. Esta prueba no
necesita PostgreSQL: lo que importa es que el setter escriba LOS DOS campos
juntos, en la organización que recibe, y sin `commit`.
"""

from __future__ import annotations

import inspect
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest

from app.core.clock import FixedClock
from app.modules.identidad import repository as identidad_repository
from app.modules.identidad import service as identidad_service

MOMENTO = datetime(2026, 9, 28, 12, 0, tzinfo=UTC)


def _configuracion(organizacion_id: UUID) -> Any:
    """Doble de la fila. No hace falta una `ConfiguracionOrganizacion` real: lo
    que se verifica acá es QUÉ se le pasa al repositorio, y el constructor del
    modelo exige columnas que este test no populate."""
    return SimpleNamespace(organizacion_id=organizacion_id)


def test_el_setter_recibe_organizacion_id_primero() -> None:
    parametros = list(inspect.signature(identidad_service.configurar_consumidor_final).parameters)
    assert parametros[:3] == ["organizacion_id", "sesion", "reloj"]


def test_el_setter_escribe_el_permiso_y_el_identificador_juntos() -> None:
    """`03` §4 los declara como un par: `permite_consumidor_final` en `true`
    sin `cliente_consumidor_final_id` apuntaría a nada, y el identificador sin
    el permiso en `true` no significaría nada para el bootstrap del change 21
    (SYN-11)."""
    organizacion_id = uuid4()
    cliente_id = uuid4()
    enviados: dict[str, Any] = {}

    def _actualizar(org: UUID, ses: object, **campos: Any) -> Any:
        enviados["organizacion_id"] = org
        enviados.update(campos)
        return _configuracion(org)

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(identidad_repository, "actualizar_configuracion", _actualizar)
    try:
        identidad_service.configurar_consumidor_final(
            organizacion_id,
            object(),
            FixedClock(MOMENTO),
            cliente_consumidor_final_id=cliente_id,
        )
    finally:
        monkeypatch.undo()

    assert enviados["organizacion_id"] == organizacion_id
    assert enviados["permite_consumidor_final"] is True
    assert enviados["cliente_consumidor_final_id"] == cliente_id


def test_el_setter_usa_el_reloj_inyectable_y_no_la_hora_del_sistema() -> None:
    """TR-05: el momento sale de `core/clock.py`, no de `datetime.now()`."""
    organizacion_id = uuid4()
    enviados: dict[str, Any] = {}

    def _actualizar(org: UUID, ses: object, **campos: Any) -> Any:
        enviados.update(campos)
        return _configuracion(org)

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(identidad_repository, "actualizar_configuracion", _actualizar)
    try:
        identidad_service.configurar_consumidor_final(
            organizacion_id, object(), FixedClock(MOMENTO), cliente_consumidor_final_id=uuid4()
        )
    finally:
        monkeypatch.undo()

    assert enviados["momento"] == MOMENTO


def test_el_setter_propaga_el_actor() -> None:
    organizacion_id = uuid4()
    actor_id = uuid4()
    enviados: dict[str, Any] = {}

    def _actualizar(org: UUID, ses: object, **campos: Any) -> Any:
        enviados.update(campos)
        return _configuracion(org)

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(identidad_repository, "actualizar_configuracion", _actualizar)
    try:
        identidad_service.configurar_consumidor_final(
            organizacion_id,
            object(),
            FixedClock(MOMENTO),
            cliente_consumidor_final_id=uuid4(),
            actor_id=actor_id,
        )
    finally:
        monkeypatch.undo()

    assert enviados["actualizado_por_id"] == actor_id


def test_el_setter_admite_un_actor_desconocido() -> None:
    """`usuario_id` es `UUID | None` en `registrar_auditoria` y en el resto de
    las escrituras: un comando sin usuario autenticado no es un caso que la
    firma tenga que rechazar."""
    organizacion_id = uuid4()
    enviados: dict[str, Any] = {}

    def _actualizar(org: UUID, ses: object, **campos: Any) -> Any:
        enviados.update(campos)
        return _configuracion(org)

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(identidad_repository, "actualizar_configuracion", _actualizar)
    try:
        identidad_service.configurar_consumidor_final(
            organizacion_id, object(), FixedClock(MOMENTO), cliente_consumidor_final_id=uuid4()
        )
    finally:
        monkeypatch.undo()

    assert enviados["actualizado_por_id"] is None


def test_el_setter_no_cierra_la_transaccion() -> None:
    """`CLAUDE.md` §4: la transacción la gestiona el bus, que comparte la
    transacción con la creación del cliente (D4: no hay estado intermedio)."""
    fuente = inspect.getsource(identidad_service.configurar_consumidor_final)
    assert ".commit(" not in fuente


def test_el_setter_no_toca_la_configuracion_de_otra_organizacion() -> None:
    """INV-02/INV-21: la escritura va dirigida por `organizacion_id` y
    `repository.actualizar_configuracion` filtra por ella, así que el setter no
    necesita ni puede recibir un identificador de organización distinto."""
    parametros = inspect.signature(identidad_service.configurar_consumidor_final).parameters
    assert "otra_organizacion_id" not in parametros
    assert "organizaciones" not in parametros
    # Un solo destino, y es la fila de `organizacion_id`.
    assert parametros["cliente_consumidor_final_id"].kind is inspect.Parameter.KEYWORD_ONLY


def test_el_setter_no_admite_el_permiso_por_parametro() -> None:
    """El permiso va siempre en `true`: es lo que habilita al consumidor final.
    Aceptarlo como parámetro invitaría a escribirlo en `false`, que es un estado
    que ningún comando de este change produce."""
    parametros = inspect.signature(identidad_service.configurar_consumidor_final).parameters
    assert "permite_consumidor_final" not in parametros
