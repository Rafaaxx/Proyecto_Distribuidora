"""Handlers de comandos de `precios` (change 13, grupo 5; `design.md` D8, D9, D11, D12, D14;
plantilla D7 del change 04: un tipo de comando por escritura, un esquema de contenido versión
1, un handler de pocas líneas que llama al servicio, sin `commit` propio, que lo gestiona el
bus).

Diez tipos, todos `ONLINE` y `admite_offline=False` (`02` §6.5: listas, reglas, redondeos,
versiones y la lista predeterminada se administran con conexión). Los cinco primeros, con el
permiso `GESTIONAR_LISTAS` (`01` §19); generar el borrador y fijar un precio manual, también;
publicar y anular, con `PUBLICAR_LISTAS`; y la lista predeterminada, con `ADMIN_CONFIGURACION`
(`LISTA_PRECIO_PREDETERMINADA_DEFINIR`, change 13 grupo 10):

- `LISTA_PRECIO_CREAR`, `LISTA_PRECIO_MODIFICAR` -- la lista y su redondeo (PRC-01, PRC-14).
- `REGLA_MARGEN_CREAR`, `REGLA_MARGEN_MODIFICAR` -- las reglas de margen (PRC-12, PRC-13).
- `REDONDEO_CATEGORIA_DEFINIR` -- la sobrescritura del redondeo por categoría (PRC-14).

Los múltiplos y los valores de margen viajan como **string** (`CLAUDE.md` §4): el campo se
declara `str` y Pydantic no lo convierte desde un número JSON, así que un `100.0` mandado por
error se rechaza como contenido inválido en vez de perder exactitud (INV-03). `extra="forbid"`
rechaza lo que el comando no define: `organizacion_id` sale siempre del token (INV-21).

Mismo criterio que `catalogo/commands.py`: los handlers NO atrapan errores de dominio, los
dejan subir; el bus (`sync/service.py::procesar_comando`) revierte toda la transacción,
incluida la reserva del `operation_id`, y el comando puede reintentarse con contenido
corregido. El permiso se comprueba PRIMERO en cada handler, antes de leer o escribir nada: un
rechazo de permiso no deja nada a medias.

El bus escribe la fila de auditoría de cada comando ejecutado (`accion` = tipo, con el
`operation_id`), así que el handler no audita por su cuenta (AUD-01).
"""

from __future__ import annotations

from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict

from app.commands.catalogo import declarar_tipo
from app.commands.registro import registrar_handler
from app.commands.sobre import SobreComando
from app.core.clock import Clock
from app.core.errors import PermisoRequeridoError
from app.modules.identidad import service as identidad_service
from app.modules.precios import service as precios_service

ResultadoHandler = tuple[str, dict[str, object] | None, str | None]
"""Misma convención que `sync/service.py::ResultadoHandler` (ver `catalogo/commands.py` para
la justificación de no importarla de `sync`)."""

PERMISO_GESTIONAR_LISTAS = "GESTIONAR_LISTAS"
PERMISO_PUBLICAR_LISTAS = "PUBLICAR_LISTAS"
PERMISO_ADMIN_CONFIGURACION = "ADMIN_CONFIGURACION"


def _exigir_permiso(sobre: SobreComando, sesion: object, codigo_permiso: str) -> None:
    """Falla con 403 `PERMISO_REQUERIDO` si el usuario del sobre no tiene el permiso (SEG-06).
    Falla cerrada: un usuario inexistente, inactivo o con el rol inactivo no tiene ninguno."""
    permitidos = identidad_service.listar_permisos_del_usuario(
        sobre.organizacion_id,
        sobre.usuario_id,
        sesion,  # type: ignore[arg-type]
    )
    if codigo_permiso not in permitidos:
        raise PermisoRequeridoError(f"Falta el permiso {codigo_permiso}.")


class ContenidoPreciosV1(BaseModel):
    """Base de los contenidos de `precios`: `extra="forbid"` convierte un campo que el
    comando no define (por ejemplo, un `organizacion_id`) en `CONTENIDO_DE_COMANDO_INVALIDO`
    en vez de descartarlo en silencio."""

    model_config = ConfigDict(extra="forbid")


