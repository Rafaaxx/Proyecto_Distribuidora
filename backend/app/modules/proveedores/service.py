"""Interfaz pública de `proveedores` (`CLAUDE.md` §4: un módulo usa a otro
solo a través de su `service.py`).

Expone alta/modificación/consulta de proveedores (tarea 8.2), informar
costos en lote (tarea 8.3, `design.md` D3/D4/D12/D14), y las lecturas que
el change 13 necesita (tarea 8.4). Sin `commit`: la transacción la
gestiona el bus de comandos (`proveedores/commands.py`, grupo 9) o quien
llame en pruebas (`CLAUDE.md` §4).

Al importarse, este módulo registra en `catalogo/service.py` el puerto de
consulta de proveedor (D9-A, ADR-025) y el verificador de uso de
`costo_informado` (D1, ADR-023) -- mismo patrón que `app/commands/
registro.py` con los handlers: alguien (`app.main`, o el propio test) debe
importar este módulo para que los puertos queden registrados."""

from __future__ import annotations

from datetime import date
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.core.ids import nuevo_id
from app.modules.catalogo import service as catalogo_service
from app.modules.configuracion import service as configuracion_service
from app.modules.proveedores import repository
from app.modules.proveedores.domain.costo_base import calcular_costo_base
from app.modules.proveedores.domain.errores import (
    CuitInvalidoError,
    PresentacionInvalidaError,
    ProductoInactivoError,
    ProveedorConProductosActivosError,
    ProveedorInactivoError,
    ProveedorNoCorrespondeError,
    RecursoNoEncontradoError,
)
from app.modules.proveedores.domain.lote import (
    CostoDelLote as CostoDelLote,  # re-exportado: lo usa `importacion` (change 10)
)
from app.modules.proveedores.domain.lote import validar_lote_de_costos
from app.modules.proveedores.domain.normalizacion import normalizar_cuit, normalizar_nombre
from app.modules.proveedores.models import CostoInformado, Proveedor

# --- D9/ADR-025: registro del puerto de consulta al importar este módulo --


def _consultar_estado_de_proveedor(
    organizacion_id: UUID, proveedor_id: UUID, sesion: Session
) -> catalogo_service.EstadoProveedor | None:
    proveedor = repository.obtener_proveedor_por_id_para_compartir(
        organizacion_id, proveedor_id, sesion
    )
    if proveedor is None:
        return None
    return catalogo_service.EstadoProveedor(activo=proveedor.activo, nombre=proveedor.nombre)


catalogo_service.registrar_consulta_proveedor(_consultar_estado_de_proveedor)


# --- D1/ADR-023: registro del verificador de uso de costo_informado -------


def _presentacion_tiene_costo_informado(
    organizacion_id: UUID, presentacion_id: UUID, sesion: Session
) -> bool:
    return repository.existe_costo_para_presentacion(organizacion_id, presentacion_id, sesion)


catalogo_service.registrar_verificador_uso("costo_informado", _presentacion_tiene_costo_informado)


# --- proveedor (D7, D5/ADR-026) --------------------------------------------


def _normalizar_cuit_o_rechazar(cuit: str | None) -> str | None:
    """D7: el CUIT es opcional; si se cargó un valor no vacío que no
    normaliza a 11 dígitos, se rechaza (`CUIT_INVALIDO`) -- distinto de "no
    se cargó CUIT" (`None`/cadena vacía), que no es un error."""
    if cuit is None:
        return None
    recortado = cuit.strip()
    if recortado == "":
        return None
    normalizado = normalizar_cuit(recortado)
    if normalizado is None:
        raise CuitInvalidoError(
            "El CUIT debe tener 11 dígitos (los guiones y espacios se descartan)."
        )
    return normalizado


def crear_proveedor(
    organizacion_id: UUID,
    sesion: Session,
    reloj: Clock,
    *,
    nombre: str,
    cuit: str | None,
    contacto: str | None,
    telefono: str | None,
    email: str | None,
    actor_id: UUID | None,
) -> Proveedor:
    nombre_normalizado = normalizar_nombre(nombre)
    cuit_normalizado = _normalizar_cuit_o_rechazar(cuit)
    momento = reloj.now()
    return repository.crear_proveedor(
        organizacion_id,
        sesion,
        proveedor_id=nuevo_id(),
        nombre=nombre_normalizado,
        cuit=cuit_normalizado,
        contacto=contacto,
        telefono=telefono,
        email=email,
        activo=True,
        momento=momento,
        actualizado_por_id=actor_id,
    )


