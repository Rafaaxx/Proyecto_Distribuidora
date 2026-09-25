"""Acceso a datos de `proveedores` (`docs/02-arquitectura.md` §8,
`CLAUDE.md` §4). Mismo contrato no negociable que `catalogo/repository.py`
(tarea 7.1, change 05 tarea 6.1): todo método público recibe
`organizacion_id` como primer parámetro obligatorio y lo usa para filtrar
toda consulta (`tests/unit/test_repositorios_organizacion_obligatoria.py`).

`guardar_con_traduccion_de_integridad` reusa la lección 6.2 del change 05:
el `flush` ocurre dentro de un `SAVEPOINT` (`begin_nested`) para que un
`IntegrityError` no deje la sesión en `DEACTIVE` -- se traduce por nombre
de restricción a un error de dominio con código estable.
"""

from __future__ import annotations

import base64
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select, tuple_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.proveedores.domain.errores import (
    CuitDuplicadoError,
    NombreDuplicadoError,
)
from app.modules.proveedores.models import CostoInformado, Proveedor

LIMITE_PAGINA_MAXIMO = 100
LIMITE_PAGINA_DEFAULT = 50


def guardar_con_traduccion_de_integridad(
    organizacion_id: UUID, sesion: Session, mutar: Callable[[], None]
) -> None:
    """Mismo mecanismo que `catalogo.repository.guardar_con_traduccion_de_
    integridad` (lección 6.2 del 05): `mutar` DEBE ejecutar la mutación
    (`sesion.add(...)` o las asignaciones de atributos) DENTRO de este
    `with`, nunca antes de llamarlo."""
    del organizacion_id  # No filtra nada: la mutación ya trae su organización.
    try:
        with sesion.begin_nested():
            mutar()
    except IntegrityError as error:
        mensaje = str(getattr(error, "orig", error))
        if "ux_proveedor__nombre" in mensaje:
            raise NombreDuplicadoError(
                "Ya existe un proveedor con ese nombre en esta organización."
            ) from error
        if "ux_proveedor__cuit" in mensaje:
            raise CuitDuplicadoError(
                "Ya existe un proveedor con ese CUIT en esta organización."
            ) from error
        raise


# --- proveedor (tarea 7.1) --------------------------------------------------


def crear_proveedor(
    organizacion_id: UUID,
    sesion: Session,
    *,
    proveedor_id: UUID,
    nombre: str,
    cuit: str | None,
    contacto: str | None,
    telefono: str | None,
    email: str | None,
    activo: bool,
    momento: datetime,
    actualizado_por_id: UUID | None = None,
) -> Proveedor:
    proveedor = Proveedor(
        id=proveedor_id,
        organizacion_id=organizacion_id,
        nombre=nombre,
        cuit=cuit,
        contacto=contacto,
        telefono=telefono,
        email=email,
        activo=activo,
        creado_en=momento,
        actualizado_en=momento,
        actualizado_por_id=actualizado_por_id,
    )
    guardar_con_traduccion_de_integridad(organizacion_id, sesion, lambda: sesion.add(proveedor))
    return proveedor


def obtener_proveedor_por_id(
    organizacion_id: UUID, proveedor_id: UUID, sesion: Session
) -> Proveedor | None:
    proveedor = sesion.get(Proveedor, proveedor_id)
    if proveedor is None or proveedor.organizacion_id != organizacion_id:
        return None
    return proveedor


def obtener_proveedor_por_id_para_actualizar(
    organizacion_id: UUID, proveedor_id: UUID, sesion: Session
) -> Proveedor | None:
    """`SELECT ... FOR UPDATE` (`design.md` D14): `PROVEEDOR_MODIFICAR`
    bloquea la fila antes de decidir/escribir, para serializar con
    cualquier lectura `FOR SHARE` concurrente (D9, D3/D5 vía
    `COSTO_INFORMAR`)."""
    consulta = (
        select(Proveedor)
        .where(Proveedor.organizacion_id == organizacion_id, Proveedor.id == proveedor_id)
        .with_for_update()
    )
    return sesion.scalars(consulta).one_or_none()