# --- LISTA_PRECIO_CREAR (PRC-01, PRC-14, D9) --------------------------------------------


class ListaPrecioCrearContenidoV1(ContenidoPreciosV1):
    nombre: str
    redondeo_multiplo: str
    redondeo_direccion: str


def manejar_lista_precio_crear(
    sobre: SobreComando,
    contenido: ListaPrecioCrearContenidoV1,
    *,
    sesion: object,
    reloj: Clock,
) -> ResultadoHandler:
    _exigir_permiso(sobre, sesion, PERMISO_GESTIONAR_LISTAS)
    lista = precios_service.crear_lista(
        sobre.organizacion_id,
        sesion,  # type: ignore[arg-type]
        reloj,
        nombre=contenido.nombre,
        redondeo_multiplo=contenido.redondeo_multiplo,
        redondeo_direccion=contenido.redondeo_direccion,
        actor_id=sobre.usuario_id,
    )
    return "ACEPTADO", {"lista_id": str(lista.id)}, None


registrar_handler("LISTA_PRECIO_CREAR", 1, ListaPrecioCrearContenidoV1)(
    manejar_lista_precio_crear  # type: ignore[arg-type]
)
declarar_tipo("LISTA_PRECIO_CREAR", admite_online=True, admite_offline=False)


# --- LISTA_PRECIO_MODIFICAR (PRC-01, PRC-04) --------------------------------------------


class ListaPrecioModificarContenidoV1(ContenidoPreciosV1):
    lista_id: UUID
    nombre: str
    redondeo_multiplo: str
    redondeo_direccion: str
    activo: bool


def manejar_lista_precio_modificar(
    sobre: SobreComando,
    contenido: ListaPrecioModificarContenidoV1,
    *,
    sesion: object,
    reloj: Clock,
) -> ResultadoHandler:
    _exigir_permiso(sobre, sesion, PERMISO_GESTIONAR_LISTAS)
    lista = precios_service.modificar_lista(
        sobre.organizacion_id,
        sesion,  # type: ignore[arg-type]
        reloj,
        lista_id=contenido.lista_id,
        nombre=contenido.nombre,
        redondeo_multiplo=contenido.redondeo_multiplo,
        redondeo_direccion=contenido.redondeo_direccion,
        activo=contenido.activo,
        actor_id=sobre.usuario_id,
    )
    return "ACEPTADO", {"lista_id": str(lista.id)}, None


registrar_handler("LISTA_PRECIO_MODIFICAR", 1, ListaPrecioModificarContenidoV1)(
    manejar_lista_precio_modificar  # type: ignore[arg-type]
)
declarar_tipo("LISTA_PRECIO_MODIFICAR", admite_online=True, admite_offline=False)


# --- REGLA_MARGEN_CREAR (PRC-12, PRC-13, D8) --------------------------------------------


class ReglaMargenCrearContenidoV1(ContenidoPreciosV1):
    lista_id: UUID
    tipo: str
    valor: str
    alcance_tipo: str
    alcance_id: UUID | None = None


def manejar_regla_margen_crear(
    sobre: SobreComando,
    contenido: ReglaMargenCrearContenidoV1,
    *,
    sesion: object,
    reloj: Clock,
) -> ResultadoHandler:
    _exigir_permiso(sobre, sesion, PERMISO_GESTIONAR_LISTAS)
    regla = precios_service.crear_regla(
        sobre.organizacion_id,
        sesion,  # type: ignore[arg-type]
        reloj,
        lista_id=contenido.lista_id,
        tipo=contenido.tipo,
        valor=contenido.valor,
        alcance_tipo=contenido.alcance_tipo,
        alcance_id=contenido.alcance_id,
        actor_id=sobre.usuario_id,
    )
    return "ACEPTADO", {"regla_id": str(regla.id), "lista_id": str(regla.lista_id)}, None


