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
from collections.abc import Callable, Collection
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select, tuple_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.proveedores.domain.compras import codificar_cursor, decodificar_cursor
from app.modules.proveedores.domain.errores import (
    CuitDuplicadoError,
    NombreDuplicadoError,
)
from app.modules.proveedores.models import (
    Compra,
    CompraLinea,
    CostoInformado,
    PagoProveedor,
    PagoProveedorMedio,
    Proveedor,
)

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
    computa_credito_fiscal: bool
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
            computa_credito_fiscal=datos.computa_credito_fiscal,
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


def contar_vigentes_por_regla_de_iva(
    organizacion_id: UUID, fecha: date, sesion: Session
) -> tuple[int, int]:
    """11b, D10: `(con_credito_fiscal, sin_credito_fiscal)`, la cantidad de costos informados
    vigentes a `fecha` -- el último de cada producto y presentación (D4: `vigencia_desde
    DESC, creado_en DESC, id DESC`) con `vigencia_desde <= fecha` -- según la regla de IVA con
    que se registraron. Una única consulta `DISTINCT ON` agrupada en la base (`CLAUDE.md` §4:
    nunca trayendo las filas a Python para contarlas)."""
    ultimos = (
        select(CostoInformado.computa_credito_fiscal)
        .distinct(CostoInformado.producto_id, CostoInformado.presentacion_id)
        .where(
            CostoInformado.organizacion_id == organizacion_id,
            CostoInformado.vigencia_desde <= fecha,
        )
        .order_by(
            CostoInformado.producto_id,
            CostoInformado.presentacion_id,
            CostoInformado.vigencia_desde.desc(),
            CostoInformado.creado_en.desc(),
            CostoInformado.id.desc(),
        )
        .subquery()
    )
    filas = sesion.execute(
        select(ultimos.c.computa_credito_fiscal, func.count()).group_by(
            ultimos.c.computa_credito_fiscal
        )
    ).all()
    por_regla = {bool(computa): int(cantidad) for computa, cantidad in filas}
    return por_regla.get(True, 0), por_regla.get(False, 0)


def obtener_vigentes_de_productos(
    organizacion_id: UUID, producto_ids: Collection[UUID], fecha: date, sesion: Session
) -> list[CostoInformado]:
    """CST-03/D4 por lote (change 13, tarea 6.2): el costo vigente a `fecha` de cada producto
    de `producto_ids` que lo tenga, en UNA consulta `DISTINCT ON (producto_id)` con el mismo
    orden que `obtener_vigente` (`vigencia_desde DESC, creado_en DESC, id DESC`). Un producto
    sin costo vigente no aparece."""
    if not producto_ids:
        return []
    consulta = (
        select(CostoInformado)
        .distinct(CostoInformado.producto_id)
        .where(
            CostoInformado.organizacion_id == organizacion_id,
            CostoInformado.producto_id.in_(producto_ids),
            CostoInformado.vigencia_desde <= fecha,
        )
        .order_by(
            CostoInformado.producto_id,
            CostoInformado.vigencia_desde.desc(),
            CostoInformado.creado_en.desc(),
            CostoInformado.id.desc(),
        )
    )
    return list(sesion.scalars(consulta).all())


def productos_con_costos_distintos_por_presentacion(
    organizacion_id: UUID, producto_ids: Collection[UUID], fecha: date, sesion: Session
) -> set[UUID]:
    """D2: los productos de `producto_ids` cuyo último costo informado a `fecha` de cada
    presentación (mismo orden de desempate) difiere por unidad base entre dos presentaciones.
    Una sola consulta agrupada en la base (`CLAUDE.md` §4)."""
    if not producto_ids:
        return set()
    ultimos = (
        select(CostoInformado.producto_id, CostoInformado.costo_base)
        .distinct(CostoInformado.producto_id, CostoInformado.presentacion_id)
        .where(
            CostoInformado.organizacion_id == organizacion_id,
            CostoInformado.producto_id.in_(producto_ids),
            CostoInformado.vigencia_desde <= fecha,
        )
        .order_by(
            CostoInformado.producto_id,
            CostoInformado.presentacion_id,
            CostoInformado.vigencia_desde.desc(),
            CostoInformado.creado_en.desc(),
            CostoInformado.id.desc(),
        )
        .subquery()
    )
    consulta = (
        select(ultimos.c.producto_id)
        .group_by(ultimos.c.producto_id)
        .having(func.count(func.distinct(ultimos.c.costo_base)) > 1)
    )
    return set(sesion.scalars(consulta).all())


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


