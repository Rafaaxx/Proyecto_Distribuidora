"""Acceso a datos de `precios` (`docs/02-arquitectura.md` §8, `CLAUDE.md` §4). Mismo
contrato no negociable que `proveedores/repository.py`: todo método público recibe
`organizacion_id` como primer parámetro obligatorio y lo usa para filtrar toda consulta
(`tests/unit/test_repositorios_organizacion_obligatoria.py`).

`guardar_con_traduccion_de_integridad` reusa la lección 6.2 del change 05: el `flush` ocurre
dentro de un `SAVEPOINT` (`begin_nested`) para que un `IntegrityError` no deje la sesión
inutilizable; se traduce por nombre de restricción a un error de dominio con código estable.
Una clave foránea compuesta que rechaza una entidad de otra organización o inexistente se
traduce a `RECURSO_NO_ENCONTRADO` (404, INV-21; mismo criterio que ADR-035).

La carga de relaciones es siempre explícita: este módulo no declara `relationship()`.
"""

from __future__ import annotations

import base64
from collections.abc import Callable, Collection
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.precios.domain.errores import (
    CursorInvalidoError,
    NombreDuplicadoError,
    RecursoNoEncontradoError,
    ReglaDuplicadaError,
    VigenciaDuplicadaError,
)
from app.modules.precios.models import (
    ListaPrecio,
    ListaVersion,
    PrecioItem,
    RedondeoCategoria,
    ReglaMargen,
)

LIMITE_PAGINA_MAXIMO = 100
LIMITE_PAGINA_DEFAULT = 50

FUNCIONES_SIN_ORGANIZACION_ID: frozenset[str] = frozenset()
"""Ninguna: toda lectura y escritura de `precios` filtra por organización (INV-21)."""

_FK_A_RECURSO = {
    "fk_regla_margen__lista": "La lista",
    "fk_regla_margen__producto": "El producto",
    "fk_regla_margen__marca": "La marca",
    "fk_regla_margen__categoria": "La categoría",
    "fk_regla_margen__proveedor": "El proveedor",
    "fk_redondeo_categoria__lista": "La lista",
    "fk_redondeo_categoria__categoria": "La categoría",
}


def guardar_con_traduccion_de_integridad(
    organizacion_id: UUID, sesion: Session, mutar: Callable[[], None]
) -> None:
    """`mutar` DEBE ejecutar la mutación (`sesion.add(...)` o las asignaciones de atributos)
    DENTRO de este `with`, nunca antes de llamarlo."""
    del organizacion_id  # No filtra nada: la mutación ya trae su organización.
    try:
        with sesion.begin_nested():
            mutar()
    except IntegrityError as error:
        mensaje = str(getattr(error, "orig", error))
        if "ux_lista_precio__nombre" in mensaje:
            raise NombreDuplicadoError(
                "Ya existe una lista con ese nombre en esta organización."
            ) from error
        if "ux_lista_version__vigencia_desde" in mensaje:
            raise VigenciaDuplicadaError(
                "Otra versión publicada de la lista tiene la misma vigencia desde."
            ) from error
        if (
            "ux_regla_margen__alcance_activa" in mensaje
            or "ux_regla_margen__lista_activa" in mensaje
        ):
            raise ReglaDuplicadaError(
                "La lista ya tiene una regla activa para ese alcance."
            ) from error
        for restriccion, recurso in _FK_A_RECURSO.items():
            if restriccion in mensaje:
                raise RecursoNoEncontradoError(
                    f"{recurso} no existe en esta organización."
                ) from error
        raise


# --- lista_precio -----------------------------------------------------------------------


def crear_lista(
    organizacion_id: UUID,
    sesion: Session,
    *,
    lista_id: UUID,
    nombre: str,
    redondeo_multiplo: Decimal,
    redondeo_direccion: str,
    activo: bool,
    momento: datetime,
    actualizado_por_id: UUID | None = None,
) -> ListaPrecio:
    lista = ListaPrecio(
        id=lista_id,
        organizacion_id=organizacion_id,
        nombre=nombre,
        redondeo_multiplo=redondeo_multiplo,
        redondeo_direccion=redondeo_direccion,
        activo=activo,
        creado_en=momento,
        actualizado_en=momento,
        actualizado_por_id=actualizado_por_id,
    )
    guardar_con_traduccion_de_integridad(organizacion_id, sesion, lambda: sesion.add(lista))
    return lista