registrar_handler("REGLA_MARGEN_CREAR", 1, ReglaMargenCrearContenidoV1)(
    manejar_regla_margen_crear  # type: ignore[arg-type]
)
declarar_tipo("REGLA_MARGEN_CREAR", admite_online=True, admite_offline=False)


# --- REGLA_MARGEN_MODIFICAR (PRC-12, PRC-16) --------------------------------------------


class ReglaMargenModificarContenidoV1(ContenidoPreciosV1):
    """El alcance y la lista no cambian: no están entre los campos y `extra="forbid"` rechaza
    un `alcance_tipo` o un `alcance_id` mandado por error."""

    lista_id: UUID
    regla_id: UUID
    tipo: str
    valor: str
    activo: bool


def manejar_regla_margen_modificar(
    sobre: SobreComando,
    contenido: ReglaMargenModificarContenidoV1,
    *,
    sesion: object,
    reloj: Clock,
) -> ResultadoHandler:
    _exigir_permiso(sobre, sesion, PERMISO_GESTIONAR_LISTAS)
    regla = precios_service.modificar_regla(
        sobre.organizacion_id,
        sesion,  # type: ignore[arg-type]
        reloj,
        lista_id=contenido.lista_id,
        regla_id=contenido.regla_id,
        tipo=contenido.tipo,
        valor=contenido.valor,
        activo=contenido.activo,
        actor_id=sobre.usuario_id,
    )
    return "ACEPTADO", {"regla_id": str(regla.id), "lista_id": str(regla.lista_id)}, None


registrar_handler("REGLA_MARGEN_MODIFICAR", 1, ReglaMargenModificarContenidoV1)(
    manejar_regla_margen_modificar  # type: ignore[arg-type]
)
declarar_tipo("REGLA_MARGEN_MODIFICAR", admite_online=True, admite_offline=False)


# --- REDONDEO_CATEGORIA_DEFINIR (PRC-14, D9) --------------------------------------------


class RedondeoCategoriaDefinirContenidoV1(ContenidoPreciosV1):
    lista_id: UUID
    categoria_id: UUID
    multiplo: str
    direccion: str
    activo: bool = True


def manejar_redondeo_categoria_definir(
    sobre: SobreComando,
    contenido: RedondeoCategoriaDefinirContenidoV1,
    *,
    sesion: object,
    reloj: Clock,
) -> ResultadoHandler:
    _exigir_permiso(sobre, sesion, PERMISO_GESTIONAR_LISTAS)
    redondeo = precios_service.definir_redondeo_categoria(
        sobre.organizacion_id,
        sesion,  # type: ignore[arg-type]
        reloj,
        lista_id=contenido.lista_id,
        categoria_id=contenido.categoria_id,
        multiplo=contenido.multiplo,
        direccion=contenido.direccion,
        activo=contenido.activo,
        actor_id=sobre.usuario_id,
    )
    return (
        "ACEPTADO",
        {
            "redondeo_id": str(redondeo.id),
            "lista_id": str(redondeo.lista_id),
            "categoria_id": str(redondeo.categoria_id),
        },
        None,
    )


registrar_handler("REDONDEO_CATEGORIA_DEFINIR", 1, RedondeoCategoriaDefinirContenidoV1)(
    manejar_redondeo_categoria_definir  # type: ignore[arg-type]
)
declarar_tipo("REDONDEO_CATEGORIA_DEFINIR", admite_online=True, admite_offline=False)


# --- LISTA_GENERAR_BORRADOR (PRC-17, D4, D5) --------------------------------------------


class ListaGenerarBorradorContenidoV1(ContenidoPreciosV1):
    lista_id: UUID