def buscar_proveedores_por_nombre(
    organizacion_id: UUID, nombre: str, sesion: Session
) -> list[Proveedor]:
    """Proveedores de la organización con ese nombre, sin distinguir mayúsculas ni
    espacios al borde, activos o no (change 10, `design.md` D4)."""
    clave = nombre.strip().lower()
    if not clave:
        return []
    consulta = (
        select(Proveedor)
        .where(
            Proveedor.organizacion_id == organizacion_id,
            func.lower(func.btrim(Proveedor.nombre)) == clave,
        )
        .order_by(Proveedor.nombre, Proveedor.id)
    )
    return list(sesion.scalars(consulta).all())


# --- compras (change 11, `design.md` D12) --------------------------------------------


@dataclass(frozen=True)
class DatosDeCompra:
    """Una compra por insertar: todo calculado y validado por el servicio."""

    id: UUID
    proveedor_id: UUID
    ubicacion_id: UUID
    fecha: date
    condicion: str
    total_neto: Decimal
    total_factura: Decimal
    numero_comprobante: str | None
    observacion: str | None
    operation_id: UUID
    usuario_id: UUID
    dispositivo_id: UUID
    occurred_at: datetime
    registered_at: datetime


@dataclass(frozen=True)
class DatosDeLineaDeCompra:
    id: UUID
    orden: int
    producto_id: UUID
    presentacion_id: UUID
    unidades_presentacion: int
    cantidad: Decimal
    cantidad_base: int
    valor_presentacion: Decimal
    incluye_iva: bool
    computa_credito_fiscal: bool
    bonificacion: Decimal
    alicuota_aplicada: Decimal
    costo_base: Decimal
    importe_neto: Decimal


def insertar_compra(
    organizacion_id: UUID,
    sesion: Session,
    *,
    compra: DatosDeCompra,
    lineas: list[DatosDeLineaDeCompra],
) -> tuple[Compra, list[CompraLinea]]:
    """Inserta la compra `CONFIRMADA` y sus líneas, en la transacción de quien llama
    (INV-01). Una compra es inmutable salvo su anulación (TR-06): no hay `actualizar`
    de importes ni `borrar` en este módulo."""
    fila = Compra(
        id=compra.id,
        organizacion_id=organizacion_id,
        proveedor_id=compra.proveedor_id,
        ubicacion_id=compra.ubicacion_id,
        fecha=compra.fecha,
        condicion=compra.condicion,
        total_neto=compra.total_neto,
        total_factura=compra.total_factura,
        numero_comprobante=compra.numero_comprobante,
        observacion=compra.observacion,
        estado="CONFIRMADA",
        anulacion_motivo_id=None,
        anulada_en=None,
        anulada_por_id=None,
        operation_id=compra.operation_id,
        usuario_id=compra.usuario_id,
        dispositivo_id=compra.dispositivo_id,
        occurred_at=compra.occurred_at,
        registered_at=compra.registered_at,
    )
    filas_de_linea = [
        CompraLinea(
            id=datos.id,
            organizacion_id=organizacion_id,
            compra_id=compra.id,
            orden=datos.orden,
            producto_id=datos.producto_id,
            presentacion_id=datos.presentacion_id,
            unidades_presentacion=datos.unidades_presentacion,
            cantidad=datos.cantidad,
            cantidad_base=datos.cantidad_base,
            valor_presentacion=datos.valor_presentacion,
            incluye_iva=datos.incluye_iva,
            computa_credito_fiscal=datos.computa_credito_fiscal,
            bonificacion=datos.bonificacion,
            alicuota_aplicada=datos.alicuota_aplicada,
            costo_base=datos.costo_base,
            importe_neto=datos.importe_neto,
        )
        for datos in lineas
    ]

    def _mutar() -> None:
        sesion.add(fila)
        sesion.flush()  # la compra antes que sus líneas (FK compuesta)
        for linea in filas_de_linea:
            sesion.add(linea)

    guardar_con_traduccion_de_integridad(organizacion_id, sesion, _mutar)
    return fila, filas_de_linea