def obtener_proveedor_por_id_para_compartir(
    organizacion_id: UUID, proveedor_id: UUID, sesion: Session
) -> Proveedor | None:
    """`SELECT ... FOR SHARE` (`design.md` D14): usada por el puerto D9
    (`catalogo` valida existencia/actividad) y por `COSTO_INFORMAR` (D3),
    para que una desactivación concurrente (`FOR UPDATE`) se serialice con
    estas lecturas en vez de correr una carrera silenciosa."""
    consulta = (
        select(Proveedor)
        .where(Proveedor.organizacion_id == organizacion_id, Proveedor.id == proveedor_id)
        .with_for_update(read=True)
    )
    return sesion.scalars(consulta).one_or_none()


def actualizar_proveedor(
    organizacion_id: UUID,
    sesion: Session,
    *,
    proveedor_id: UUID,
    nombre: str,
    cuit: str | None,
    contacto: str | None,
    telefono: str | None,
    email: str | None,
    activo: bool,
    momento: datetime,
    actualizado_por_id: UUID | None = None,
) -> Proveedor | None:
    proveedor = obtener_proveedor_por_id(organizacion_id, proveedor_id, sesion)
    if proveedor is None:
        return None

    def _mutar() -> None:
        proveedor.nombre = nombre
        proveedor.cuit = cuit
        proveedor.contacto = contacto
        proveedor.telefono = telefono
        proveedor.email = email
        proveedor.activo = activo
        proveedor.actualizado_en = momento
        proveedor.actualizado_por_id = actualizado_por_id

    guardar_con_traduccion_de_integridad(organizacion_id, sesion, _mutar)
    return proveedor


def _codificar_cursor(valor: str) -> str:
    return base64.urlsafe_b64encode(valor.encode("utf-8")).decode("ascii")


def _decodificar_cursor(cursor: str) -> str:
    return base64.urlsafe_b64decode(cursor.encode("ascii")).decode("utf-8")


def _digitos(texto: str) -> str:
    return "".join(caracter for caracter in texto if caracter.isdigit())


def listar_proveedores_paginado(
    organizacion_id: UUID,
    sesion: Session,
    *,
    limite: int = LIMITE_PAGINA_DEFAULT,
    cursor: str | None = None,
    texto: str | None = None,
    activo: bool | None = None,
) -> tuple[list[Proveedor], str | None]:
    """Paginación por cursor (`design.md` D13, tarea 7.2): ordenado por
    `nombre` (único por organización, D7), límite máximo
    `LIMITE_PAGINA_MAXIMO`.

    `texto` busca por nombre O CUIT (contrato-api.md P5, aprobado
    2026-09-24): un `texto` con al menos un dígito también compara contra
    el CUIT normalizado a solo dígitos (`Proveedor.cuit` ya se guarda sin
    guiones ni espacios, D7), así que un fragmento como `"20-123"` iguala
    el CUIT `"20123456789"` sin que el usuario tenga que tipear el CUIT
    completo ni sin guiones."""
    limite_efectivo = min(max(limite, 1), LIMITE_PAGINA_MAXIMO)

    consulta = select(Proveedor).where(Proveedor.organizacion_id == organizacion_id)
    if cursor is not None:
        consulta = consulta.where(Proveedor.nombre > _decodificar_cursor(cursor))
    if texto is not None:
        patron_nombre = f"%{texto}%"
        digitos = _digitos(texto)
        if digitos:
            patron_cuit = f"%{digitos}%"
            consulta = consulta.where(
                Proveedor.nombre.ilike(patron_nombre) | Proveedor.cuit.ilike(patron_cuit)
            )
        else:
            consulta = consulta.where(Proveedor.nombre.ilike(patron_nombre))
    if activo is not None:
        consulta = consulta.where(Proveedor.activo.is_(activo))
    consulta = consulta.order_by(Proveedor.nombre).limit(limite_efectivo + 1)

    filas = list(sesion.scalars(consulta).all())
    if len(filas) > limite_efectivo:
        pagina = filas[:limite_efectivo]
        cursor_siguiente: str | None = _codificar_cursor(pagina[-1].nombre)
    else:
        pagina = filas
        cursor_siguiente = None
    return pagina, cursor_siguiente