def manejar_lista_generar_borrador(
    sobre: SobreComando,
    contenido: ListaGenerarBorradorContenidoV1,
    *,
    sesion: object,
    reloj: Clock,
) -> ResultadoHandler:
    _exigir_permiso(sobre, sesion, PERMISO_GESTIONAR_LISTAS)
    resultado = precios_service.generar_borrador(
        sobre.organizacion_id,
        sesion,  # type: ignore[arg-type]
        reloj,
        lista_id=contenido.lista_id,
        actor_id=sobre.usuario_id,
        operation_id=sobre.operation_id,
    )
    return (
        "ACEPTADO",
        {
            "version_id": str(resultado.version_id),
            "numero": resultado.numero,
            "regenerado": resultado.regenerado,
            "cantidad_precios": resultado.cantidad_precios,
            "productos_sin_precio": [
                {"producto_id": str(sin.producto_id), "causa": sin.causa}
                for sin in resultado.productos_sin_precio
            ],
            "precios_con_otra_regla_iva": resultado.precios_con_otra_regla_iva,
            "precios_con_costos_distintos": resultado.precios_con_costos_distintos,
        },
        None,
    )


registrar_handler("LISTA_GENERAR_BORRADOR", 1, ListaGenerarBorradorContenidoV1)(
    manejar_lista_generar_borrador  # type: ignore[arg-type]
)
declarar_tipo("LISTA_GENERAR_BORRADOR", admite_online=True, admite_offline=False)


# --- LISTA_BORRADOR_PRECIO_FIJAR (PRC-16, D7) -------------------------------------------


class ListaBorradorPrecioFijarContenidoV1(ContenidoPreciosV1):
    """`precio_final` es obligatorio y puede ser nulo: un importe lo fija a mano, `null` quita
    la marca manual y el precio vuelve a calcularse (D7). Omitirlo es un contenido inválido,
    para no quitar la marca en silencio."""

    lista_id: UUID
    version_id: UUID
    producto_id: UUID
    precio_final: str | None


def manejar_lista_borrador_precio_fijar(
    sobre: SobreComando,
    contenido: ListaBorradorPrecioFijarContenidoV1,
    *,
    sesion: object,
    reloj: Clock,
) -> ResultadoHandler:
    _exigir_permiso(sobre, sesion, PERMISO_GESTIONAR_LISTAS)
    resultado = precios_service.fijar_precio_manual(
        sobre.organizacion_id,
        sesion,  # type: ignore[arg-type]
        reloj,
        lista_id=contenido.lista_id,
        version_id=contenido.version_id,
        producto_id=contenido.producto_id,
        precio_final=contenido.precio_final,
    )
    return (
        "ACEPTADO",
        {
            "version_id": str(resultado.version_id),
            "producto_id": str(resultado.producto_id),
            "precio_final": None if resultado.precio_final is None else str(resultado.precio_final),
            "manual": resultado.manual,
        },
        None,
    )


registrar_handler("LISTA_BORRADOR_PRECIO_FIJAR", 1, ListaBorradorPrecioFijarContenidoV1)(
    manejar_lista_borrador_precio_fijar  # type: ignore[arg-type]
)
declarar_tipo("LISTA_BORRADOR_PRECIO_FIJAR", admite_online=True, admite_offline=False)


# --- LISTA_PUBLICAR (PRC-02, PRC-06, D6) ------------------------------------------------


class ListaPublicarContenidoV1(ContenidoPreciosV1):
    """Las vigencias son instantes con zona horaria (`AwareDatetime`): una fecha sin zona no
    dice qué instante es y se rechaza como contenido inválido. `vigencia_desde` nula significa
    "ahora" (D6); ambas son obligatorias en el contenido aunque puedan ser nulas, para que el
    contenido auditado diga siempre con qué vigencia se publicó."""

    lista_id: UUID
    version_id: UUID
    vigencia_desde: AwareDatetime | None
    vigencia_hasta: AwareDatetime | None