def modificar_proveedor(
    organizacion_id: UUID,
    sesion: Session,
    reloj: Clock,
    *,
    proveedor_id: UUID,
    nombre: str,
    cuit: str | None,
    contacto: str | None,
    telefono: str | None,
    email: str | None,
    activo: bool,
    actor_id: UUID | None,
) -> Proveedor:
    """`PROVEEDOR_MODIFICAR` (D14: `FOR UPDATE` sobre la fila del
    proveedor, antes de decidir/escribir). D5/ADR-026: rechaza
    `PROVEEDOR_CON_PRODUCTOS_ACTIVOS` si se intenta desactivar (transición
    `True -> False`) un proveedor con productos activos -- reactivar, o
    mantener el mismo estado, no dispara la verificación (mismo criterio
    que `catalogo_service.modificar_categoria`, D11 del 05)."""
    proveedor = repository.obtener_proveedor_por_id_para_actualizar(
        organizacion_id, proveedor_id, sesion
    )
    if proveedor is None:
        raise RecursoNoEncontradoError(
            f"El proveedor {proveedor_id} no existe en esta organización."
        )

    nombre_normalizado = normalizar_nombre(nombre)
    cuit_normalizado = _normalizar_cuit_o_rechazar(cuit)

    if (
        proveedor.activo
        and not activo
        and catalogo_service.existen_productos_activos_de_proveedor(
            organizacion_id, proveedor_id, sesion
        )
    ):
        raise ProveedorConProductosActivosError(
            "No se puede desactivar un proveedor con productos activos (ADR-026)."
        )

    actualizado = repository.actualizar_proveedor(
        organizacion_id,
        sesion,
        proveedor_id=proveedor_id,
        nombre=nombre_normalizado,
        cuit=cuit_normalizado,
        contacto=contacto,
        telefono=telefono,
        email=email,
        activo=activo,
        momento=reloj.now(),
        actualizado_por_id=actor_id,
    )
    assert actualizado is not None
    return actualizado


def listar_proveedores(
    organizacion_id: UUID,
    sesion: Session,
    *,
    limite: int = repository.LIMITE_PAGINA_DEFAULT,
    cursor: str | None = None,
    texto: str | None = None,
    activo: bool | None = None,
) -> tuple[list[Proveedor], str | None]:
    return repository.listar_proveedores_paginado(
        organizacion_id, sesion, limite=limite, cursor=cursor, texto=texto, activo=activo
    )


def buscar_proveedores_por_nombre(
    organizacion_id: UUID, nombre: str, sesion: Session
) -> list[Proveedor]:
    """Lectura pública para la importación (change 10, `design.md` D4): proveedores de
    la organización con ese nombre, sin distinguir mayúsculas ni espacios al borde,
    activos o no (el alta de producto y de costo rechazan después uno inactivo con
    `PROVEEDOR_INACTIVO`)."""
    return repository.buscar_proveedores_por_nombre(organizacion_id, nombre, sesion)


def listar_opciones_de_proveedores(
    organizacion_id: UUID,
    sesion: Session,
    *,
    limite: int = repository.LIMITE_PAGINA_DEFAULT,
    cursor: str | None = None,
) -> tuple[list[Proveedor], str | None]:
    """`GET /proveedores/opciones` (D8, contrato-api.md P2 aprobado
    2026-09-24): solo proveedores activos, paginados."""
    return repository.listar_opciones_de_proveedores(
        organizacion_id, sesion, limite=limite, cursor=cursor
    )


def obtener_proveedor(
    organizacion_id: UUID, proveedor_id: UUID, sesion: Session
) -> Proveedor | None:
    return repository.obtener_proveedor_por_id(organizacion_id, proveedor_id, sesion)


# --- COSTO_INFORMAR (tarea 8.3, [ALTA: cálculo de costos]) ----------------


