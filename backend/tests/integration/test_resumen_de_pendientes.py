"""Change 25, tarea 6.2: `GET /api/v1/observaciones/resumen`, lo pendiente para el aviso de
`/admin` (spec `sync/revision-de-observaciones`, requisito "Administración ve un aviso de lo
pendiente", escenarios del servidor; `design.md` D5).

Reglas citadas: CRE-09, SYN-08, INV-21, INV-02, SEG-06.
"""

# ruff: noqa: F811  (las fixtures importadas se piden por nombre de parámetro)

from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import UUID, uuid4

from cuentas_corrientes_utiles import crear_organizacion, crear_usuario_y_dispositivo
from fastapi.testclient import TestClient
from revision_utiles import sembrar_observaciones
from sqlalchemy import text
from sqlalchemy.orm import Session
from test_stock_api import (  # noqa: F401  (fixtures reutilizadas)
    Entorno,
    _con_op,
    _limpiar_datos_confirmados,
    cliente,
    sesion,
)

URL = "/api/v1/observaciones/resumen"
REVISOR = frozenset({"REVISAR_OBSERVACIONES"})
MOMENTO = datetime(2026, 11, 5, 12, 0, tzinfo=UTC)


def _rechazo(
    sesion: Session, org: UUID, usuario: UUID, dispositivo: UUID, **cambios: object
) -> None:
    valores: dict[str, object] = {
        "id": uuid4(),
        "organizacion_id": org,
        "operation_id": uuid4(),
        "tipo": "VENTA_CONFIRMAR",
        "version": 1,
        "modo": "OFFLINE",
        "usuario_id": usuario,
        "dispositivo_id": dispositivo,
        "secuencia": 1,
        "occurred_at": MOMENTO,
        "app_version": "prueba",
        "contenido": json.dumps({"venta_id": str(uuid4())}),
        "error_codigo": "CLIENTE_INEXISTENTE",
        "recibido_en": MOMENTO,
        "estado": "PENDIENTE",
    }
    valores.update(cambios)
    sesion.execute(
        text(
            "INSERT INTO comando_rechazado (id, organizacion_id, operation_id, tipo, version, "
            "modo, usuario_id, dispositivo_id, secuencia, occurred_at, app_version, contenido, "
            "error_codigo, recibido_en, estado) VALUES (:id, :organizacion_id, :operation_id, "
            ":tipo, :version, :modo, :usuario_id, :dispositivo_id, :secuencia, :occurred_at, "
            ":app_version, CAST(:contenido AS jsonb), :error_codigo, :recibido_en, :estado)"
        ),
        valores,
    )


def _cuarentena(
    sesion: Session, org: UUID, usuario: UUID, dispositivo: UUID, **cambios: object
) -> None:
    valores: dict[str, object] = {
        "id": uuid4(),
        "organizacion_id": org,
        "dispositivo_id": dispositivo,
        "usuario_id": usuario,
        "operation_id": uuid4(),
        "tipo": "VENTA_CONFIRMAR",
        "contenido": json.dumps({"venta_id": str(uuid4())}),
        "motivo": "DISPOSITIVO_REVOCADO",
        "recibido_en": MOMENTO,
    }
    valores.update(cambios)
    sesion.execute(
        text(
            "INSERT INTO comando_cuarentena (id, organizacion_id, dispositivo_id, usuario_id, "
            "operation_id, tipo, contenido, motivo, recibido_en) VALUES (:id, :organizacion_id, "
            ":dispositivo_id, :usuario_id, :operation_id, :tipo, CAST(:contenido AS jsonb), "
            ":motivo, :recibido_en)"
        ),
        valores,
    )


def test_el_resumen_cuenta_los_avisos_por_codigo_los_rechazos_y_las_cuarentenas(
    cliente: TestClient, sesion: Session
) -> None:
    """Escenario "Exceso detectado al sincronizar" (CRE-09): el contador sube y el exceso se
    distingue por su código."""
    entorno = Entorno(sesion, permisos=REVISOR)
    sembrar_observaciones(
        sesion,
        entorno.org,
        usuario_id=entorno.usuario_id,
        dispositivo_id=entorno.dispositivo_id,
        codigos=("STOCK_NEGATIVO", "STOCK_NEGATIVO", "EXCESO_CREDITO_DETECTADO_SYNC"),
    )
    _rechazo(sesion, entorno.org, entorno.usuario_id, entorno.dispositivo_id)
    _rechazo(sesion, entorno.org, entorno.usuario_id, entorno.dispositivo_id)
    _cuarentena(sesion, entorno.org, entorno.usuario_id, entorno.dispositivo_id)
    headers = entorno.confirmar_y_entrar(cliente)

    respuesta = cliente.get(URL, headers=headers)

    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["observaciones_por_codigo"] == {
        "STOCK_NEGATIVO": 2,
        "EXCESO_CREDITO_DETECTADO_SYNC": 1,
    }
    assert cuerpo["observaciones_pendientes"] == 3
    assert cuerpo["rechazos_pendientes"] == 2
    assert cuerpo["cuarentenas_pendientes"] == 1
    assert cuerpo["total_pendiente"] == 6


