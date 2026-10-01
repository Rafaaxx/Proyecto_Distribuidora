"""Acceso a datos de `catalogo` (`docs/02-arquitectura.md` §8, `CLAUDE.md`
§4). Mismo contrato no negociable que `identidad/repository.py`: todo
método público recibe `organizacion_id` como primer parámetro obligatorio
y lo usa para filtrar toda consulta (`tests/unit/
test_repositorios_organizacion_obligatoria.py`, tarea 6.1).

Las unicidades se validan primero en el servicio (mensaje claro) y la base
es la garantía final (`design.md` D6): `guardar_con_traduccion_de_integridad`
hace el `flush` dentro de un `SAVEPOINT` (`begin_nested`, que
`SesionSinCommit` delega tal cual) y traduce `IntegrityError` por nombre de
restricción a un error de dominio con código estable, para que dos altas
concurrentes terminen en un error de dominio y no en un 500 (tarea 6.2).
"""

from __future__ import annotations

import base64
from collections.abc import Callable
from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.catalogo.domain.errores import (
    CodigoDuplicadoError,
    NombreDuplicadoError,
    RecursoNoEncontradoError,
    ReferenciaInvalidaError,
)
from app.modules.catalogo.models import Categoria, Marca, Presentacion, Producto

LIMITE_PAGINA_MAXIMO = 100
LIMITE_PAGINA_DEFAULT = 50


def guardar_con_traduccion_de_integridad(
    organizacion_id: UUID, sesion: Session, mutar: Callable[[], None]
) -> None:
    """Ejecuta `mutar` (el `sesion.add(...)` de un alta, o las asignaciones
    de atributos de una modificación) dentro de un `SAVEPOINT`
    (`begin_nested`, que `SesionSinCommit` delega tal cual) y traduce
    `IntegrityError` por nombre de restricción a un error de dominio con
    código estable (`design.md` D6, tarea 6.2), para que dos altas
    concurrentes terminen en un error de dominio y no en un 500.

    `organizacion_id` no se usa para filtrar acá (no hay nada que leer): se
    declara como primer parámetro solo para cumplir el mismo contrato de
    firma que el resto del repositorio, verificado por
    `test_repositorios_organizacion_obligatoria.py` -- la función igual
    solo puede fallar sobre lo que `mutar` le agrega a `sesion` para ESA
    organización.

    `mutar` DEBE ejecutar la mutación (el `add`, o la asignación de
    atributos) DENTRO de este `with`, no antes de llamar a esta función
    (descubrimiento al implementar esta tarea, confirmado empíricamente
    contra PostgreSQL real): si la mutación ya sucedió afuera y acá solo se
    hace `sesion.flush()`, una segunda llamada a esta función que SÍ falla
    dentro del mismo `with sesion.begin_nested():` deja la sesión completa
    en estado `DEACTIVE` -- una lectura posterior revienta con
    `PendingRollbackError` aunque la traducción a error de dominio haya
    funcionado. Con la mutación DENTRO del `with` (el flush ocurre de forma
    implícita al liberar el SAVEPOINT), el error queda acotado al SAVEPOINT
    y la sesión sigue utilizable para la siguiente operación."""
    del organizacion_id  # No filtra nada: ver docstring.
    try:
        with sesion.begin_nested():
            mutar()
    except IntegrityError as error:
        mensaje = str(getattr(error, "orig", error))
        if "ux_categoria__nombre" in mensaje or "ux_marca__nombre" in mensaje:
            raise NombreDuplicadoError(
                "Ya existe una categoría o marca con ese nombre en esta organización."
            ) from error
        if "ux_producto__codigo" in mensaje:
            raise CodigoDuplicadoError(
                "Ya existe un producto con ese código en esta organización."
            ) from error
        if (
            "ux_presentacion__referencia" in mensaje
            or "ck_presentacion__referencia_venta" in mensaje
        ):
            raise ReferenciaInvalidaError(
                "El producto ya tiene una presentación de referencia, o la "
                "referencia debe usarse en venta."
            ) from error
        if "fk_producto__proveedor" in mensaje:
            # Change 06, tarea 8.1: existencia y pertenencia del proveedor a
            # la organización ya las garantiza la FK compuesta (`design.md`
            # D9-A) -- un proveedor inexistente (o de otra organización)
            # responde 404, nunca un 500 (SEG-07/INV-21).
            raise RecursoNoEncontradoError(
                "El proveedor indicado no existe en esta organización."
            ) from error
        raise


