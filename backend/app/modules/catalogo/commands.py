"""Handlers de comandos de `catalogo` (change 05, grupo 8; `design.md` D3,
D4, D7 -- plantilla del change 04, aprobada tal cual el 2026-09-22).

Nueve tipos, todos `ONLINE`, permiso `GESTIONAR_CATALOGO` (D4):
`CATEGORIA_CREAR`, `CATEGORIA_MODIFICAR`, `MARCA_CREAR`, `MARCA_MODIFICAR`,
`PRODUCTO_CREAR`, `PRODUCTO_MODIFICAR`, `PRESENTACION_AGREGAR`,
`PRESENTACION_MODIFICAR`, `PRESENTACION_REFERENCIA_CAMBIAR`. Cada handler
declara `sesion`/`reloj` como parámetros de palabra clave OBLIGATORIOS
(sin default) -- mismo motivo que `identidad/commands.py` (ver su
docstring, D3): `HandlerFuncion` no los modela todavía (deuda nominada al
change 17), pero los nueve tipos de acá son `admite_offline=False` y sus
endpoints (grupo 9) llaman al handler directamente con los cuatro
argumentos, nunca a través del despacho genérico de dos argumentos del
lote `OFFLINE`.

A diferencia de `identidad/commands.py` (que devuelve `"RECHAZADO"` para
"no encontrado" porque sus funciones de servicio devuelven `None`), los
servicios de `catalogo` LANZAN `RecursoNoEncontradoError` y el resto de los
errores de dominio (`design.md` D6: "esto difiere de identidad ... aquí se
sigue `02` §6.3 al pie de la letra"). Los handlers de acá no atrapan nada:
dejan que la excepción suba, el bus (`sync/service.py::procesar_comando`)
revierte TODA la transacción, incluida la reserva del `operation_id`, y el
`operation_id` puede reintentarse con contenido corregido.

Los ids de entidades nuevas se generan en el servidor (UUIDv7,
`core/ids.py`, dentro de `catalogo/service.py`) y se devuelven en el
resultado del comando (D4, mismo criterio que `USUARIO_CREAR`).

Change 06, grupo 9 (`design.md` D6 del 06): `PRODUCTO_CREAR` y
`PRODUCTO_MODIFICAR` pasan a **v2**, con `proveedor_id` obligatorio; v1 se
retira (sin comandos pendientes: ambos tipos son `admite_offline=False`).
Un envío v1 recibe `VersionDeComandoSinHandlerError`. Los endpoints REST de
`catalogo/api.py` siguen construyendo el sobre v1 hasta que el change 06
grupo 10 amplíe el contrato de la API (`ProductoCrearRequest`/
`ProductoModificarRequest` con `proveedor_id`) -- deuda nominada, no
resuelta acá.
"""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel

from app.commands.catalogo import declarar_tipo
from app.commands.registro import registrar_handler
from app.commands.sobre import SobreComando
from app.core.clock import Clock
from app.modules.catalogo import service as catalogo_service
from app.modules.catalogo.domain.presentaciones import DatosPresentacion

ResultadoHandler = tuple[str, dict[str, object] | None, str | None]
"""Misma convención que `sync/service.py::ResultadoHandler` (ver
`identidad/commands.py` para la justificación de no importarla de `sync`)."""


# --- CATEGORIA_CREAR / CATEGORIA_MODIFICAR (CAT-01, CAT-05, D11) -----------


class CategoriaCrearContenidoV1(BaseModel):
    nombre: str


def manejar_categoria_crear(
    sobre: SobreComando, contenido: CategoriaCrearContenidoV1, *, sesion: object, reloj: Clock
) -> ResultadoHandler:
    categoria = catalogo_service.crear_categoria(
        sobre.organizacion_id,
        sesion,  # type: ignore[arg-type]
        reloj,
        nombre=contenido.nombre,
        actor_id=sobre.usuario_id,
    )
    return "ACEPTADO", {"categoria_id": str(categoria.id)}, None


registrar_handler("CATEGORIA_CREAR", 1, CategoriaCrearContenidoV1)(
    manejar_categoria_crear  # type: ignore[arg-type]
)
declarar_tipo("CATEGORIA_CREAR", admite_online=True, admite_offline=False)


class CategoriaModificarContenidoV1(BaseModel):
    categoria_id: UUID
    nombre: str
    activo: bool


def manejar_categoria_modificar(
    sobre: SobreComando,
    contenido: CategoriaModificarContenidoV1,
    *,
    sesion: object,
    reloj: Clock,
) -> ResultadoHandler:
    categoria = catalogo_service.modificar_categoria(
        sobre.organizacion_id,
        sesion,  # type: ignore[arg-type]
        reloj,
        categoria_id=contenido.categoria_id,
        nombre=contenido.nombre,
        activo=contenido.activo,
        actor_id=sobre.usuario_id,
    )
    return "ACEPTADO", {"categoria_id": str(categoria.id)}, None