def listar_opciones_de_proveedores(
    organizacion_id: UUID,
    sesion: Session,
    *,
    limite: int = LIMITE_PAGINA_DEFAULT,
    cursor: str | None = None,
) -> tuple[list[Proveedor], str | None]:
    """`GET /proveedores/opciones` (`design.md` D8, contrato-api.md P2,
    aprobado 2026-09-24): solo proveedores activos, paginados por cursor de
    `nombre` (mismo mecanismo que `listar_proveedores_paginado`) -- el
    llamador (`service.py`) se queda solo con `id`/`nombre` al armar el
    esquema de salida."""
    limite_efectivo = min(max(limite, 1), LIMITE_PAGINA_MAXIMO)

    consulta = select(Proveedor).where(
        Proveedor.organizacion_id == organizacion_id, Proveedor.activo.is_(True)
    )
    if cursor is not None:
        consulta = consulta.where(Proveedor.nombre > _decodificar_cursor(cursor))
    consulta = consulta.order_by(Proveedor.nombre).limit(limite_efectivo + 1)

    filas = list(sesion.scalars(consulta).all())
    if len(filas) > limite_efectivo:
        pagina = filas[:limite_efectivo]
        cursor_siguiente: str | None = _codificar_cursor(pagina[-1].nombre)
    else:
        pagina = filas
        cursor_siguiente = None
    return pagina, cursor_siguiente


# --- costo_informado (tarea 7.3) --------------------------------------------


@dataclass(frozen=True, slots=True)
class DatosCostoInformado:
    """Un costo ya validado y calculado, listo para insertar
    (`design.md` D12, D15). Construido por `proveedores/service.py`
    (tarea 8.3): esta capa no calcula ni valida, solo inserta."""

    id: UUID
    proveedor_id: UUID
    producto_id: UUID
    presentacion_id: UUID
    valor: Decimal
    incluye_iva: bool
    bonificacion: Decimal
    alicuota_aplicada: Decimal
    costo_base: Decimal
    vigencia_desde: date
    observacion: str | None
    operation_id: UUID
    usuario_id: UUID
    momento: datetime


def insertar_costos(
    organizacion_id: UUID, sesion: Session, *, costos: list[DatosCostoInformado]
) -> list[CostoInformado]:
    """Inserción en lote, todo o nada (INV-01): el llamador (servicio)
    valida y calcula TODO antes de invocar esta función una única vez, así
    que si algo falla antes no se llegó a construir ninguna fila. `costo_
    informado` es de solo inserción (CST-03): no hay `actualizar`/`borrar`
    en este módulo."""
    filas = [
        CostoInformado(
            id=datos.id,
            organizacion_id=organizacion_id,
            proveedor_id=datos.proveedor_id,
            producto_id=datos.producto_id,
            presentacion_id=datos.presentacion_id,
            valor=datos.valor,
            incluye_iva=datos.incluye_iva,
            bonificacion=datos.bonificacion,
            alicuota_aplicada=datos.alicuota_aplicada,
            costo_base=datos.costo_base,
            vigencia_desde=datos.vigencia_desde,
            observacion=datos.observacion,
            operation_id=datos.operation_id,
            usuario_id=datos.usuario_id,
            creado_en=datos.momento,
        )
        for datos in costos
    ]

    def _mutar() -> None:
        for fila in filas:
            sesion.add(fila)

    guardar_con_traduccion_de_integridad(organizacion_id, sesion, _mutar)
    return filas


def obtener_vigente(
    organizacion_id: UUID, producto_id: UUID, fecha: date, sesion: Session
) -> CostoInformado | None:
    """CST-03/D4: el costo vigente de un producto para `fecha`, resuelto
    con SQL (`ORDER BY ... LIMIT 1` sobre `ix_costo_informado__producto_
    vigencia`), nunca trayendo filas a Python (`CLAUDE.md` §4). Mismo orden
    que `proveedores/domain/vigencia.py::elegir_vigente` -- comparados por
    una propiedad Hypothesis (tarea 7.3)."""
    consulta = (
        select(CostoInformado)
        .where(
            CostoInformado.organizacion_id == organizacion_id,
            CostoInformado.producto_id == producto_id,
            CostoInformado.vigencia_desde <= fecha,
        )
        .order_by(
            CostoInformado.vigencia_desde.desc(),
            CostoInformado.creado_en.desc(),
            CostoInformado.id.desc(),
        )
        .limit(1)
    )
    return sesion.scalars(consulta).one_or_none()