# --- categoria -------------------------------------------------------------


def crear_categoria(
    organizacion_id: UUID,
    sesion: Session,
    *,
    categoria_id: UUID,
    nombre: str,
    activo: bool,
    momento: datetime,
    actualizado_por_id: UUID | None = None,
) -> Categoria:
    categoria = Categoria(
        id=categoria_id,
        organizacion_id=organizacion_id,
        nombre=nombre,
        activo=activo,
        creado_en=momento,
        actualizado_en=momento,
        actualizado_por_id=actualizado_por_id,
    )
    guardar_con_traduccion_de_integridad(organizacion_id, sesion, lambda: sesion.add(categoria))
    return categoria


def obtener_categoria_por_id(
    organizacion_id: UUID, categoria_id: UUID, sesion: Session
) -> Categoria | None:
    categoria = sesion.get(Categoria, categoria_id)
    if categoria is None or categoria.organizacion_id != organizacion_id:
        return None
    return categoria


def listar_categorias(
    organizacion_id: UUID, sesion: Session, *, solo_activas: bool = False
) -> list[Categoria]:
    consulta = select(Categoria).where(Categoria.organizacion_id == organizacion_id)
    if solo_activas:
        consulta = consulta.where(Categoria.activo.is_(True))
    consulta = consulta.order_by(Categoria.nombre)
    return list(sesion.scalars(consulta).all())


def actualizar_categoria(
    organizacion_id: UUID,
    sesion: Session,
    *,
    categoria_id: UUID,
    nombre: str,
    activo: bool,
    momento: datetime,
    actualizado_por_id: UUID | None = None,
) -> Categoria | None:
    categoria = obtener_categoria_por_id(organizacion_id, categoria_id, sesion)
    if categoria is None:
        return None

    def _mutar() -> None:
        categoria.nombre = nombre
        categoria.activo = activo
        categoria.actualizado_en = momento
        categoria.actualizado_por_id = actualizado_por_id

    guardar_con_traduccion_de_integridad(organizacion_id, sesion, _mutar)
    return categoria


def existen_productos_activos_en_categoria(
    organizacion_id: UUID, categoria_id: UUID, sesion: Session
) -> bool:
    """D11: usado para rechazar la desactivación de una categoría con
    productos activos (`CATEGORIA_CON_PRODUCTOS_ACTIVOS`). Cuenta en la
    base, nunca trae filas a Python (`CLAUDE.md` §4)."""
    consulta = (
        select(func.count())
        .select_from(Producto)
        .where(
            Producto.organizacion_id == organizacion_id,
            Producto.categoria_id == categoria_id,
            Producto.activo.is_(True),
        )
    )
    return int(sesion.execute(consulta).scalar_one()) > 0


def existen_productos_activos_de_proveedor(
    organizacion_id: UUID, proveedor_id: UUID, sesion: Session
) -> bool:
    """Change 06, tarea 8.1 (`design.md` D5, ADR-026): usado por
    `proveedores/service.py` (vía este `service.py`, `CLAUDE.md` §4 -- un
    módulo usa a otro solo por su `service.py`) para rechazar la
    desactivación de un proveedor con productos activos
    (`PROVEEDOR_CON_PRODUCTOS_ACTIVOS`). Cuenta en la base, nunca trae
    filas a Python."""
    consulta = (
        select(func.count())
        .select_from(Producto)
        .where(
            Producto.organizacion_id == organizacion_id,
            Producto.proveedor_id == proveedor_id,
            Producto.activo.is_(True),
        )
    )
    return int(sesion.execute(consulta).scalar_one()) > 0


# --- marca -------------------------------------------------------------