def existe_linea_para_presentacion(
    organizacion_id: UUID, presentacion_id: UUID, sesion: Session
) -> bool:
    """INV-18, ADR-023: verificador de uso que `proveedores/service.py` registra en
    `catalogo_service.registrar_verificador_uso` -- `True` si ALGUNA línea de compra,
    de una compra confirmada o anulada, referencia esa presentación."""
    consulta = (
        select(func.count())
        .select_from(CompraLinea)
        .where(
            CompraLinea.organizacion_id == organizacion_id,
            CompraLinea.presentacion_id == presentacion_id,
        )
    )
    return int(sesion.execute(consulta).scalar_one()) > 0


@dataclass(frozen=True)
class DatosDePago:
    """El pago a insertar. `origen` es `COMPRA` (el pago de una compra de contado, D2) o
    `INDEPENDIENTE` (un pago suelto, PAG-02); `compra_id` es `None` en el independiente,
    que no se imputa a ninguna compra. La observación es opcional (D6) y el pago nace
    siempre `CONFIRMADA`: no se inserta un pago ya anulado."""

    id: UUID
    proveedor_id: UUID
    fecha: date
    importe: Decimal
    origen: str
    compra_id: UUID | None
    observacion: str | None
    operation_id: UUID
    usuario_id: UUID
    dispositivo_id: UUID
    occurred_at: datetime
    registered_at: datetime


@dataclass(frozen=True)
class DatosDeMedioDePago:
    medio_pago_id: UUID
    importe: Decimal
    referencia: str | None


def insertar_pago(
    organizacion_id: UUID,
    sesion: Session,
    *,
    pago: DatosDePago,
    medios: list[DatosDeMedioDePago],
) -> PagoProveedor:
    """Inserta el pago `CONFIRMADA` de origen `COMPRA` o `INDEPENDIENTE` y sus medios, en la
    transacción de quien llama (INV-01, INV-08: la suma de los medios la valida el servicio).
    La compra, si la hay, ya debe estar insertada (FK compuesta)."""
    fila = PagoProveedor(
        id=pago.id,
        organizacion_id=organizacion_id,
        proveedor_id=pago.proveedor_id,
        fecha=pago.fecha,
        importe=pago.importe,
        estado="CONFIRMADA",
        origen=pago.origen,
        compra_id=pago.compra_id,
        observacion=pago.observacion,
        anulado_en=None,
        anulado_por_id=None,
        anulacion_motivo_id=None,
        operation_id=pago.operation_id,
        usuario_id=pago.usuario_id,
        dispositivo_id=pago.dispositivo_id,
        occurred_at=pago.occurred_at,
        registered_at=pago.registered_at,
    )
    filas_de_medio = [
        PagoProveedorMedio(
            organizacion_id=organizacion_id,
            pago_id=pago.id,
            medio_pago_id=medio.medio_pago_id,
            importe=medio.importe,
            referencia=medio.referencia,
        )
        for medio in medios
    ]

    def _mutar() -> None:
        sesion.add(fila)
        sesion.flush()  # el pago antes que sus medios (FK compuesta)
        for medio in filas_de_medio:
            sesion.add(medio)

    guardar_con_traduccion_de_integridad(organizacion_id, sesion, _mutar)
    return fila


