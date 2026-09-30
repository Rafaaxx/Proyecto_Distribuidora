"""Acceso a datos de `cuentas_corrientes` (`docs/02-arquitectura.md` §7, §8,
`CLAUDE.md` §4). Mismo contrato no negociable que `clientes/repository.py`: toda
función pública recibe `organizacion_id` como primer parámetro obligatorio y lo
usa para filtrar toda consulta
(`tests/unit/test_repositorios_organizacion_obligatoria.py`).

Ninguna suma se hace en Python (`CLAUDE.md` §4, CC-04, CC-07, INV-13): el saldo
nuevo (`saldo + efecto`), la suma del libro, el saldo anterior de un período, el
acumulado del estado de cuenta (`SUM(...) OVER (ORDER BY occurred_at, id)`) y la
consulta de consistencia se calculan con SQL. El `efecto` de un movimiento lo
decide el dominio (`+importe` o `-importe`) y llega como dato.

Ninguna función borra ni actualiza el libro: `cuenta_movimiento` es de solo
inserción y el usuario de aplicación no tiene `UPDATE` ni `DELETE` sobre ella
(CC-06, INV-05). `saldo_cuenta` sí se actualiza (`02` §7.2).

Traducción de errores de la base a errores de dominio (`design.md` D6, D7,
Risks): la FK compuesta que valida que la entidad exista en la organización
(`fk_cuenta_movimiento__cliente`/`__proveedor`, `fk_saldo_cuenta__cliente`/
`__proveedor`) se traduce a `RecursoNoEncontradoError` (404, INV-21, SEG-07), y
un `numeric field overflow` del saldo acumulado a `SaldoFueraDeRangoError`. El
`flush` ocurre dentro de un `SAVEPOINT` (`begin_nested`) para que el error no
deje la sesión inutilizable y el bus pueda revertir la transacción entera.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import case, func, literal, select, tuple_, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import DataError, IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.sql import ColumnElement

from app.modules.cuentas_corrientes.domain.errores import (
    RecursoNoEncontradoError,
    SaldoFueraDeRangoError,
)
from app.modules.cuentas_corrientes.domain.estado_de_cuenta import (
    DiferenciaDeSaldo,
    LineaDeEstadoDeCuenta,
    codificar_cursor,
    decodificar_cursor,
    limite_efectivo,
)
from app.modules.cuentas_corrientes.models import CuentaMovimiento, SaldoCuenta

# Las cuatro FK que garantizan que la entidad existe en la organización y es
# del tipo que dice `cuenta_tipo` (D6-A).
_FK_DE_ENTIDAD = (
    "fk_cuenta_movimiento__cliente",
    "fk_cuenta_movimiento__proveedor",
    "fk_saldo_cuenta__cliente",
    "fk_saldo_cuenta__proveedor",
)


def _con_traduccion[T](sesion: Session, operacion: Callable[[], T]) -> T:
    """Ejecuta `operacion` dentro de un `SAVEPOINT` y traduce los errores de la
    base que tienen significado de negocio (D6, D7, Risks)."""
    try:
        with sesion.begin_nested():
            return operacion()
    except IntegrityError as error:
        mensaje = str(getattr(error, "orig", error))
        if any(fk in mensaje for fk in _FK_DE_ENTIDAD):
            raise RecursoNoEncontradoError(
                "El cliente o el proveedor de la cuenta no existe en esta organización."
            ) from error
        raise
    except DataError as error:
        mensaje = str(getattr(error, "orig", error))
        if "numeric field overflow" in mensaje:
            raise SaldoFueraDeRangoError(
                "El saldo resultante no entra en el máximo que admite la cuenta."
            ) from error
        raise


def _efecto_sql() -> ColumnElement[Decimal]:
    """`+importe` si el movimiento aumenta, `-importe` si reduce (CC-04), en SQL."""
    return case(
        (CuentaMovimiento.sentido == "AUMENTA", CuentaMovimiento.importe),
        else_=-CuentaMovimiento.importe,
    )


def _de_la_cuenta(
    organizacion_id: UUID, cuenta_tipo: str, entidad_id: UUID
) -> list[ColumnElement[bool]]:
    return [
        CuentaMovimiento.organizacion_id == organizacion_id,
        CuentaMovimiento.cuenta_tipo == cuenta_tipo,
        CuentaMovimiento.entidad_id == entidad_id,
    ]


# --- fila de saldo: creación perezosa y bloqueo (D10) ------------------------


def asegurar_saldo(
    organizacion_id: UUID,
    sesion: Session,
    *,
    cuenta_tipo: str,
    entidad_id: UUID,
    momento: datetime,
) -> None:
    """`INSERT ... ON CONFLICT DO NOTHING` de la fila de saldo en cero (D10).

    La carrera de la primera fila la resuelve la clave primaria: si dos
    transacciones la crean a la vez, la segunda espera a la primera y no hace
    nada. La FK de D6 valida acá, con un bloqueo liviano sobre la fila del
    cliente o del proveedor, que la entidad existe en la organización."""
    sentencia = (
        pg_insert(SaldoCuenta)
        .values(
            organizacion_id=organizacion_id,
            cuenta_tipo=cuenta_tipo,
            entidad_id=entidad_id,
            saldo=Decimal("0.00"),
            actualizado_en=momento,
        )
        .on_conflict_do_nothing(index_elements=["organizacion_id", "cuenta_tipo", "entidad_id"])
    )
    _con_traduccion(sesion, lambda: sesion.execute(sentencia))


def bloquear_saldo(
    organizacion_id: UUID, sesion: Session, *, cuenta_tipo: str, entidad_id: UUID
) -> SaldoCuenta | None:
    """`SELECT ... FOR UPDATE` de la fila de saldo (`02` §7.3, ADR-015).
    `populate_existing` para que el valor devuelto sea el de la base y no el de
    una instancia que la sesión ya tuviera cargada."""
    consulta = (
        select(SaldoCuenta)
        .where(
            SaldoCuenta.organizacion_id == organizacion_id,
            SaldoCuenta.cuenta_tipo == cuenta_tipo,
            SaldoCuenta.entidad_id == entidad_id,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return sesion.scalars(consulta).one_or_none()


def obtener_saldo(
    organizacion_id: UUID, sesion: Session, *, cuenta_tipo: str, entidad_id: UUID
) -> Decimal | None:
    """Saldo materializado sin bloquear, o `None` si la cuenta nunca tuvo un
    movimiento (no tiene fila)."""
    consulta = select(SaldoCuenta.saldo).where(
        SaldoCuenta.organizacion_id == organizacion_id,
        SaldoCuenta.cuenta_tipo == cuenta_tipo,
        SaldoCuenta.entidad_id == entidad_id,
    )
    return sesion.scalar(consulta)


def actualizar_saldo(
    organizacion_id: UUID,
    sesion: Session,
    *,
    cuenta_tipo: str,
    entidad_id: UUID,
    efecto: Decimal,
    momento: datetime,
) -> Decimal:
    """`UPDATE saldo_cuenta SET saldo = saldo + :efecto ... RETURNING saldo`: la
    suma la hace la base. Devuelve el saldo nuevo."""
    sentencia = (
        update(SaldoCuenta)
        .where(
            SaldoCuenta.organizacion_id == organizacion_id,
            SaldoCuenta.cuenta_tipo == cuenta_tipo,
            SaldoCuenta.entidad_id == entidad_id,
        )
        .values(saldo=SaldoCuenta.saldo + efecto, actualizado_en=momento)
        .returning(SaldoCuenta.saldo)
        .execution_options(synchronize_session=False)
    )
    return _con_traduccion(sesion, lambda: sesion.execute(sentencia).scalar_one())


# --- libro -------------------------------------------------------------------


def insertar_movimiento(
    organizacion_id: UUID,
    sesion: Session,
    *,
    movimiento_id: UUID,
    cuenta_tipo: str,
    entidad_id: UUID,
    tipo: str,
    sentido: str,
    importe: Decimal,
    origen_tipo: str,
    origen_id: UUID,
    occurred_at: datetime,
    registered_at: datetime,
    usuario_id: UUID,
    dispositivo_id: UUID,
    operation_id: UUID,
) -> CuentaMovimiento:
    """Inserta un movimiento ya validado por `domain/`. `cliente_id` y
    `proveedor_id` las calcula PostgreSQL (D6-A): no se escriben acá."""
    movimiento = CuentaMovimiento(
        id=movimiento_id,
        organizacion_id=organizacion_id,
        cuenta_tipo=cuenta_tipo,
        entidad_id=entidad_id,
        tipo=tipo,
        sentido=sentido,
        importe=importe,
        origen_tipo=origen_tipo,
        origen_id=origen_id,
        occurred_at=occurred_at,
        registered_at=registered_at,
        usuario_id=usuario_id,
        dispositivo_id=dispositivo_id,
        operation_id=operation_id,
    )
    _con_traduccion(sesion, lambda: sesion.add(movimiento))
    return movimiento


def existe_movimiento(
    organizacion_id: UUID,
    sesion: Session,
    *,
    cuenta_tipo: str,
    entidad_id: UUID,
    tipo: str | None = None,
    excluyendo_tipo: str | None = None,
) -> bool:
    """¿La cuenta tiene algún movimiento? Sin filtro cuenta cualquiera (CLI-06,
    D8); con `tipo`, solo de ese tipo; con `excluyendo_tipo`, solo de otro tipo
    (D3: "movimientos de otro tipo" que `SALDO_INICIAL`)."""
    condiciones = _de_la_cuenta(organizacion_id, cuenta_tipo, entidad_id)
    if tipo is not None:
        condiciones.append(CuentaMovimiento.tipo == tipo)
    if excluyendo_tipo is not None:
        condiciones.append(CuentaMovimiento.tipo != excluyendo_tipo)
    consulta = select(literal(1)).where(*condiciones).limit(1)
    return sesion.scalar(consulta) is not None


def suma_del_libro(
    organizacion_id: UUID, sesion: Session, *, cuenta_tipo: str, entidad_id: UUID
) -> Decimal:
    """Suma de los movimientos que aumentan menos los que reducen, calculada en
    SQL (CC-04, INV-13). Cero si la cuenta no tiene movimientos."""
    consulta = select(func.coalesce(func.sum(_efecto_sql()), Decimal("0.00"))).where(
        *_de_la_cuenta(organizacion_id, cuenta_tipo, entidad_id)
    )
    resultado = sesion.scalar(consulta)
    return Decimal("0.00") if resultado is None else resultado


def saldo_anterior(
    organizacion_id: UUID,
    sesion: Session,
    *,
    cuenta_tipo: str,
    entidad_id: UUID,
    antes_de: datetime,
) -> Decimal:
    """Suma SQL de lo anterior al instante `antes_de` (D9: el saldo con el que
    arranca el período)."""
    consulta = select(func.coalesce(func.sum(_efecto_sql()), Decimal("0.00"))).where(
        *_de_la_cuenta(organizacion_id, cuenta_tipo, entidad_id),
        CuentaMovimiento.occurred_at < antes_de,
    )
    resultado = sesion.scalar(consulta)
    return Decimal("0.00") if resultado is None else resultado


# --- estado de cuenta (CC-07, D9) ---------------------------------------------


def estado_de_cuenta(
    organizacion_id: UUID,
    sesion: Session,
    *,
    cuenta_tipo: str,
    entidad_id: UUID,
    desde: datetime | None,
    hasta: datetime | None,
    cursor: str | None,
    limite: int | None,
) -> tuple[list[LineaDeEstadoDeCuenta], str | None]:
    """Movimientos de la cuenta en orden `(occurred_at, id)` con su saldo
    acumulado, paginados por cursor `(occurred_at, id)` (D9).

    El acumulado se calcula con `SUM(...) OVER (ORDER BY occurred_at, id)` sobre
    la cuenta COMPLETA en una subconsulta, y el período (`desde` inclusive,
    `hasta` exclusive) y el cursor se filtran después, por fuera: cada fila trae
    el saldo real de la cuenta y no uno que arranca de cero en cada página. Usa
    el índice `(organizacion_id, cuenta_tipo, entidad_id, occurred_at, id)`.

    Pide una fila de más para saber si hay otra página; `cursor_siguiente` es
    `None` en la última."""
    limite_pagina = limite_efectivo(limite)
    acumulado = (
        func.sum(_efecto_sql())
        .over(order_by=(CuentaMovimiento.occurred_at, CuentaMovimiento.id))
        .label("saldo_acumulado")
    )
    con_acumulado = (
        select(
            CuentaMovimiento.id,
            CuentaMovimiento.tipo,
            CuentaMovimiento.sentido,
            CuentaMovimiento.importe,
            CuentaMovimiento.origen_tipo,
            CuentaMovimiento.origen_id,
            CuentaMovimiento.occurred_at,
            CuentaMovimiento.registered_at,
            CuentaMovimiento.usuario_id,
            CuentaMovimiento.operation_id,
            acumulado,
        )
        .where(*_de_la_cuenta(organizacion_id, cuenta_tipo, entidad_id))
        .subquery()
    )
    consulta = select(con_acumulado)
    if desde is not None:
        consulta = consulta.where(con_acumulado.c.occurred_at >= desde)
    if hasta is not None:
        consulta = consulta.where(con_acumulado.c.occurred_at < hasta)
    if cursor is not None:
        momento_cursor, id_cursor = decodificar_cursor(cursor)
        consulta = consulta.where(
            tuple_(con_acumulado.c.occurred_at, con_acumulado.c.id) > (momento_cursor, id_cursor)
        )
    consulta = consulta.order_by(con_acumulado.c.occurred_at, con_acumulado.c.id).limit(
        limite_pagina + 1
    )

    filas = list(sesion.execute(consulta).all())
    hay_mas = len(filas) > limite_pagina
    pagina = filas[:limite_pagina]
    lineas = [
        LineaDeEstadoDeCuenta(
            id=fila.id,
            tipo=fila.tipo,
            sentido=fila.sentido,
            importe=fila.importe,
            origen_tipo=fila.origen_tipo,
            origen_id=fila.origen_id,
            occurred_at=fila.occurred_at,
            registered_at=fila.registered_at,
            usuario_id=fila.usuario_id,
            operation_id=fila.operation_id,
            saldo_acumulado=fila.saldo_acumulado,
        )
        for fila in pagina
    ]
    cursor_siguiente = (
        codificar_cursor(lineas[-1].occurred_at, lineas[-1].id) if hay_mas and lineas else None
    )
    return lineas, cursor_siguiente


# --- consistencia saldo vs libro (INV-13, `02` §7.6) ---------------------------


def verificar_consistencia(organizacion_id: UUID, sesion: Session) -> list[DiferenciaDeSaldo]:
    """Cuentas cuyo saldo materializado no coincide con la suma de su libro,
    calculado con SQL. Una cuenta con movimientos y sin fila de saldo también
    es una diferencia (su saldo materializado cuenta como cero). Solo lee: no
    corrige nada (ADR-015); la tarea diaria que la ejecuta es del change 28."""
    libro = (
        select(
            CuentaMovimiento.cuenta_tipo.label("cuenta_tipo"),
            CuentaMovimiento.entidad_id.label("entidad_id"),
            func.sum(_efecto_sql()).label("suma"),
        )
        .where(CuentaMovimiento.organizacion_id == organizacion_id)
        .group_by(CuentaMovimiento.cuenta_tipo, CuentaMovimiento.entidad_id)
        .subquery()
    )
    saldos = (
        select(
            SaldoCuenta.cuenta_tipo.label("cuenta_tipo"),
            SaldoCuenta.entidad_id.label("entidad_id"),
            SaldoCuenta.saldo.label("saldo"),
        )
        .where(SaldoCuenta.organizacion_id == organizacion_id)
        .subquery()
    )
    cuenta_tipo = func.coalesce(saldos.c.cuenta_tipo, libro.c.cuenta_tipo)
    entidad_id = func.coalesce(saldos.c.entidad_id, libro.c.entidad_id)
    materializado = func.coalesce(saldos.c.saldo, Decimal("0.00"))
    suma = func.coalesce(libro.c.suma, Decimal("0.00"))
    consulta = (
        select(
            cuenta_tipo.label("cuenta_tipo"),
            entidad_id.label("entidad_id"),
            materializado.label("saldo_materializado"),
            suma.label("suma_del_libro"),
        )
        .select_from(
            saldos.outerjoin(
                libro,
                (saldos.c.cuenta_tipo == libro.c.cuenta_tipo)
                & (saldos.c.entidad_id == libro.c.entidad_id),
                full=True,
            )
        )
        .where(materializado != suma)
        .order_by(cuenta_tipo, entidad_id)
    )
    return [
        DiferenciaDeSaldo(
            cuenta_tipo=fila.cuenta_tipo,
            entidad_id=fila.entidad_id,
            saldo_materializado=fila.saldo_materializado,
            suma_del_libro=fila.suma_del_libro,
        )
        for fila in sesion.execute(consulta).all()
    ]


FUNCIONES_SIN_ORGANIZACION_ID: frozenset[str] = frozenset()
"""Sin excepción (mismo criterio que `clientes.repository`): `cuentas_corrientes`
no tiene ningún catálogo global propio -- toda función pública recibe
`organizacion_id` primero."""