def informar_costos(
    organizacion_id: UUID,
    sesion: Session,
    reloj: Clock,
    *,
    proveedor_id: UUID,
    costos: list[CostoDelLote],
    operation_id: UUID,
    actor_id: UUID,
) -> list[CostoInformado]:
    """`COSTO_INFORMAR` (`design.md` D3, D4, D12, D14; CST-01, CST-02,
    INV-01, INV-18).

    Orden de validación y bloqueo (D14, evita interbloqueos entre lotes
    concurrentes): 1) forma del lote (6.4, pura); 2) proveedor, `FOR SHARE`;
    3) productos referenciados, `FOR SHARE`, en orden ascendente de `id`.
    Todo el cálculo (6.3) y la resolución de presentaciones/alícuota ocurre
    ANTES de la única llamada a `repository.insertar_costos` -- si algo
    falla a mitad de camino (INV-01), no se llegó a construir ninguna fila
    para insertar."""
    validar_lote_de_costos(costos)

    proveedor = repository.obtener_proveedor_por_id_para_compartir(
        organizacion_id, proveedor_id, sesion
    )
    if proveedor is None:
        raise RecursoNoEncontradoError(
            f"El proveedor {proveedor_id} no existe en esta organización."
        )
    if not proveedor.activo:
        raise ProveedorInactivoError(f"El proveedor {proveedor_id} está inactivo (D5).")

    # contrato-api.md P9 (aprobado 2026-09-24): `fila` es el índice 0-based
    # de la PRIMERA fila del lote que referencia cada producto -- el lock de
    # productos (D14) recorre ids únicos y ordenados, no filas, pero el
    # error que puede levantar sigue siendo específico de una fila.
    primera_fila_por_producto: dict[UUID, int] = {}
    for fila, costo in enumerate(costos):
        primera_fila_por_producto.setdefault(costo.producto_id, fila)

    productos_por_id: dict[UUID, Any] = {}
    ids_productos_ordenados = sorted({costo.producto_id for costo in costos})
    for producto_id in ids_productos_ordenados:
        fila_producto = primera_fila_por_producto[producto_id]
        producto = catalogo_service.obtener_producto_para_compartir(
            organizacion_id, producto_id, sesion
        )
        if producto is None:
            raise RecursoNoEncontradoError(
                f"El producto {producto_id} no existe en esta organización.",
                extension={"fila": fila_producto},
            )
        if producto.proveedor_id != proveedor_id:
            raise ProveedorNoCorrespondeError(
                f"El producto {producto_id} no tiene a {proveedor_id} como proveedor actual (D3).",
                extension={"fila": fila_producto},
            )
        if not producto.activo:
            raise ProductoInactivoError(
                f"El producto {producto_id} está inactivo.", extension={"fila": fila_producto}
            )
        productos_por_id[producto_id] = producto

    momento = reloj.now()
    filas: list[repository.DatosCostoInformado] = []
    for fila_actual, costo in enumerate(costos):
        producto = productos_por_id[costo.producto_id]
        presentacion = catalogo_service.obtener_presentacion(
            organizacion_id, costo.presentacion_id, sesion
        )
        if (
            presentacion is None
            or presentacion.producto_id != costo.producto_id
            or not presentacion.activo
            or not presentacion.usar_en_compra
        ):
            raise PresentacionInvalidaError(
                f"La presentación {costo.presentacion_id} no es una presentación de compra "
                f"activa del producto {costo.producto_id}.",
                extension={"fila": fila_actual},
            )

        alicuota = configuracion_service.obtener_alicuota_por_id(
            organizacion_id, producto.alicuota_id, sesion
        )
        assert alicuota is not None  # la FK del producto garantiza su existencia.

        costo_base = calcular_costo_base(
            valor=costo.valor,
            incluye_iva=costo.incluye_iva,
            alicuota=alicuota.valor,
            bonificacion=costo.bonificacion,
            unidades=presentacion.unidades_base,
        )

        filas.append(
            repository.DatosCostoInformado(
                id=nuevo_id(),
                proveedor_id=proveedor_id,
                producto_id=costo.producto_id,
                presentacion_id=costo.presentacion_id,
                valor=costo.valor,
                incluye_iva=costo.incluye_iva,
                bonificacion=costo.bonificacion,
                alicuota_aplicada=alicuota.valor,
                costo_base=costo_base,
                vigencia_desde=costo.vigencia_desde,
                observacion=costo.observacion,
                operation_id=operation_id,
                usuario_id=actor_id,
                momento=momento,
            )
        )

    return repository.insertar_costos(organizacion_id, sesion, costos=filas)


# --- lecturas para el change 13 (tarea 8.4) --------------------------------


def obtener_costo_informado_vigente(
    organizacion_id: UUID, producto_id: UUID, fecha: date, sesion: Session
) -> CostoInformado | None:
    """CST-03: el costo vigente de un producto para `fecha`, resuelto con
    SQL (D4)."""
    return repository.obtener_vigente(organizacion_id, producto_id, fecha, sesion)


def listar_historial_costos(
    organizacion_id: UUID,
    producto_id: UUID,
    sesion: Session,
    *,
    limite: int = repository.LIMITE_PAGINA_DEFAULT,
    cursor: str | None = None,
) -> tuple[list[CostoInformado], str | None]:
    return repository.listar_historial_de_producto(
        organizacion_id, producto_id, sesion, limite=limite, cursor=cursor
    )


def listar_ultimo_costo_por_presentacion(
    organizacion_id: UUID, producto_id: UUID, fecha: date, sesion: Session
) -> list[CostoInformado]:
    """P11 (`contrato-api.md`, aprobado en la verificación manual 13.5,
    opción B): el último costo informado (D4) de CADA presentación del
    producto con al menos un costo con `vigencia_desde <= fecha` -- las
    presentaciones sin costo se omiten. Informativo: el precio (PRC-11)
    sigue calculándose solo con `obtener_costo_informado_vigente`."""
    return repository.obtener_ultimo_por_presentacion(organizacion_id, producto_id, fecha, sesion)