def manejar_lista_publicar(
    sobre: SobreComando,
    contenido: ListaPublicarContenidoV1,
    *,
    sesion: object,
    reloj: Clock,
) -> ResultadoHandler:
    _exigir_permiso(sobre, sesion, PERMISO_PUBLICAR_LISTAS)
    resultado = precios_service.publicar_version(
        sobre.organizacion_id,
        sesion,  # type: ignore[arg-type]
        reloj,
        lista_id=contenido.lista_id,
        version_id=contenido.version_id,
        vigencia_desde=contenido.vigencia_desde,
        vigencia_hasta=contenido.vigencia_hasta,
        actor_id=sobre.usuario_id,
    )
    return (
        "ACEPTADO",
        {
            "version_id": str(resultado.version_id),
            "numero": resultado.numero,
            "vigencia_desde": resultado.vigencia_desde.isoformat(),
            "vigencia_hasta": (
                None if resultado.vigencia_hasta is None else resultado.vigencia_hasta.isoformat()
            ),
            "cantidad_precios": resultado.cantidad_precios,
        },
        None,
    )


registrar_handler("LISTA_PUBLICAR", 1, ListaPublicarContenidoV1)(
    manejar_lista_publicar  # type: ignore[arg-type]
)
declarar_tipo("LISTA_PUBLICAR", admite_online=True, admite_offline=False)


# --- LISTA_ANULAR_VERSION (PRC-05, PRC-06) ----------------------------------------------


class ListaAnularVersionContenidoV1(ContenidoPreciosV1):
    lista_id: UUID
    version_id: UUID


def manejar_lista_anular_version(
    sobre: SobreComando,
    contenido: ListaAnularVersionContenidoV1,
    *,
    sesion: object,
    reloj: Clock,
) -> ResultadoHandler:
    _exigir_permiso(sobre, sesion, PERMISO_PUBLICAR_LISTAS)
    resultado = precios_service.anular_version(
        sobre.organizacion_id,
        sesion,  # type: ignore[arg-type]
        reloj,
        lista_id=contenido.lista_id,
        version_id=contenido.version_id,
        actor_id=sobre.usuario_id,
    )
    return "ACEPTADO", {"version_id": str(resultado.version_id), "numero": resultado.numero}, None


registrar_handler("LISTA_ANULAR_VERSION", 1, ListaAnularVersionContenidoV1)(
    manejar_lista_anular_version  # type: ignore[arg-type]
)
declarar_tipo("LISTA_ANULAR_VERSION", admite_online=True, admite_offline=False)


# --- LISTA_PRECIO_PREDETERMINADA_DEFINIR (PRC-20, D11 punto 2) --------------------------


class ListaPrecioPredeterminadaDefinirContenidoV1(ContenidoPreciosV1):
    """Solo la lista elegida: `organizacion_id` sale del token (INV-21)."""

    lista_id: UUID


def manejar_lista_precio_predeterminada_definir(
    sobre: SobreComando,
    contenido: ListaPrecioPredeterminadaDefinirContenidoV1,
    *,
    sesion: object,
    reloj: Clock,
) -> ResultadoHandler:
    """Con `ADMIN_CONFIGURACION` (no `GESTIONAR_LISTAS`: lo que se toca es la configuración
    de la organización, mismo criterio que `CLIENTE_CONSUMIDOR_FINAL_CONFIGURAR`, SEG-06). La
    auditoría con valor anterior y nuevo la escribe `identidad/service.py` (AUD-01)."""
    _exigir_permiso(sobre, sesion, PERMISO_ADMIN_CONFIGURACION)
    precios_service.definir_lista_predeterminada(
        sobre.organizacion_id,
        sesion,  # type: ignore[arg-type]
        reloj,
        lista_id=contenido.lista_id,
        actor_id=sobre.usuario_id,
        dispositivo_id_actor=sobre.dispositivo_id,
        operation_id=sobre.operation_id,
    )
    return "ACEPTADO", {"lista_id": str(contenido.lista_id)}, None


registrar_handler(
    "LISTA_PRECIO_PREDETERMINADA_DEFINIR", 1, ListaPrecioPredeterminadaDefinirContenidoV1
)(
    manejar_lista_precio_predeterminada_definir  # type: ignore[arg-type]
)
declarar_tipo("LISTA_PRECIO_PREDETERMINADA_DEFINIR", admite_online=True, admite_offline=False)