def obtener_lista(organizacion_id: UUID, lista_id: UUID, sesion: Session) -> ListaPrecio | None:
    lista = sesion.get(ListaPrecio, lista_id)
    if lista is None or lista.organizacion_id != organizacion_id:
        return None
    return lista


def obtener_lista_para_actualizar(
    organizacion_id: UUID, lista_id: UUID, sesion: Session
) -> ListaPrecio | None:
    """`SELECT ... FOR UPDATE`: la fila de `lista_precio` es el candado de la lista
    (`design.md` D14). Todo comando que escribe reglas, redondeos, versiones o precios de una
    lista la toma primero y revalida el estado antes de escribir."""
    consulta = (
        select(ListaPrecio)
        .where(ListaPrecio.organizacion_id == organizacion_id, ListaPrecio.id == lista_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return sesion.scalars(consulta).one_or_none()


def obtener_lista_para_compartir(
    organizacion_id: UUID, lista_id: UUID, sesion: Session
) -> ListaPrecio | None:
    """`SELECT ... FOR SHARE`: quien asigna una lista a un cliente (`clientes`) la lee así, de
    modo que desactivarla (`FOR UPDATE`) y asignarla no se crucen: o la asignación entra antes
    y la desactivación ve el uso (`LISTA_EN_USO`), o la desactivación entra antes y la
    asignación ve la lista inactiva (`LISTA_INACTIVA`). Varias asignaciones no se bloquean
    entre sí (`design.md` D11 y D14)."""
    consulta = (
        select(ListaPrecio)
        .where(ListaPrecio.organizacion_id == organizacion_id, ListaPrecio.id == lista_id)
        .with_for_update(read=True)
        .execution_options(populate_existing=True)
    )
    return sesion.scalars(consulta).one_or_none()


def actualizar_lista(
    organizacion_id: UUID,
    sesion: Session,
    lista: ListaPrecio,
    *,
    nombre: str,
    redondeo_multiplo: Decimal,
    redondeo_direccion: str,
    activo: bool,
    momento: datetime,
    actualizado_por_id: UUID | None,
) -> ListaPrecio:
    def mutar() -> None:
        lista.nombre = nombre
        lista.redondeo_multiplo = redondeo_multiplo
        lista.redondeo_direccion = redondeo_direccion
        lista.activo = activo
        lista.actualizado_en = momento
        lista.actualizado_por_id = actualizado_por_id
        sesion.flush()

    guardar_con_traduccion_de_integridad(organizacion_id, sesion, mutar)
    return lista


def listar_listas(organizacion_id: UUID, sesion: Session) -> list[ListaPrecio]:
    consulta = (
        select(ListaPrecio)
        .where(ListaPrecio.organizacion_id == organizacion_id)
        .order_by(func.lower(ListaPrecio.nombre), ListaPrecio.id)
    )
    return list(sesion.scalars(consulta).all())


def listar_listas_activas(organizacion_id: UUID, sesion: Session) -> list[ListaPrecio]:
    consulta = (
        select(ListaPrecio)
        .where(ListaPrecio.organizacion_id == organizacion_id, ListaPrecio.activo.is_(True))
        .order_by(func.lower(ListaPrecio.nombre), ListaPrecio.id)
    )
    return list(sesion.scalars(consulta).all())


def resumen_de_versiones(
    organizacion_id: UUID, sesion: Session, *, ahora: datetime
) -> tuple[dict[UUID, int], set[UUID]]:
    """Por lista: el número de su versión vigente a `ahora` (PRC-03: la `PUBLICADA` con mayor
    vigencia desde que no supera `ahora` y cuya vigencia hasta, si existe, es posterior) y el
    conjunto de listas con un borrador. Dos consultas en SQL, sin traer versiones a Python
    para decidir."""
    vigentes = (
        select(ListaVersion.lista_id, ListaVersion.numero)
        .where(
            ListaVersion.organizacion_id == organizacion_id,
            ListaVersion.estado == "PUBLICADA",
            ListaVersion.vigencia_desde <= ahora,
            (ListaVersion.vigencia_hasta.is_(None)) | (ListaVersion.vigencia_hasta > ahora),
        )
        .distinct(ListaVersion.lista_id)
        .order_by(ListaVersion.lista_id, ListaVersion.vigencia_desde.desc())
    )
    version_vigente = {fila.lista_id: fila.numero for fila in sesion.execute(vigentes)}
    con_borrador = set(
        sesion.scalars(
            select(ListaVersion.lista_id).where(
                ListaVersion.organizacion_id == organizacion_id,
                ListaVersion.estado == "BORRADOR",
            )
        )
    )
    return version_vigente, con_borrador


# --- regla_margen -----------------------------------------------------------------------


def crear_regla(
    organizacion_id: UUID,
    sesion: Session,
    *,
    regla_id: UUID,
    lista_id: UUID,
    alcance_tipo: str,
    alcance_id: UUID | None,
    tipo: str,
    valor: Decimal,
    activo: bool,
    momento: datetime,
    actualizado_por_id: UUID | None = None,
) -> ReglaMargen:
    regla = ReglaMargen(
        id=regla_id,
        organizacion_id=organizacion_id,
        lista_id=lista_id,
        alcance_tipo=alcance_tipo,
        alcance_id=alcance_id,
        tipo=tipo,
        valor=valor,
        activo=activo,
        creado_en=momento,
        actualizado_en=momento,
        actualizado_por_id=actualizado_por_id,
    )
    guardar_con_traduccion_de_integridad(organizacion_id, sesion, lambda: sesion.add(regla))
    return regla


def obtener_regla_para_actualizar(
    organizacion_id: UUID, lista_id: UUID, regla_id: UUID, sesion: Session
) -> ReglaMargen | None:
    consulta = (
        select(ReglaMargen)
        .where(
            ReglaMargen.organizacion_id == organizacion_id,
            ReglaMargen.lista_id == lista_id,
            ReglaMargen.id == regla_id,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return sesion.scalars(consulta).one_or_none()


def actualizar_regla(
    organizacion_id: UUID,
    sesion: Session,
    regla: ReglaMargen,
    *,
    tipo: str,
    valor: Decimal,
    activo: bool,
    momento: datetime,
    actualizado_por_id: UUID | None,
) -> ReglaMargen:
    def mutar() -> None:
        regla.tipo = tipo
        regla.valor = valor
        regla.activo = activo
        regla.actualizado_en = momento
        regla.actualizado_por_id = actualizado_por_id
        sesion.flush()

    guardar_con_traduccion_de_integridad(organizacion_id, sesion, mutar)
    return regla


def listar_reglas(organizacion_id: UUID, lista_id: UUID, sesion: Session) -> list[ReglaMargen]:
    consulta = (
        select(ReglaMargen)
        .where(ReglaMargen.organizacion_id == organizacion_id, ReglaMargen.lista_id == lista_id)
        .order_by(ReglaMargen.creado_en, ReglaMargen.id)
    )
    return list(sesion.scalars(consulta).all())


# --- redondeo_categoria -----------------------------------------------------------------


def obtener_redondeo_categoria_para_actualizar(
    organizacion_id: UUID, lista_id: UUID, categoria_id: UUID, sesion: Session
) -> RedondeoCategoria | None:
    consulta = (
        select(RedondeoCategoria)
        .where(
            RedondeoCategoria.organizacion_id == organizacion_id,
            RedondeoCategoria.lista_id == lista_id,
            RedondeoCategoria.categoria_id == categoria_id,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return sesion.scalars(consulta).one_or_none()


def crear_redondeo_categoria(
    organizacion_id: UUID,
    sesion: Session,
    *,
    redondeo_id: UUID,
    lista_id: UUID,
    categoria_id: UUID,
    multiplo: Decimal,
    direccion: str,
    activo: bool,
    momento: datetime,
    actualizado_por_id: UUID | None = None,
) -> RedondeoCategoria:
    redondeo = RedondeoCategoria(
        id=redondeo_id,
        organizacion_id=organizacion_id,
        lista_id=lista_id,
        categoria_id=categoria_id,
        multiplo=multiplo,
        direccion=direccion,
        activo=activo,
        creado_en=momento,
        actualizado_en=momento,
        actualizado_por_id=actualizado_por_id,
    )
    guardar_con_traduccion_de_integridad(organizacion_id, sesion, lambda: sesion.add(redondeo))
    return redondeo


def actualizar_redondeo_categoria(
    organizacion_id: UUID,
    sesion: Session,
    redondeo: RedondeoCategoria,
    *,
    multiplo: Decimal,
    direccion: str,
    activo: bool,
    momento: datetime,
    actualizado_por_id: UUID | None,
) -> RedondeoCategoria:
    def mutar() -> None:
        redondeo.multiplo = multiplo
        redondeo.direccion = direccion
        redondeo.activo = activo
        redondeo.actualizado_en = momento
        redondeo.actualizado_por_id = actualizado_por_id
        sesion.flush()

    guardar_con_traduccion_de_integridad(organizacion_id, sesion, mutar)
    return redondeo


def listar_redondeos_de_categoria(
    organizacion_id: UUID, lista_id: UUID, sesion: Session
) -> list[RedondeoCategoria]:
    consulta = (
        select(RedondeoCategoria)
        .where(
            RedondeoCategoria.organizacion_id == organizacion_id,
            RedondeoCategoria.lista_id == lista_id,
        )
        .order_by(RedondeoCategoria.creado_en, RedondeoCategoria.id)
    )
    return list(sesion.scalars(consulta).all())


# --- lista_version (borradores y versiones publicadas) -----------------------------------


def obtener_borrador(organizacion_id: UUID, lista_id: UUID, sesion: Session) -> ListaVersion | None:
    """El borrador de la lista, si lo tiene: a lo sumo uno (`ux_lista_version__borrador`,
    D5). Se llama con el candado de la lista tomado (D14)."""
    consulta = (
        select(ListaVersion)
        .where(
            ListaVersion.organizacion_id == organizacion_id,
            ListaVersion.lista_id == lista_id,
            ListaVersion.estado == "BORRADOR",
        )
        .execution_options(populate_existing=True)
    )
    return sesion.scalars(consulta).one_or_none()


def obtener_version(
    organizacion_id: UUID, lista_id: UUID, version_id: UUID, sesion: Session
) -> ListaVersion | None:
    """Una versión de la lista, leída con el candado de la lista ya tomado (D14) y sin usar
    lo que la sesión tenga en memoria."""
    consulta = (
        select(ListaVersion)
        .where(
            ListaVersion.organizacion_id == organizacion_id,
            ListaVersion.lista_id == lista_id,
            ListaVersion.id == version_id,
        )
        .execution_options(populate_existing=True)
    )
    return sesion.scalars(consulta).one_or_none()


def listar_versiones(organizacion_id: UUID, lista_id: UUID, sesion: Session) -> list[ListaVersion]:
    """Las versiones de la lista, de la más nueva (mayor número) a la más antigua."""
    consulta = (
        select(ListaVersion)
        .where(ListaVersion.organizacion_id == organizacion_id, ListaVersion.lista_id == lista_id)
        .order_by(ListaVersion.numero.desc())
        .execution_options(populate_existing=True)
    )
    return list(sesion.scalars(consulta).all())


def obtener_version_base(
    organizacion_id: UUID, lista_id: UUID, sesion: Session
) -> ListaVersion | None:
    """La versión base de un borrador (D4): la `PUBLICADA` -no anulada- de mayor vigencia
    desde de la lista, vigente o programada; `None` si la lista no publicó nunca."""
    consulta = (
        select(ListaVersion)
        .where(
            ListaVersion.organizacion_id == organizacion_id,
            ListaVersion.lista_id == lista_id,
            ListaVersion.estado == "PUBLICADA",
        )
        .order_by(ListaVersion.vigencia_desde.desc())
        .limit(1)
    )
    return sesion.scalars(consulta).one_or_none()


def siguiente_numero_de_version(organizacion_id: UUID, lista_id: UUID, sesion: Session) -> int:
    """El número siguiente de la lista. Se asigna con el candado de la lista tomado (D14);
    `ux_lista_version__numero` es la garantía final."""
    maximo = sesion.execute(
        select(func.max(ListaVersion.numero)).where(
            ListaVersion.organizacion_id == organizacion_id, ListaVersion.lista_id == lista_id
        )
    ).scalar_one()
    return int(maximo or 0) + 1


def crear_borrador(
    organizacion_id: UUID,
    sesion: Session,
    *,
    version_id: UUID,
    lista_id: UUID,
    numero: int,
    version_base_id: UUID | None,
    generado_en: datetime,
    creado_por_id: UUID,
    operation_id: UUID,
) -> ListaVersion:
    version = ListaVersion(
        id=version_id,
        organizacion_id=organizacion_id,
        lista_id=lista_id,
        numero=numero,
        estado="BORRADOR",
        version_base_id=version_base_id,
        generado_en=generado_en,
        creado_por_id=creado_por_id,
        creado_en=generado_en,
        operation_id=operation_id,
    )
    guardar_con_traduccion_de_integridad(organizacion_id, sesion, lambda: sesion.add(version))
    return version


def actualizar_generacion(
    organizacion_id: UUID,
    sesion: Session,
    version: ListaVersion,
    *,
    version_base_id: UUID | None,
    generado_en: datetime,
) -> ListaVersion:
    """Regenerar un borrador: nueva versión base y nuevo momento de generación; el número, el
    creador y el `operation_id` de origen no cambian (D5)."""

    def mutar() -> None:
        version.version_base_id = version_base_id
        version.generado_en = generado_en
        sesion.flush()

    guardar_con_traduccion_de_integridad(organizacion_id, sesion, mutar)
    return version


# --- precio_item -------------------------------------------------------------------------


def listar_precios_de_version(
    organizacion_id: UUID, version_id: UUID, sesion: Session
) -> list[PrecioItem]:
    consulta = (
        select(PrecioItem)
        .where(PrecioItem.organizacion_id == organizacion_id, PrecioItem.version_id == version_id)
        .order_by(PrecioItem.producto_id)
        .execution_options(populate_existing=True)
    )
    return list(sesion.scalars(consulta).all())


def listar_precios_de_productos(
    organizacion_id: UUID, version_id: UUID, producto_ids: Collection[UUID], sesion: Session
) -> list[PrecioItem]:
    """Los precios de `producto_ids` en la versión, en una consulta (resolución de precio)."""
    if not producto_ids:
        return []
    consulta = (
        select(PrecioItem)
        .where(
            PrecioItem.organizacion_id == organizacion_id,
            PrecioItem.version_id == version_id,
            PrecioItem.producto_id.in_(producto_ids),
        )
        .order_by(PrecioItem.producto_id)
        .execution_options(populate_existing=True)
    )
    return list(sesion.scalars(consulta).all())


def borrar_precios_de_version(
    organizacion_id: UUID,
    version_id: UUID,
    sesion: Session,
    *,
    producto_ids: Collection[UUID] | None = None,
) -> None:
    """Quita los precios de un BORRADOR para volver a escribirlos (D5, D13 punto 7: `DELETE`
    sobre `precio_item`): los de `producto_ids`, o todos si es `None`. Solo lo llama la
    función única de escritura de precios del servicio, que exige un borrador."""
    consulta = delete(PrecioItem).where(
        PrecioItem.organizacion_id == organizacion_id, PrecioItem.version_id == version_id
    )
    if producto_ids is not None:
        consulta = consulta.where(PrecioItem.producto_id.in_(producto_ids))
    sesion.execute(consulta)


def insertar_precios(organizacion_id: UUID, sesion: Session, filas: list[PrecioItem]) -> None:
    """Inserta los precios en lote: todo o nada. Solo lo llama la función única de escritura
    de precios del servicio (D13)."""

    def mutar() -> None:
        sesion.add_all(filas)
        sesion.flush()

    guardar_con_traduccion_de_integridad(organizacion_id, sesion, mutar)


def _codificar_cursor(producto_id: UUID) -> str:
    return base64.urlsafe_b64encode(str(producto_id).encode("ascii")).decode("ascii")


def _decodificar_cursor(cursor: str) -> UUID:
    try:
        return UUID(base64.urlsafe_b64decode(cursor.encode("ascii")).decode("ascii"))
    except ValueError as error:  # incluye `binascii.Error` y `UnicodeError`
        raise CursorInvalidoError("El cursor de paginación no es válido.") from error


def listar_precios_paginado(
    organizacion_id: UUID,
    version_id: UUID,
    sesion: Session,
    *,
    limite: int = LIMITE_PAGINA_DEFAULT,
    cursor: str | None = None,
) -> tuple[list[PrecioItem], str | None]:
    """Los precios de una versión paginados por cursor (`02` §11), ordenados por
    `producto_id` (único por versión, PRC-10: una clave estable para el cursor). Devuelve
    `(precios, cursor_siguiente)`; el cursor es `None` en la última página."""
    limite_efectivo = min(max(limite, 1), LIMITE_PAGINA_MAXIMO)
    consulta = select(PrecioItem).where(
        PrecioItem.organizacion_id == organizacion_id, PrecioItem.version_id == version_id
    )
    if cursor is not None:
        consulta = consulta.where(PrecioItem.producto_id > _decodificar_cursor(cursor))
    consulta = consulta.order_by(PrecioItem.producto_id).limit(limite_efectivo + 1)
    filas = list(sesion.scalars(consulta).all())
    if len(filas) > limite_efectivo:
        pagina = filas[:limite_efectivo]
        return pagina, _codificar_cursor(pagina[-1].producto_id)
    return filas, None


def precios_finales_por_producto(
    organizacion_id: UUID, version_id: UUID, producto_ids: Collection[UUID], sesion: Session
) -> dict[UUID, Decimal]:
    """`{producto_id: precio_final}` de `producto_ids` en la versión, en una consulta: el
    precio de la versión base para compararlo con el del borrador (PRC-17)."""
    if not producto_ids:
        return {}
    consulta = select(PrecioItem.producto_id, PrecioItem.precio_final).where(
        PrecioItem.organizacion_id == organizacion_id,
        PrecioItem.version_id == version_id,
        PrecioItem.producto_id.in_(producto_ids),
    )
    return {fila.producto_id: fila.precio_final for fila in sesion.execute(consulta)}


def ids_de_productos_con_precio(
    organizacion_id: UUID, version_id: UUID, sesion: Session
) -> set[UUID]:
    consulta = select(PrecioItem.producto_id).where(
        PrecioItem.organizacion_id == organizacion_id, PrecioItem.version_id == version_id
    )
    return set(sesion.scalars(consulta).all())


def vigencias_desde_publicadas(
    organizacion_id: UUID, lista_id: UUID, sesion: Session
) -> list[datetime]:
    """Las vigencias desde de las versiones `PUBLICADA` de la lista (las anuladas no cuentan:
    `ux_lista_version__vigencia_desde` es parcial sobre las publicadas, D6)."""
    consulta = select(ListaVersion.vigencia_desde).where(
        ListaVersion.organizacion_id == organizacion_id,
        ListaVersion.lista_id == lista_id,
        ListaVersion.estado == "PUBLICADA",
        ListaVersion.vigencia_desde.is_not(None),
    )
    return [vigencia for vigencia in sesion.scalars(consulta).all() if vigencia is not None]


def contar_precios_de_version(organizacion_id: UUID, version_id: UUID, sesion: Session) -> int:
    """Cuántos precios tiene la versión, contados en la base."""
    return int(
        sesion.execute(
            select(func.count()).where(
                PrecioItem.organizacion_id == organizacion_id, PrecioItem.version_id == version_id
            )
        ).scalar_one()
    )


def marcar_publicada(
    organizacion_id: UUID,
    sesion: Session,
    version: ListaVersion,
    *,
    vigencia_desde: datetime,
    vigencia_hasta: datetime | None,
    publicado_por_id: UUID,
    publicado_en: datetime,
) -> ListaVersion:
    """`BORRADOR` -> `PUBLICADA` con su vigencia, usuario y momento (PRC-02). Solo cambia las
    columnas que `app_runtime` puede actualizar (D13 punto 7); los precios no se tocan."""

    def mutar() -> None:
        version.estado = "PUBLICADA"
        version.vigencia_desde = vigencia_desde
        version.vigencia_hasta = vigencia_hasta
        version.publicado_por_id = publicado_por_id
        version.publicado_en = publicado_en
        sesion.flush()

    guardar_con_traduccion_de_integridad(organizacion_id, sesion, mutar)
    return version


def marcar_anulada(
    organizacion_id: UUID,
    sesion: Session,
    version: ListaVersion,
    *,
    anulado_por_id: UUID,
    anulado_en: datetime,
) -> ListaVersion:
    """`PUBLICADA` -> `ANULADA` con usuario y momento (PRC-05). No toca ni borra los precios
    ni las vigencias (TR-06, INV-11)."""

    def mutar() -> None:
        version.estado = "ANULADA"
        version.anulado_por_id = anulado_por_id
        version.anulado_en = anulado_en
        sesion.flush()

    guardar_con_traduccion_de_integridad(organizacion_id, sesion, mutar)
    return version