def obtener_ultimo_por_presentacion(
    organizacion_id: UUID, producto_id: UUID, fecha: date, sesion: Session
) -> list[CostoInformado]:
    """P11 (`contrato-api.md`, aprobado en la verificación manual 13.5,
    opción B): el último costo informado (D4: `vigencia_desde DESC,
    creado_en DESC, id DESC`) de CADA presentación del producto con al
    menos un costo con `vigencia_desde <= fecha` -- una presentación sin
    costo se omite. Una única consulta `DISTINCT ON (presentacion_id)`
    (`CLAUDE.md` §4: nunca trayendo el historial completo a Python); el
    orden devuelto es por `presentacion_id` (lo exige `DISTINCT ON`, que
    debe empezar el `ORDER BY` con las columnas distintas) -- `api.py`
    reordena la lista pequeña resultante por `presentacion_nombre` una vez
    resueltos los nombres para mostrar, mismo patrón que `proveedor_
    nombre`/`presentacion_nombre` (P4)."""
    consulta = (
        select(CostoInformado)
        .distinct(CostoInformado.presentacion_id)
        .where(
            CostoInformado.organizacion_id == organizacion_id,
            CostoInformado.producto_id == producto_id,
            CostoInformado.vigencia_desde <= fecha,
        )
        .order_by(
            CostoInformado.presentacion_id,
            CostoInformado.vigencia_desde.desc(),
            CostoInformado.creado_en.desc(),
            CostoInformado.id.desc(),
        )
    )
    return list(sesion.scalars(consulta).all())


def _codificar_cursor_historial(vigencia_desde: date, creado_en: datetime, id_: UUID) -> str:
    valor = f"{vigencia_desde.isoformat()}|{creado_en.isoformat()}|{id_}"
    return base64.urlsafe_b64encode(valor.encode("utf-8")).decode("ascii")


def _decodificar_cursor_historial(cursor: str) -> tuple[date, datetime, UUID]:
    valor = base64.urlsafe_b64decode(cursor.encode("ascii")).decode("utf-8")
    vigencia_str, creado_str, id_str = valor.split("|")
    return date.fromisoformat(vigencia_str), datetime.fromisoformat(creado_str), UUID(id_str)


def listar_historial_de_producto(
    organizacion_id: UUID,
    producto_id: UUID,
    sesion: Session,
    *,
    limite: int = LIMITE_PAGINA_DEFAULT,
    cursor: str | None = None,
) -> tuple[list[CostoInformado], str | None]:
    """Historial completo (vigencias pasadas y futuras, D12) por cursor
    `(vigencia_desde, creado_en, id)` descendente -- mismo orden que
    `obtener_vigente` (D4), para que "vigente a hoy" sea siempre la primera
    fila de la primera página."""
    limite_efectivo = min(max(limite, 1), LIMITE_PAGINA_MAXIMO)

    consulta = select(CostoInformado).where(
        CostoInformado.organizacion_id == organizacion_id,
        CostoInformado.producto_id == producto_id,
    )
    if cursor is not None:
        vigencia_desde, creado_en, id_ = _decodificar_cursor_historial(cursor)
        consulta = consulta.where(
            tuple_(CostoInformado.vigencia_desde, CostoInformado.creado_en, CostoInformado.id)
            < (vigencia_desde, creado_en, id_)
        )
    consulta = consulta.order_by(
        CostoInformado.vigencia_desde.desc(),
        CostoInformado.creado_en.desc(),
        CostoInformado.id.desc(),
    ).limit(limite_efectivo + 1)

    filas = list(sesion.scalars(consulta).all())
    if len(filas) > limite_efectivo:
        pagina = filas[:limite_efectivo]
        ultima = pagina[-1]
        cursor_siguiente: str | None = _codificar_cursor_historial(
            ultima.vigencia_desde, ultima.creado_en, ultima.id
        )
    else:
        pagina = filas
        cursor_siguiente = None
    return pagina, cursor_siguiente


def existe_costo_para_presentacion(
    organizacion_id: UUID, presentacion_id: UUID, sesion: Session
) -> bool:
    """D1: verificador de uso (ADR-023) que `proveedores/service.py`
    registra en `catalogo_service.registrar_verificador_uso` (tarea 8.5) --
    `True` si ALGÚN costo informado referencia esa presentación."""
    consulta = (
        select(func.count())
        .select_from(CostoInformado)
        .where(
            CostoInformado.organizacion_id == organizacion_id,
            CostoInformado.presentacion_id == presentacion_id,
        )
    )
    return int(sesion.execute(consulta).scalar_one()) > 0


FUNCIONES_SIN_ORGANIZACION_ID: frozenset[str] = frozenset()
"""Sin excepción (mismo criterio que `catalogo.repository.FUNCIONES_SIN_
ORGANIZACION_ID`, tarea 7.1): `proveedores` no tiene ningún catálogo global
propio -- toda función pública recibe `organizacion_id` primero."""