registrar_handler("CATEGORIA_MODIFICAR", 1, CategoriaModificarContenidoV1)(
    manejar_categoria_modificar  # type: ignore[arg-type]
)
declarar_tipo("CATEGORIA_MODIFICAR", admite_online=True, admite_offline=False)


# --- MARCA_CREAR / MARCA_MODIFICAR (CAT-01, CAT-05) ------------------------


class MarcaCrearContenidoV1(BaseModel):
    nombre: str


def manejar_marca_crear(
    sobre: SobreComando, contenido: MarcaCrearContenidoV1, *, sesion: object, reloj: Clock
) -> ResultadoHandler:
    marca = catalogo_service.crear_marca(
        sobre.organizacion_id,
        sesion,  # type: ignore[arg-type]
        reloj,
        nombre=contenido.nombre,
        actor_id=sobre.usuario_id,
    )
    return "ACEPTADO", {"marca_id": str(marca.id)}, None


registrar_handler("MARCA_CREAR", 1, MarcaCrearContenidoV1)(
    manejar_marca_crear  # type: ignore[arg-type]
)
declarar_tipo("MARCA_CREAR", admite_online=True, admite_offline=False)


class MarcaModificarContenidoV1(BaseModel):
    marca_id: UUID
    nombre: str
    activo: bool


def manejar_marca_modificar(
    sobre: SobreComando, contenido: MarcaModificarContenidoV1, *, sesion: object, reloj: Clock
) -> ResultadoHandler:
    marca = catalogo_service.modificar_marca(
        sobre.organizacion_id,
        sesion,  # type: ignore[arg-type]
        reloj,
        marca_id=contenido.marca_id,
        nombre=contenido.nombre,
        activo=contenido.activo,
        actor_id=sobre.usuario_id,
    )
    return "ACEPTADO", {"marca_id": str(marca.id)}, None


registrar_handler("MARCA_MODIFICAR", 1, MarcaModificarContenidoV1)(
    manejar_marca_modificar  # type: ignore[arg-type]
)
declarar_tipo("MARCA_MODIFICAR", admite_online=True, admite_offline=False)


# --- PRODUCTO_CREAR / PRODUCTO_MODIFICAR (CAT-01 a CAT-06, INV-01) ---------


class PresentacionInicialContenidoV1(BaseModel):
    """Presentación inicial de un `PRODUCTO_CREAR` (D4: "incluye las
    presentaciones iniciales para que CAT-03 se cumpla desde la primera
    confirmación"). `unidades_base: int`: Pydantic ya rechaza un valor con
    parte fraccionaria (`2.5`) como contenido inválido, antes de llegar al
    dominio (spec productos-y-presentaciones, "0, -6 o 2.5")."""

    nombre: str
    unidades_base: int
    usar_en_venta: bool
    usar_en_compra: bool
    es_referencia: bool


class ProductoCrearContenidoV2(BaseModel):
    """D6 (change 06): v2 retira v1 y hace `proveedor_id` obligatorio --
    `02` §6.6 permite retirar una versión sin comandos pendientes, y
    `PRODUCTO_CREAR` es `admite_offline=False`, así que no hay cola v1 que
    proteger. Un envío v1 recibe `VersionDeComandoSinHandlerError` (`app/
    commands/registro.py`), no se reescribe el esquema v1 en el lugar."""

    codigo: str
    nombre: str
    categoria_id: UUID
    marca_id: UUID | None = None
    proveedor_id: UUID
    unidad_base: str
    alicuota_id: UUID
    presentaciones: list[PresentacionInicialContenidoV1]


def manejar_producto_crear(
    sobre: SobreComando, contenido: ProductoCrearContenidoV2, *, sesion: object, reloj: Clock
) -> ResultadoHandler:
    producto, presentaciones = catalogo_service.crear_producto(
        sobre.organizacion_id,
        sesion,  # type: ignore[arg-type]
        reloj,
        codigo=contenido.codigo,
        nombre=contenido.nombre,
        categoria_id=contenido.categoria_id,
        marca_id=contenido.marca_id,
        proveedor_id=contenido.proveedor_id,
        unidad_base=contenido.unidad_base,
        alicuota_id=contenido.alicuota_id,
        presentaciones=[
            DatosPresentacion(
                nombre=datos.nombre,
                unidades_base=datos.unidades_base,
                usar_en_venta=datos.usar_en_venta,
                usar_en_compra=datos.usar_en_compra,
                es_referencia=datos.es_referencia,
            )
            for datos in contenido.presentaciones
        ],
        actor_id=sobre.usuario_id,
    )
    return (
        "ACEPTADO",
        {
            "producto_id": str(producto.id),
            "presentacion_ids": [str(presentacion.id) for presentacion in presentaciones],
        },
        None,
    )


registrar_handler("PRODUCTO_CREAR", 2, ProductoCrearContenidoV2)(
    manejar_producto_crear  # type: ignore[arg-type]
)
declarar_tipo("PRODUCTO_CREAR", admite_online=True, admite_offline=False)