def obtener_compra_para_actualizar(
    organizacion_id: UUID, compra_id: UUID, sesion: Session
) -> Compra | None:
    """`SELECT ... FOR UPDATE` de la compra (`02` §7.3, `design.md` D12 y "Orden de
    bloqueo"): serializa dos anulaciones simultáneas. `populate_existing` para que el
    segundo en llegar vea el `estado` que dejó el primero y no el de una instancia que
    la sesión ya tuviera cargada."""
    consulta = (
        select(Compra)
        .where(Compra.organizacion_id == organizacion_id, Compra.id == compra_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return sesion.scalars(consulta).one_or_none()


def listar_lineas_de_compra(
    organizacion_id: UUID, compra_id: UUID, sesion: Session
) -> list[CompraLinea]:
    """Las líneas de la compra en el orden en que se cargaron."""
    consulta = (
        select(CompraLinea)
        .where(CompraLinea.organizacion_id == organizacion_id, CompraLinea.compra_id == compra_id)
        .order_by(CompraLinea.orden)
    )
    return list(sesion.scalars(consulta).all())


def obtener_pago_de_compra(
    organizacion_id: UUID, compra_id: UUID, sesion: Session
) -> PagoProveedor | None:
    """El pago de contado de la compra (a lo sumo uno: `ux_pago_proveedor__compra`)."""
    consulta = (
        select(PagoProveedor)
        .where(
            PagoProveedor.organizacion_id == organizacion_id, PagoProveedor.compra_id == compra_id
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return sesion.scalars(consulta).one_or_none()


def obtener_pago(organizacion_id: UUID, pago_id: UUID, sesion: Session) -> PagoProveedor | None:
    """El pago por id, sin bloquear, o `None` si no existe en la organización (INV-21).

    Es el primer paso de `anular_pago` (`design.md` D10): la anulación necesita saber el
    `origen` del pago ANTES de decidir qué fila bloquear, y tomar el bloqueo equivocado
    rompe el orden que evita el interbloqueo con `anular_compra`.
    """
    consulta = select(PagoProveedor).where(
        PagoProveedor.organizacion_id == organizacion_id, PagoProveedor.id == pago_id
    )
    return sesion.scalars(consulta).one_or_none()


def obtener_pago_para_actualizar(
    organizacion_id: UUID, pago_id: UUID, sesion: Session
) -> PagoProveedor | None:
    """`SELECT ... FOR UPDATE` del pago (`02` §7.3, `design.md` D10): serializa dos
    anulaciones simultáneas del mismo pago. `populate_existing` para que el segundo en
    llegar vea el `estado` que dejó el primero y no el de una instancia que la sesión ya
    tuviera cargada.

    Para un pago de origen `COMPRA` el llamador bloquea antes la fila de la compra (D10),
    con `obtener_compra_para_actualizar`, y recién después esta: es el mismo orden que
    usa `anular_compra`, así que ninguna de las dos se queda esperando la otra.
    """
    consulta = (
        select(PagoProveedor)
        .where(PagoProveedor.organizacion_id == organizacion_id, PagoProveedor.id == pago_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return sesion.scalars(consulta).one_or_none()


def marcar_compra_anulada(
    organizacion_id: UUID,
    sesion: Session,
    *,
    compra: Compra,
    motivo_id: UUID,
    anulada_en: datetime,
    anulada_por_id: UUID,
) -> None:
    """Pasa la compra a `ANULADA` (`design.md` D12). Solo toca las columnas de estado y
    anulación, las únicas con `UPDATE` para `app_runtime` (INV-05)."""
    del (
        organizacion_id
    )  # la fila ya viene filtrada y bloqueada por `obtener_compra_para_actualizar`.

    def _mutar() -> None:
        compra.estado = "ANULADA"
        compra.anulacion_motivo_id = motivo_id
        compra.anulada_en = anulada_en
        compra.anulada_por_id = anulada_por_id

    guardar_con_traduccion_de_integridad(compra.organizacion_id, sesion, _mutar)


def marcar_pago_anulado(
    organizacion_id: UUID,
    sesion: Session,
    *,
    pago: PagoProveedor,
    motivo_id: UUID,
    anulado_en: datetime,
    anulado_por_id: UUID,
) -> None:
    """Pasa el pago de contado a `ANULADA` cuando se devuelve (`design.md` D3, D12)."""

    def _mutar() -> None:
        pago.estado = "ANULADA"
        pago.anulacion_motivo_id = motivo_id
        pago.anulado_en = anulado_en
        pago.anulado_por_id = anulado_por_id

    guardar_con_traduccion_de_integridad(organizacion_id, sesion, _mutar)


def listar_compras_paginado(
    organizacion_id: UUID,
    sesion: Session,
    *,
    limite: int,
    cursor: str | None,
    proveedor_id: UUID | None,
    estado: str | None,
    desde: date | None,
    hasta: date | None,
    numero_comprobante: str | None,
) -> tuple[list[tuple[Compra, str]], str | None]:
    """Compras de la organización de la más reciente a la más vieja, por cursor
    `(fecha, id)` descendente (índice `(organizacion_id, fecha DESC, id)`, D12). Cada
    fila trae el nombre del proveedor. `desde` y `hasta` son fechas de comprobante
    inclusivas. Devuelve `(filas, cursor_siguiente)`."""
    consulta = (
        select(Compra, Proveedor.nombre)
        .join(
            Proveedor,
            (Proveedor.organizacion_id == Compra.organizacion_id)
            & (Proveedor.id == Compra.proveedor_id),
        )
        .where(Compra.organizacion_id == organizacion_id)
    )
    if proveedor_id is not None:
        consulta = consulta.where(Compra.proveedor_id == proveedor_id)
    if estado is not None:
        consulta = consulta.where(Compra.estado == estado)
    if desde is not None:
        consulta = consulta.where(Compra.fecha >= desde)
    if hasta is not None:
        consulta = consulta.where(Compra.fecha <= hasta)
    if numero_comprobante is not None:
        consulta = consulta.where(Compra.numero_comprobante.ilike(f"%{numero_comprobante}%"))
    if cursor is not None:
        fecha_cursor, id_cursor = decodificar_cursor(cursor)
        consulta = consulta.where(tuple_(Compra.fecha, Compra.id) < (fecha_cursor, id_cursor))
    consulta = consulta.order_by(Compra.fecha.desc(), Compra.id.desc()).limit(limite + 1)

    filas = [(compra, nombre) for compra, nombre in sesion.execute(consulta).all()]
    if len(filas) > limite:
        pagina = filas[:limite]
        ultima = pagina[-1][0]
        return pagina, codificar_cursor(ultima.fecha, ultima.id)
    return filas, None


def obtener_compra(
    organizacion_id: UUID, compra_id: UUID, sesion: Session
) -> tuple[Compra, str] | None:
    """La compra con el nombre de su proveedor, sin bloquear, o `None` si no existe en
    la organización (INV-21)."""
    consulta = (
        select(Compra, Proveedor.nombre)
        .join(
            Proveedor,
            (Proveedor.organizacion_id == Compra.organizacion_id)
            & (Proveedor.id == Compra.proveedor_id),
        )
        .where(Compra.organizacion_id == organizacion_id, Compra.id == compra_id)
    )
    fila = sesion.execute(consulta).one_or_none()
    return None if fila is None else (fila[0], fila[1])


def listar_medios_de_pago(
    organizacion_id: UUID, pago_id: UUID, sesion: Session
) -> list[PagoProveedorMedio]:
    """Los medios del pago, del de mayor importe al de menor."""
    consulta = (
        select(PagoProveedorMedio)
        .where(
            PagoProveedorMedio.organizacion_id == organizacion_id,
            PagoProveedorMedio.pago_id == pago_id,
        )
        .order_by(PagoProveedorMedio.importe.desc(), PagoProveedorMedio.id)
    )
    return list(sesion.scalars(consulta).all())


def obtener_pago_de_compra_sin_bloquear(
    organizacion_id: UUID, compra_id: UUID, sesion: Session
) -> PagoProveedor | None:
    """El pago de contado de la compra, para lectura."""
    consulta = select(PagoProveedor).where(
        PagoProveedor.organizacion_id == organizacion_id, PagoProveedor.compra_id == compra_id
    )
    return sesion.scalars(consulta).one_or_none()


# --- pagos a proveedor: lecturas (change 12, tarea 6.1; PAG-01, `design.md` D11) ----------


def listar_pagos_paginado(
    organizacion_id: UUID,
    sesion: Session,
    *,
    limite: int,
    cursor: str | None,
    proveedor_id: UUID | None,
    estado: str | None,
    origen: str | None,
    desde: date | None,
    hasta: date | None,
) -> tuple[list[tuple[PagoProveedor, str]], str | None]:
    """Pagos de la organización de la más reciente a la más vieja, por cursor
    `(fecha, id)` descendente (índices `ix_pago_proveedor__fecha` y
    `ix_pago_proveedor__proveedor_fecha`, `design.md` D9 punto 4). Cada fila trae el
    nombre del proveedor. `desde` y `hasta` son fechas de pago inclusivas. Devuelve
    `(filas, cursor_siguiente)`.

    Incluye los pagos de origen `COMPRA` (los de contado): el listado es de todos los
    pagos de la organización, con su `compra_id` para el enlace (D11)."""
    consulta = (
        select(PagoProveedor, Proveedor.nombre)
        .join(
            Proveedor,
            (Proveedor.organizacion_id == PagoProveedor.organizacion_id)
            & (Proveedor.id == PagoProveedor.proveedor_id),
        )
        .where(PagoProveedor.organizacion_id == organizacion_id)
    )
    if proveedor_id is not None:
        consulta = consulta.where(PagoProveedor.proveedor_id == proveedor_id)
    if estado is not None:
        consulta = consulta.where(PagoProveedor.estado == estado)
    if origen is not None:
        consulta = consulta.where(PagoProveedor.origen == origen)
    if desde is not None:
        consulta = consulta.where(PagoProveedor.fecha >= desde)
    if hasta is not None:
        consulta = consulta.where(PagoProveedor.fecha <= hasta)
    if cursor is not None:
        fecha_cursor, id_cursor = decodificar_cursor(cursor)
        consulta = consulta.where(
            tuple_(PagoProveedor.fecha, PagoProveedor.id) < (fecha_cursor, id_cursor)
        )
    consulta = consulta.order_by(PagoProveedor.fecha.desc(), PagoProveedor.id.desc()).limit(
        limite + 1
    )

    filas = [(pago, nombre) for pago, nombre in sesion.execute(consulta).all()]
    if len(filas) > limite:
        pagina = filas[:limite]
        ultima = pagina[-1][0]
        return pagina, codificar_cursor(ultima.fecha, ultima.id)
    return filas, None


def obtener_pago_para_detalle(
    organizacion_id: UUID, pago_id: UUID, sesion: Session
) -> tuple[PagoProveedor, str, str | None] | None:
    """`(pago, nombre del proveedor, estado de su compra)`, o `None` si el pago no existe
    en la organización (INV-21). El estado de la compra es `None` para un pago
    `INDEPENDIENTE`; en el detalle es lo que permite no ofrecer "Anular" mientras la
    compra sigue vigente (CMP-05, `design.md` D2)."""
    consulta = (
        select(PagoProveedor, Proveedor.nombre, Compra.estado)
        .join(
            Proveedor,
            (Proveedor.organizacion_id == PagoProveedor.organizacion_id)
            & (Proveedor.id == PagoProveedor.proveedor_id),
        )
        .outerjoin(
            Compra,
            (Compra.organizacion_id == PagoProveedor.organizacion_id)
            & (Compra.id == PagoProveedor.compra_id),
        )
        .where(PagoProveedor.organizacion_id == organizacion_id, PagoProveedor.id == pago_id)
    )
    fila = sesion.execute(consulta).one_or_none()
    return None if fila is None else (fila[0], fila[1], fila[2])


def nombres_de_proveedores(
    organizacion_id: UUID, proveedor_ids: Collection[UUID], sesion: Session
) -> dict[UUID, str]:
    """`{id: nombre}` de los proveedores de la organización entre `proveedor_ids`, en una
    consulta (los de otra organización, o inexistentes, no aparecen)."""
    if not proveedor_ids:
        return {}
    consulta = select(Proveedor.id, Proveedor.nombre).where(
        Proveedor.organizacion_id == organizacion_id, Proveedor.id.in_(proveedor_ids)
    )
    return {fila.id: fila.nombre for fila in sesion.execute(consulta)}