def crear_marca(
    organizacion_id: UUID,
    sesion: Session,
    *,
    marca_id: UUID,
    nombre: str,
    activo: bool,
    momento: datetime,
    actualizado_por_id: UUID | None = None,
) -> Marca:
    marca = Marca(
        id=marca_id,
        organizacion_id=organizacion_id,
        nombre=nombre,
        activo=activo,
        creado_en=momento,
        actualizado_en=momento,
        actualizado_por_id=actualizado_por_id,
    )
    guardar_con_traduccion_de_integridad(organizacion_id, sesion, lambda: sesion.add(marca))
    return marca


def obtener_marca_por_id(organizacion_id: UUID, marca_id: UUID, sesion: Session) -> Marca | None:
    marca = sesion.get(Marca, marca_id)
    if marca is None or marca.organizacion_id != organizacion_id:
        return None
    return marca


def listar_marcas(
    organizacion_id: UUID, sesion: Session, *, solo_activas: bool = False
) -> list[Marca]:
    consulta = select(Marca).where(Marca.organizacion_id == organizacion_id)
    if solo_activas:
        consulta = consulta.where(Marca.activo.is_(True))
    consulta = consulta.order_by(Marca.nombre)
    return list(sesion.scalars(consulta).all())


def actualizar_marca(
    organizacion_id: UUID,
    sesion: Session,
    *,
    marca_id: UUID,
    nombre: str,
    activo: bool,
    momento: datetime,
    actualizado_por_id: UUID | None = None,
) -> Marca | None:
    marca = obtener_marca_por_id(organizacion_id, marca_id, sesion)
    if marca is None:
        return None

    def _mutar() -> None:
        marca.nombre = nombre
        marca.activo = activo
        marca.actualizado_en = momento
        marca.actualizado_por_id = actualizado_por_id

    guardar_con_traduccion_de_integridad(organizacion_id, sesion, _mutar)
    return marca


# --- producto ------------------------------------------------------------


def crear_producto(
    organizacion_id: UUID,
    sesion: Session,
    *,
    producto_id: UUID,
    codigo: str,
    nombre: str,
    categoria_id: UUID,
    marca_id: UUID | None,
    proveedor_id: UUID,
    unidad_base: str,
    alicuota_id: UUID,
    activo: bool,
    momento: datetime,
    actualizado_por_id: UUID | None = None,
) -> Producto:
    producto = Producto(
        id=producto_id,
        organizacion_id=organizacion_id,
        codigo=codigo,
        nombre=nombre,
        categoria_id=categoria_id,
        marca_id=marca_id,
        proveedor_id=proveedor_id,
        unidad_base=unidad_base,
        alicuota_id=alicuota_id,
        activo=activo,
        creado_en=momento,
        actualizado_en=momento,
        actualizado_por_id=actualizado_por_id,
    )
    guardar_con_traduccion_de_integridad(organizacion_id, sesion, lambda: sesion.add(producto))
    return producto


def obtener_producto_por_id(
    organizacion_id: UUID, producto_id: UUID, sesion: Session
) -> Producto | None:
    producto = sesion.get(Producto, producto_id)
    if producto is None or producto.organizacion_id != organizacion_id:
        return None
    return producto


def obtener_producto_por_id_para_actualizar(
    organizacion_id: UUID, producto_id: UUID, sesion: Session
) -> Producto | None:
    """`SELECT ... FOR UPDATE` de la fila de `producto` (`design.md` D5):
    serializa los cambios de presentaciones/referencia de un mismo
    producto. `producto` no es tabla de saldo (`02` §7.3): este bloqueo no
    entra en ningún orden de bloqueo entre tablas, es autocontenido."""
    consulta = (
        select(Producto)
        .where(Producto.organizacion_id == organizacion_id, Producto.id == producto_id)
        .with_for_update()
    )
    return sesion.scalars(consulta).one_or_none()


def obtener_producto_por_id_para_compartir(
    organizacion_id: UUID, producto_id: UUID, sesion: Session
) -> Producto | None:
    """`SELECT ... FOR SHARE` (change 06, `design.md` D14): usada por
    `proveedores` (`COSTO_INFORMAR`) para leer el producto sin bloquear en
    exclusiva, serializando contra una modificación concurrente
    (`FOR UPDATE`, D5 del 05) en vez de correr una carrera silenciosa."""
    consulta = (
        select(Producto)
        .where(Producto.organizacion_id == organizacion_id, Producto.id == producto_id)
        .with_for_update(read=True)
    )
    return sesion.scalars(consulta).one_or_none()