class ProductoModificarContenidoV2(BaseModel):
    """D6 (change 06): mismo criterio que `ProductoCrearContenidoV2`."""

    producto_id: UUID
    codigo: str
    nombre: str
    categoria_id: UUID
    marca_id: UUID | None = None
    proveedor_id: UUID
    unidad_base: str
    alicuota_id: UUID
    activo: bool


def manejar_producto_modificar(
    sobre: SobreComando, contenido: ProductoModificarContenidoV2, *, sesion: object, reloj: Clock
) -> ResultadoHandler:
    producto = catalogo_service.modificar_producto(
        sobre.organizacion_id,
        sesion,  # type: ignore[arg-type]
        reloj,
        producto_id=contenido.producto_id,
        codigo=contenido.codigo,
        nombre=contenido.nombre,
        categoria_id=contenido.categoria_id,
        marca_id=contenido.marca_id,
        proveedor_id=contenido.proveedor_id,
        unidad_base=contenido.unidad_base,
        alicuota_id=contenido.alicuota_id,
        activo=contenido.activo,
        actor_id=sobre.usuario_id,
    )
    return "ACEPTADO", {"producto_id": str(producto.id)}, None


registrar_handler("PRODUCTO_MODIFICAR", 2, ProductoModificarContenidoV2)(
    manejar_producto_modificar  # type: ignore[arg-type]
)
declarar_tipo("PRODUCTO_MODIFICAR", admite_online=True, admite_offline=False)


# --- PRESENTACION_AGREGAR / PRESENTACION_MODIFICAR (CAT-02, CAT-04) --------


class PresentacionAgregarContenidoV1(BaseModel):
    producto_id: UUID
    nombre: str
    unidades_base: int
    usar_en_venta: bool
    usar_en_compra: bool


def manejar_presentacion_agregar(
    sobre: SobreComando, contenido: PresentacionAgregarContenidoV1, *, sesion: object, reloj: Clock
) -> ResultadoHandler:
    presentacion = catalogo_service.agregar_presentacion(
        sobre.organizacion_id,
        sesion,  # type: ignore[arg-type]
        reloj,
        producto_id=contenido.producto_id,
        nombre=contenido.nombre,
        unidades_base=contenido.unidades_base,
        usar_en_venta=contenido.usar_en_venta,
        usar_en_compra=contenido.usar_en_compra,
        actor_id=sobre.usuario_id,
    )
    return "ACEPTADO", {"presentacion_id": str(presentacion.id)}, None


registrar_handler("PRESENTACION_AGREGAR", 1, PresentacionAgregarContenidoV1)(
    manejar_presentacion_agregar  # type: ignore[arg-type]
)
declarar_tipo("PRESENTACION_AGREGAR", admite_online=True, admite_offline=False)


class PresentacionModificarContenidoV1(BaseModel):
    presentacion_id: UUID
    nombre: str
    unidades_base: int
    usar_en_venta: bool
    usar_en_compra: bool
    activo: bool


def manejar_presentacion_modificar(
    sobre: SobreComando,
    contenido: PresentacionModificarContenidoV1,
    *,
    sesion: object,
    reloj: Clock,
) -> ResultadoHandler:
    presentacion = catalogo_service.modificar_presentacion(
        sobre.organizacion_id,
        sesion,  # type: ignore[arg-type]
        reloj,
        presentacion_id=contenido.presentacion_id,
        nombre=contenido.nombre,
        unidades_base=contenido.unidades_base,
        usar_en_venta=contenido.usar_en_venta,
        usar_en_compra=contenido.usar_en_compra,
        activo=contenido.activo,
        actor_id=sobre.usuario_id,
    )
    return "ACEPTADO", {"presentacion_id": str(presentacion.id)}, None


registrar_handler("PRESENTACION_MODIFICAR", 1, PresentacionModificarContenidoV1)(
    manejar_presentacion_modificar  # type: ignore[arg-type]
)
declarar_tipo("PRESENTACION_MODIFICAR", admite_online=True, admite_offline=False)


# --- PRESENTACION_REFERENCIA_CAMBIAR (CAT-03, D5) --------------------------


class PresentacionReferenciaCambiarContenidoV1(BaseModel):
    producto_id: UUID
    presentacion_id: UUID


def manejar_presentacion_referencia_cambiar(
    sobre: SobreComando,
    contenido: PresentacionReferenciaCambiarContenidoV1,
    *,
    sesion: object,
    reloj: Clock,
) -> ResultadoHandler:
    presentacion = catalogo_service.cambiar_referencia(
        sobre.organizacion_id,
        sesion,  # type: ignore[arg-type]
        reloj,
        producto_id=contenido.producto_id,
        presentacion_id=contenido.presentacion_id,
        actor_id=sobre.usuario_id,
    )
    return "ACEPTADO", {"presentacion_id": str(presentacion.id)}, None


registrar_handler("PRESENTACION_REFERENCIA_CAMBIAR", 1, PresentacionReferenciaCambiarContenidoV1)(
    manejar_presentacion_referencia_cambiar  # type: ignore[arg-type]
)
declarar_tipo("PRESENTACION_REFERENCIA_CAMBIAR", admite_online=True, admite_offline=False)
