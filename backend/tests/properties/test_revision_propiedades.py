"""Change 25, tarea 20.1: propiedad (Hypothesis) de la revisión contra PostgreSQL real, con la base
como juez (consultas SQL sobre las tablas, no sobre las estructuras de la prueba).

**SYN-08, INV-05, INV-12, INV-13** (spec `sync/revision-de-observaciones`, "Resolver nunca altera la
operación"): para secuencias aleatorias de ventas y de cobranzas sin conexión con observaciones y
de resoluciones en bloque (grupos aleatorios, en orden aleatorio, con comentarios distintos), las
operaciones, sus líneas, los libros (stock, cuentas y costos), los saldos y los comandos quedan
idénticos byte a byte, y de las observaciones solo cambian las columnas de la resolución
(`estado`, `resuelto_por_id`, `resuelto_en`, `comentario`).

Cada ejemplo crea su propia organización dentro de la transacción de `db_session`, que se revierte
al terminar la prueba (mismo criterio que `test_ventas_18b_propiedades.py`).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from cobranzas_utiles import MOMENTO as MOMENTO_COBRANZA
from cobranzas_utiles import RELOJ as RELOJ_COBRANZA
from cobranzas_utiles import Entorno as EntornoCobranza
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from sqlalchemy import text
from sqlalchemy.orm import Session
from test_ventas_offline import Ruta
from ventas_anular_utiles import EntornoAnulacion
from ventas_confirmar_utiles import RELOJ_VENTA

from app.core.errors import DomainError
from app.modules.sync import revision_casos as casos
from app.modules.sync import service as sync_service
from app.modules.sync.service import ItemLote

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")

_PROPIEDAD = settings(
    max_examples=15,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture, HealthCheck.too_slow],
)

# Todo lo que una resolución NO puede tocar: la operación, sus líneas, los libros, los saldos y los
# comandos (con su resultado y su estado).
_TABLAS_INTACTAS = (
    "venta",
    "venta_linea",
    "cobranza",
    "cobranza_medio",
    "stock_movimiento",
    "stock_saldo",
    "cuenta_movimiento",
    "saldo_cuenta",
    "costo_producto_mov",
    "comando",
)
_COLUMNAS_DE_RESOLUCION = ("estado", "resuelto_por_id", "resuelto_en", "comentario")


def _huella(sesion: Session, org: UUID, tabla: str, recorte: tuple[str, ...] = ()) -> str:
    """Una huella `md5` de todas las filas de la organización (cada fila como `jsonb`, ordenadas
    por su texto) sin las columnas de `recorte`."""
    menos = "".join(f" - '{columna}'" for columna in recorte)
    return str(
        sesion.scalar(
            text(
                f"SELECT COALESCE(md5(string_agg((to_jsonb(t){menos})::text, '|' "  # noqa: S608
                f"ORDER BY (to_jsonb(t){menos})::text)), '') FROM {tabla} t "
                "WHERE organizacion_id = :o"
            ),
            {"o": org},
        )
    )


def _foto(sesion: Session, org: UUID) -> dict[str, str]:
    sesion.flush()
    foto = {tabla: _huella(sesion, org, tabla) for tabla in _TABLAS_INTACTAS}
    foto["observacion_sin_resolucion"] = _huella(
        sesion, org, "observacion", recorte=_COLUMNAS_DE_RESOLUCION
    )
    return foto


def _pendientes_resueltas(sesion: Session, org: UUID) -> dict[UUID, tuple[str, Any]]:
    sesion.flush()
    filas = sesion.execute(
        text("SELECT id, estado, comentario FROM observacion WHERE organizacion_id = :o"),
        {"o": org},
    )
    return {fila.id: (fila.estado, fila.comentario) for fila in filas}


def _resolver_en_grupos(
    sesion: Session,
    org: UUID,
    usuario_id: UUID,
    reloj: Any,
    ids: list[UUID],
    grupos: list[list[int]],
) -> dict[UUID, str]:
    """Aplica las resoluciones en bloque; las que chocan con algo ya resuelto se saltean (el
    dominio las rechazaría con `OBSERVACION_YA_RESUELTA`). Devuelve `{id: comentario}` de lo que
    quedó resuelto."""
    resueltas: dict[UUID, str] = {}
    for numero, grupo in enumerate(grupos):
        elegidas = [ids[indice] for indice in grupo]
        if any(id_ in resueltas for id_ in elegidas):
            with pytest.raises(DomainError) as error:
                casos.resolver_observaciones(
                    org,
                    sesion,
                    reloj,
                    usuario_id=usuario_id,
                    observaciones=elegidas,
                    comentario="otra vez",
                )
            assert error.value.codigo == "OBSERVACION_YA_RESUELTA"
            continue
        comentario = f"Revisado {numero}"
        casos.resolver_observaciones(
            org,
            sesion,
            reloj,
            usuario_id=usuario_id,
            observaciones=elegidas,
            comentario=comentario,
        )
        resueltas.update({id_: comentario for id_ in elegidas})
    return resueltas


def _verificar(
    sesion: Session,
    org: UUID,
    antes: dict[str, str],
    ids: list[UUID],
    resueltas: dict[UUID, str],
) -> None:
    despues = _foto(sesion, org)
    for tabla, huella in antes.items():
        assert despues[tabla] == huella, f"cambió {tabla}"  # SYN-08, INV-05, INV-12, INV-13
    estado = _pendientes_resueltas(sesion, org)
    for id_ in ids:
        if id_ in resueltas:
            assert estado[id_] == ("RESUELTA", resueltas[id_])
        else:
            assert estado[id_] == ("PENDIENTE", None)


_GRUPOS = st.lists(
    st.lists(st.integers(0, 7), min_size=1, max_size=8, unique=True), min_size=1, max_size=4
)


# Escenario: "Resolver nunca altera la operación" (ventas sin conexión)
@_PROPIEDAD
@given(st.integers(1, 3), _GRUPOS)
def test_syn08_resolver_observaciones_de_ventas_no_altera_la_operacion_ni_los_libros(
    db_session: Session, ventas: int, grupos: list[list[int]]
) -> None:
    """INV-05, INV-12, INV-13: ventas sin conexión sobre una camioneta con 1 botella (cada una
    deja `STOCK_NEGATIVO` por línea); resoluciones en bloque aleatorias."""
    entorno = EntornoAnulacion(db_session)
    ruta = Ruta(entorno, stock=1)
    for _ in range(ventas):
        _, resultado = ruta.enviar(entorno.linea(cantidad=3))
        assert resultado.estado == "ACEPTADO_CON_OBSERVACIONES"
    ids = list(
        db_session.scalars(
            text("SELECT id FROM observacion WHERE organizacion_id = :o ORDER BY id").bindparams(
                o=entorno.org
            )
        )
    )
    assert len(ids) == ventas
    grupos = [list(dict.fromkeys(i % len(ids) for i in grupo)) for grupo in grupos]
    antes = _foto(db_session, entorno.org)

    resueltas = _resolver_en_grupos(
        db_session, entorno.org, entorno.usuario_id, RELOJ_VENTA, ids, grupos
    )

    _verificar(db_session, entorno.org, antes, ids, resueltas)
    assert resueltas  # al menos un grupo se resolvió: la propiedad no es vacía


# Escenario: "Resolver nunca altera la operación" (cobranzas sin conexión)
@_PROPIEDAD
@given(st.integers(1, 3), _GRUPOS)
def test_syn08_resolver_observaciones_de_cobranzas_no_altera_la_operacion_ni_los_libros(
    db_session: Session, cobranzas: int, grupos: list[list[int]]
) -> None:
    """INV-05, INV-13: cobranzas sin conexión con un medio desactivado después de abrir la
    jornada (`MEDIO_INACTIVO`); resoluciones en bloque aleatorias."""
    entorno = EntornoCobranza(db_session)
    billetera = entorno.crear_medio("Billetera", requiere_referencia=False)
    jornada = entorno.crear_jornada()
    db_session.commit()
    entorno.desactivar_medio(billetera)
    for _ in range(cobranzas):
        contenido = entorno.contenido(
            cobranza_id=str(uuid4()),
            importe="10000.00",
            medios=entorno.medios((billetera, "10000.00", None)),
        )
        (resultado,) = sync_service.procesar_lote(
            entorno.sesion,
            RELOJ_COBRANZA,
            organizacion_id=entorno.org,
            usuario_id=entorno.usuario_id,
            dispositivo_id=entorno.dispositivo_id,
            items=[
                ItemLote(
                    operation_id=uuid4(),
                    tipo="COBRANZA_REGISTRAR",
                    version=1,
                    modo="OFFLINE",
                    usuario_id=entorno.usuario_id,
                    dispositivo_id=entorno.dispositivo_id,
                    occurred_at=MOMENTO_COBRANZA,
                    secuencia=1,
                    app_version="1.0.0",
                    contenido=contenido,
                    jornada_id=jornada,
                )
            ],
        )
        assert resultado.estado == "ACEPTADO_CON_OBSERVACIONES"
    ids = list(
        db_session.scalars(
            text("SELECT id FROM observacion WHERE organizacion_id = :o ORDER BY id").bindparams(
                o=entorno.org
            )
        )
    )
    assert len(ids) == cobranzas
    grupos = [list(dict.fromkeys(i % len(ids) for i in grupo)) for grupo in grupos]
    antes = _foto(db_session, entorno.org)

    resueltas = _resolver_en_grupos(
        db_session, entorno.org, entorno.usuario_id, RELOJ_COBRANZA, ids, grupos
    )

    _verificar(db_session, entorno.org, antes, ids, resueltas)
    assert resueltas
    assert entorno.saldo() == Decimal(150000) - Decimal(10000) * cobranzas