def actualizar_producto(
    organizacion_id: UUID,
    sesion: Session,
    *,
    producto_id: UUID,
    codigo: str,
    nombre: str,
    categoria_id: UUID,
    marca_id: UUID | None,
    proveedor_id: UUID,
    unidad_base: str,
    alicuota_id: UUID,
    activo: bool,
    momento: datetime,
    actualizado_por_id: UUID | None = None,
) -> Producto | None:
    producto = obtener_producto_por_id(organizacion_id, producto_id, sesion)
    if producto is None:
        return None

    def _mutar() -> None:
        producto.codigo = codigo
        producto.nombre = nombre
        producto.categoria_id = categoria_id
        producto.marca_id = marca_id
        producto.proveedor_id = proveedor_id
        producto.unidad_base = unidad_base
        producto.alicuota_id = alicuota_id
        producto.activo = activo
        producto.actualizado_en = momento
        producto.actualizado_por_id = actualizado_por_id

    guardar_con_traduccion_de_integridad(organizacion_id, sesion, _mutar)
    return producto


def _codificar_cursor(valor: str) -> str:
    return base64.urlsafe_b64encode(valor.encode("utf-8")).decode("ascii")


def _decodificar_cursor(cursor: str) -> str:
    return base64.urlsafe_b64decode(cursor.encode("ascii")).decode("utf-8")


def listar_productos_paginado(
    organizacion_id: UUID,
    sesion: Session,
    *,
    limite: int = LIMITE_PAGINA_DEFAULT,
    cursor: str | None = None,
    texto: str | None = None,
    categoria_id: UUID | None = None,
    marca_id: UUID | None = None,
    activo: bool | None = None,
) -> tuple[list[Producto], str | None]:
    """Paginación por cursor (`02` §11): ordenado por `codigo` (único por
    organización, CAT-01 -- una clave estable para el cursor), con límite
    máximo por página (`LIMITE_PAGINA_MAXIMO`). Devuelve `(productos,
    cursor_siguiente)`; `cursor_siguiente` es `None` en la última página."""
    limite_efectivo = min(max(limite, 1), LIMITE_PAGINA_MAXIMO)

    consulta = select(Producto).where(Producto.organizacion_id == organizacion_id)
    if cursor is not None:
        consulta = consulta.where(Producto.codigo > _decodificar_cursor(cursor))
    if texto is not None:
        patron = f"%{texto}%"
        consulta = consulta.where(Producto.codigo.ilike(patron) | Producto.nombre.ilike(patron))
    if categoria_id is not None:
        consulta = consulta.where(Producto.categoria_id == categoria_id)
    if marca_id is not None:
        consulta = consulta.where(Producto.marca_id == marca_id)
    if activo is not None:
        consulta = consulta.where(Producto.activo.is_(activo))
    consulta = consulta.order_by(Producto.codigo).limit(limite_efectivo + 1)

    filas = list(sesion.scalars(consulta).all())
    if len(filas) > limite_efectivo:
        pagina = filas[:limite_efectivo]
        cursor_siguiente: str | None = _codificar_cursor(pagina[-1].codigo)
    else:
        pagina = filas
        cursor_siguiente = None
    return pagina, cursor_siguiente


def listar_categorias_paginado(
    organizacion_id: UUID,
    sesion: Session,
    *,
    limite: int = LIMITE_PAGINA_DEFAULT,
    cursor: str | None = None,
    solo_activas: bool = False,
) -> tuple[list[Categoria], str | None]:
    limite_efectivo = min(max(limite, 1), LIMITE_PAGINA_MAXIMO)
    consulta = select(Categoria).where(Categoria.organizacion_id == organizacion_id)
    if solo_activas:
        consulta = consulta.where(Categoria.activo.is_(True))
    if cursor is not None:
        consulta = consulta.where(Categoria.nombre > _decodificar_cursor(cursor))
    consulta = consulta.order_by(Categoria.nombre).limit(limite_efectivo + 1)

    filas = list(sesion.scalars(consulta).all())
    if len(filas) > limite_efectivo:
        pagina = filas[:limite_efectivo]
        cursor_siguiente: str | None = _codificar_cursor(pagina[-1].nombre)
    else:
        pagina = filas
        cursor_siguiente = None
    return pagina, cursor_siguiente