def test_lo_resuelto_no_cuenta_como_pendiente(cliente: TestClient, sesion: Session) -> None:
    """Escenario "Sin pendientes" (SYN-08): todo en cero cuando se resolvió todo."""
    entorno = Entorno(sesion, permisos=REVISOR)
    observado = sembrar_observaciones(
        sesion,
        entorno.org,
        usuario_id=entorno.usuario_id,
        dispositivo_id=entorno.dispositivo_id,
        codigos=("STOCK_NEGATIVO", "VENTA_SIN_COSTO"),
    )
    headers = entorno.confirmar_y_entrar(cliente)
    resolucion = cliente.post(
        "/api/v1/observaciones/resolucion",
        json={"observaciones": [str(i) for i in observado.observaciones], "comentario": "Listo"},
        headers=_con_op(headers),
    )
    assert resolucion.status_code == 200, resolucion.text

    cuerpo = cliente.get(URL, headers=headers).json()

    assert cuerpo == {
        "observaciones_por_codigo": {},
        "observaciones_pendientes": 0,
        "rechazos_pendientes": 0,
        "cuarentenas_pendientes": 0,
        "total_pendiente": 0,
    }


def test_un_rechazo_y_una_cuarentena_ya_resueltos_no_cuentan(
    cliente: TestClient, sesion: Session
) -> None:
    entorno = Entorno(sesion, permisos=REVISOR)
    _rechazo(sesion, entorno.org, entorno.usuario_id, entorno.dispositivo_id)
    sesion.execute(
        text(
            "UPDATE comando_rechazado SET estado = 'RESUELTO', resuelto_por_id = :u, "
            "resuelto_en = :m, comentario = 'No ocurrió' WHERE organizacion_id = :o"
        ),
        {"u": entorno.usuario_id, "m": MOMENTO, "o": entorno.org},
    )
    _cuarentena(sesion, entorno.org, entorno.usuario_id, entorno.dispositivo_id)
    sesion.execute(
        text(
            "UPDATE comando_cuarentena SET revisado_en = :m, revisado_por_id = :u, "
            "comentario = 'Era real' WHERE organizacion_id = :o"
        ),
        {"u": entorno.usuario_id, "m": MOMENTO, "o": entorno.org},
    )
    headers = entorno.confirmar_y_entrar(cliente)

    cuerpo = cliente.get(URL, headers=headers).json()

    assert cuerpo["rechazos_pendientes"] == 0
    assert cuerpo["cuarentenas_pendientes"] == 0
    assert cuerpo["total_pendiente"] == 0


def test_solo_cuenta_la_organizacion_del_token(cliente: TestClient, sesion: Session) -> None:
    """Escenario "Otra organización no aparece" (INV-21, INV-02)."""
    entorno = Entorno(sesion, permisos=REVISOR)
    sembrar_observaciones(
        sesion,
        entorno.org,
        usuario_id=entorno.usuario_id,
        dispositivo_id=entorno.dispositivo_id,
        codigos=("STOCK_NEGATIVO",),
    )
    otra_org = crear_organizacion(sesion).id
    usuario, dispositivo = crear_usuario_y_dispositivo(sesion, otra_org)
    sembrar_observaciones(
        sesion,
        otra_org,
        usuario_id=usuario,
        dispositivo_id=dispositivo,
        codigos=("STOCK_NEGATIVO", "VENTA_SIN_COSTO"),
    )
    _rechazo(sesion, otra_org, usuario, dispositivo)
    _cuarentena(sesion, otra_org, usuario, dispositivo)
    headers = entorno.confirmar_y_entrar(cliente)

    cuerpo = cliente.get(URL, headers=headers).json()

    assert cuerpo["observaciones_por_codigo"] == {"STOCK_NEGATIVO": 1}
    assert cuerpo["rechazos_pendientes"] == 0
    assert cuerpo["cuarentenas_pendientes"] == 0
    assert cuerpo["total_pendiente"] == 1


def test_sin_el_permiso_responde_403(cliente: TestClient, sesion: Session) -> None:
    """Escenario "Sin permiso no hay aviso" (`01` §19, SEG-06)."""
    entorno = Entorno(sesion, permisos=frozenset({"VENDER"}))
    headers = entorno.confirmar_y_entrar(cliente)

    respuesta = cliente.get(URL, headers=headers)

    assert respuesta.status_code == 403
    assert respuesta.json()["codigo"] == "PERMISO_REQUERIDO"