def listar_marcas_paginado(
    organizacion_id: UUID,
    sesion: Session,
    *,
    limite: int = LIMITE_PAGINA_DEFAULT,
    cursor: str | None = None,
    solo_activas: bool = False,
) -> tuple[list[Marca], str | None]:
    limite_efectivo = min(max(limite, 1), LIMITE_PAGINA_MAXIMO)
    consulta = select(Marca).where(Marca.organizacion_id == organizacion_id)
    if solo_activas:
        consulta = consulta.where(Marca.activo.is_(True))
    if cursor is not None:
        consulta = consulta.where(Marca.nombre > _decodificar_cursor(cursor))
    consulta = consulta.order_by(Marca.nombre).limit(limite_efectivo + 1)

    filas = list(sesion.scalars(consulta).all())
    if len(filas) > limite_efectivo:
        pagina = filas[:limite_efectivo]
        cursor_siguiente: str | None = _codificar_cursor(pagina[-1].nombre)
    else:
        pagina = filas
        cursor_siguiente = None
    return pagina, cursor_siguiente


# --- presentacion ----------------------------------------------------------


def crear_presentacion(
    organizacion_id: UUID,
    sesion: Session,
    *,
    presentacion_id: UUID,
    producto_id: UUID,
    nombre: str,
    unidades_base: int,
    usar_en_venta: bool,
    usar_en_compra: bool,
    es_referencia: bool,
    activo: bool,
    momento: datetime,
    actualizado_por_id: UUID | None = None,
) -> Presentacion:
    presentacion = Presentacion(
        id=presentacion_id,
        organizacion_id=organizacion_id,
        producto_id=producto_id,
        nombre=nombre,
        unidades_base=unidades_base,
        usar_en_venta=usar_en_venta,
        usar_en_compra=usar_en_compra,
        es_referencia=es_referencia,
        activo=activo,
        creado_en=momento,
        actualizado_en=momento,
        actualizado_por_id=actualizado_por_id,
    )
    guardar_con_traduccion_de_integridad(organizacion_id, sesion, lambda: sesion.add(presentacion))
    return presentacion


def obtener_presentacion_por_id(
    organizacion_id: UUID, presentacion_id: UUID, sesion: Session
) -> Presentacion | None:
    presentacion = sesion.get(Presentacion, presentacion_id)
    if presentacion is None or presentacion.organizacion_id != organizacion_id:
        return None
    return presentacion


def listar_presentaciones_de_producto(
    organizacion_id: UUID, producto_id: UUID, sesion: Session
) -> list[Presentacion]:
    consulta = (
        select(Presentacion)
        .where(
            Presentacion.organizacion_id == organizacion_id,
            Presentacion.producto_id == producto_id,
        )
        .order_by(Presentacion.creado_en)
    )
    return list(sesion.scalars(consulta).all())


def obtener_referencia_de_producto(
    organizacion_id: UUID, producto_id: UUID, sesion: Session
) -> Presentacion | None:
    consulta = select(Presentacion).where(
        Presentacion.organizacion_id == organizacion_id,
        Presentacion.producto_id == producto_id,
        Presentacion.es_referencia.is_(True),
    )
    return sesion.scalars(consulta).one_or_none()


def actualizar_presentacion(
    organizacion_id: UUID,
    sesion: Session,
    *,
    presentacion_id: UUID,
    nombre: str,
    unidades_base: int,
    usar_en_venta: bool,
    usar_en_compra: bool,
    activo: bool,
    momento: datetime,
    actualizado_por_id: UUID | None = None,
) -> Presentacion | None:
    """No toca `es_referencia`: el cambio de referencia tiene su propia
    operación (`marcar_referencia`/`desmarcar_referencia`, D5) porque debe
    desmarcar la anterior y marcar la nueva en la misma transacción."""
    presentacion = obtener_presentacion_por_id(organizacion_id, presentacion_id, sesion)
    if presentacion is None:
        return None

    def _mutar() -> None:
        presentacion.nombre = nombre
        presentacion.unidades_base = unidades_base
        presentacion.usar_en_venta = usar_en_venta
        presentacion.usar_en_compra = usar_en_compra
        presentacion.activo = activo
        presentacion.actualizado_en = momento
        presentacion.actualizado_por_id = actualizado_por_id

    guardar_con_traduccion_de_integridad(organizacion_id, sesion, _mutar)
    return presentacion


def desmarcar_referencia(
    organizacion_id: UUID, producto_id: UUID, sesion: Session, *, momento: datetime
) -> None:
    """D5: desmarca la referencia actual del producto (si hay una) ANTES de
    marcar la nueva, en la misma transacción -- el índice parcial no es
    diferible, así que el orden importa (`ux_presentacion__referencia`
    exigiría dos filas con `es_referencia = true` simultáneas si se
    marcara primero)."""
    actual = obtener_referencia_de_producto(organizacion_id, producto_id, sesion)
    if actual is None:
        return

    def _mutar() -> None:
        actual.es_referencia = False
        actual.actualizado_en = momento

    guardar_con_traduccion_de_integridad(organizacion_id, sesion, _mutar)


def marcar_referencia(
    organizacion_id: UUID,
    presentacion_id: UUID,
    sesion: Session,
    *,
    momento: datetime,
) -> Presentacion | None:
    presentacion = obtener_presentacion_por_id(organizacion_id, presentacion_id, sesion)
    if presentacion is None:
        return None

    def _mutar() -> None:
        presentacion.es_referencia = True
        presentacion.actualizado_en = momento

    guardar_con_traduccion_de_integridad(organizacion_id, sesion, _mutar)
    return presentacion


FUNCIONES_SIN_ORGANIZACION_ID: frozenset[str] = frozenset()
"""Catálogo sin excepción (`design.md` D7, mismo criterio que `identidad.
repository.FUNCIONES_SIN_ORGANIZACION_ID`, tarea 6.1): `catalogo` no tiene
ningún catálogo global propio ni ningún lookup previo a la resolución de la
organización -- toda función pública recibe `organizacion_id` primero."""


# --- búsquedas por clave natural (change 10, `design.md` D4) -------------------


def buscar_categorias_por_nombre(
    organizacion_id: UUID, nombre: str, sesion: Session
) -> list[Categoria]:
    """Categorías de la organización cuyo nombre coincide con `nombre` sin distinguir
    mayúsculas ni espacios al borde, activas o no. Texto vacío no coincide con nada."""
    clave = nombre.strip().lower()
    if not clave:
        return []
    consulta = (
        select(Categoria)
        .where(
            Categoria.organizacion_id == organizacion_id,
            func.lower(func.btrim(Categoria.nombre)) == clave,
        )
        .order_by(Categoria.nombre, Categoria.id)
    )
    return list(sesion.scalars(consulta).all())


def buscar_marcas_por_nombre(organizacion_id: UUID, nombre: str, sesion: Session) -> list[Marca]:
    """Igual que `buscar_categorias_por_nombre`, para marcas."""
    clave = nombre.strip().lower()
    if not clave:
        return []
    consulta = (
        select(Marca)
        .where(
            Marca.organizacion_id == organizacion_id,
            func.lower(func.btrim(Marca.nombre)) == clave,
        )
        .order_by(Marca.nombre, Marca.id)
    )
    return list(sesion.scalars(consulta).all())


def buscar_productos_por_codigo(
    organizacion_id: UUID, codigo: str, sesion: Session
) -> list[Producto]:
    """Productos de la organización cuyo código coincide con `codigo` sin distinguir
    mayúsculas ni espacios al borde, activos o no."""
    clave = codigo.strip().lower()
    if not clave:
        return []
    consulta = (
        select(Producto)
        .where(
            Producto.organizacion_id == organizacion_id,
            func.lower(func.btrim(Producto.codigo)) == clave,
        )
        .order_by(Producto.codigo, Producto.id)
    )
    return list(sesion.scalars(consulta).all())
