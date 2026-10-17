"""Handlers de comandos de `descuentos` (change 16, grupo 8; `design.md` D15, D16, D18; plantilla
D7 del change 04: un tipo de comando por escritura, un esquema de contenido versión 1, un handler
de pocas líneas que llama al servicio, sin `commit` propio, que lo gestiona el bus).

Cuatro tipos, todos `ONLINE` y `admite_offline=False` (`02` §6.5: las reglas se administran con
conexión), con el permiso `GESTIONAR_DESCUENTOS` (`01` §19):

- `REGLA_DESCUENTO_CREAR` -- una regla nueva, siempre en `BORRADOR` (DSC-01).
- `REGLA_DESCUENTO_MODIFICAR` -- reemplaza un borrador; en una regla activada o pausada solo fija
  la vigencia hasta (D15).
- `REGLA_DESCUENTO_ACTIVAR` y `REGLA_DESCUENTO_PAUSAR` -- la máquina `BORRADOR → ACTIVA ↔
  PAUSADA` (`01` §18).

El umbral y el valor de la acción viajan como **string** (`CLAUDE.md` §4): el campo se declara
`str` y Pydantic no lo convierte desde un número JSON, así que un `0.05` mandado por error se
rechaza como contenido inválido en vez de perder exactitud (INV-03). `extra="forbid"` rechaza lo
que el comando no define: `organizacion_id` sale siempre del token (INV-21).

Los handlers NO atrapan errores de dominio, los dejan subir; el bus revierte toda la transacción,
incluida la reserva del `operation_id`. El permiso se comprueba PRIMERO en cada handler, antes de
leer o escribir nada. El bus escribe la fila de auditoría de cada comando aceptado (AUD-01), así
que ningún handler devuelve datos de auditoría propios.
"""

from __future__ import annotations

from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, StrictInt

from app.commands.catalogo import declarar_tipo
from app.commands.registro import SesionDeHandler, registrar_handler
from app.commands.sobre import SobreComando
from app.core.clock import Clock
from app.core.errors import PermisoRequeridoError
from app.modules.descuentos import service as descuentos_service
from app.modules.descuentos.domain.reglas import AlcanceNuevo
from app.modules.identidad import service as identidad_service

ResultadoHandler = tuple[str, dict[str, object] | None, str | None]
"""Misma convención que `sync/service.py::ResultadoHandler` (ver `catalogo/commands.py` para la
justificación de no importarla de `sync`)."""

PERMISO_GESTIONAR_DESCUENTOS = "GESTIONAR_DESCUENTOS"


def _exigir_permiso(sobre: SobreComando, sesion: SesionDeHandler, codigo_permiso: str) -> None:
    """Falla con 403 `PERMISO_REQUERIDO` si el usuario del sobre no tiene el permiso (SEG-06).
    Falla cerrada: un usuario inexistente, inactivo o con el rol inactivo no tiene ninguno."""
    permitidos = identidad_service.listar_permisos_del_usuario(
        sobre.organizacion_id,
        sobre.usuario_id,
        sesion,
    )
    if codigo_permiso not in permitidos:
        raise PermisoRequeridoError(f"Falta el permiso {codigo_permiso}.")


class ContenidoDescuentosV1(BaseModel):
    """Base de los contenidos de `descuentos`: `extra="forbid"` convierte un campo que el
    comando no define (por ejemplo, un `organizacion_id`) en `CONTENIDO_DE_COMANDO_INVALIDO` en
    vez de descartarlo en silencio."""

    model_config = ConfigDict(extra="forbid")


class AlcanceContenidoV1(ContenidoDescuentosV1):
    """Un alcance de la regla: `tipo` es `PRODUCTO`, `CATEGORIA` o `MARCA` (lo valida el
    dominio, `ALCANCE_INVALIDO`) y `entidad_id` su identificador."""

    tipo: str
    entidad_id: UUID


def _alcances(contenido: list[AlcanceContenidoV1] | None) -> list[AlcanceNuevo]:
    return [AlcanceNuevo(a.tipo, a.entidad_id) for a in contenido or []]


# --- REGLA_DESCUENTO_CREAR (DSC-01 a DSC-04) --------------------------------------------


class ReglaDescuentoCrearContenidoV1(ContenidoDescuentosV1):
    """`prioridad` es un entero estricto: el contenido de un comando no admite números con coma
    (`commands/huella.py`); el rechazo con `PRIORIDAD_INVALIDA` de un decimal lo hace la ruta HTTP
    antes de armar el sobre."""

    nombre: str
    tipo: str
    medida: str
    operador: str
    umbral: str
    accion_tipo: str
    accion_valor: str
    prioridad: StrictInt
    acumulable: bool
    alcances: list[AlcanceContenidoV1] = []
    vigencia_desde: AwareDatetime | None = None
    vigencia_hasta: AwareDatetime | None = None


def manejar_regla_descuento_crear(
    sobre: SobreComando,
    contenido: ReglaDescuentoCrearContenidoV1,
    *,
    sesion: SesionDeHandler,
    reloj: Clock,
) -> ResultadoHandler:
    _exigir_permiso(sobre, sesion, PERMISO_GESTIONAR_DESCUENTOS)
    regla = descuentos_service.crear_regla(
        sobre.organizacion_id,
        sesion,
        reloj,
        datos=descuentos_service.DatosDeRegla(
            nombre=contenido.nombre,
            tipo=contenido.tipo,
            medida=contenido.medida,
            operador=contenido.operador,
            umbral=contenido.umbral,
            accion_tipo=contenido.accion_tipo,
            accion_valor=contenido.accion_valor,
            prioridad=contenido.prioridad,
            acumulable=contenido.acumulable,
            alcances=_alcances(contenido.alcances),
            vigencia_desde=contenido.vigencia_desde,
            vigencia_hasta=contenido.vigencia_hasta,
        ),
        actor_id=sobre.usuario_id,
    )
    return "ACEPTADO", {"regla_id": str(regla.id)}, None


registrar_handler("REGLA_DESCUENTO_CREAR", 1, ReglaDescuentoCrearContenidoV1)(
    manejar_regla_descuento_crear
)
declarar_tipo("REGLA_DESCUENTO_CREAR", admite_online=True, admite_offline=False)


# --- REGLA_DESCUENTO_MODIFICAR (D15, D16) -----------------------------------------------


class ReglaDescuentoModificarContenidoV1(ContenidoDescuentosV1):
    """Un borrador se reemplaza con todos los campos del alta; una regla activada o pausada solo
    admite `vigencia_hasta` (D15). Todos son opcionales en el formato: qué campos vinieron
    (`model_fields_set`) decide qué se hace, y `null` en `vigencia_hasta` quita el fin."""

    regla_id: UUID
    nombre: str | None = None
    tipo: str | None = None
    medida: str | None = None
    operador: str | None = None
    umbral: str | None = None
    accion_tipo: str | None = None
    accion_valor: str | None = None
    prioridad: StrictInt | None = None
    acumulable: bool | None = None
    alcances: list[AlcanceContenidoV1] | None = None
    vigencia_desde: AwareDatetime | None = None
    vigencia_hasta: AwareDatetime | None = None


def manejar_regla_descuento_modificar(
    sobre: SobreComando,
    contenido: ReglaDescuentoModificarContenidoV1,
    *,
    sesion: SesionDeHandler,
    reloj: Clock,
) -> ResultadoHandler:
    _exigir_permiso(sobre, sesion, PERMISO_GESTIONAR_DESCUENTOS)
    regla = descuentos_service.modificar_regla(
        sobre.organizacion_id,
        sesion,
        reloj,
        regla_id=contenido.regla_id,
        cambios=descuentos_service.CambiosDeRegla(
            campos=frozenset(contenido.model_fields_set - {"regla_id"}),
            nombre=contenido.nombre,
            tipo=contenido.tipo,
            medida=contenido.medida,
            operador=contenido.operador,
            umbral=contenido.umbral,
            accion_tipo=contenido.accion_tipo,
            accion_valor=contenido.accion_valor,
            prioridad=contenido.prioridad,
            acumulable=contenido.acumulable,
            alcances=None if contenido.alcances is None else _alcances(contenido.alcances),
            vigencia_desde=contenido.vigencia_desde,
            vigencia_hasta=contenido.vigencia_hasta,
        ),
        actor_id=sobre.usuario_id,
    )
    return "ACEPTADO", {"regla_id": str(regla.id)}, None


registrar_handler("REGLA_DESCUENTO_MODIFICAR", 1, ReglaDescuentoModificarContenidoV1)(
    manejar_regla_descuento_modificar
)
declarar_tipo("REGLA_DESCUENTO_MODIFICAR", admite_online=True, admite_offline=False)


# --- REGLA_DESCUENTO_ACTIVAR y REGLA_DESCUENTO_PAUSAR (`01` §18) ------------------------


class ReglaDescuentoTransicionContenidoV1(ContenidoDescuentosV1):
    regla_id: UUID


def manejar_regla_descuento_activar(
    sobre: SobreComando,
    contenido: ReglaDescuentoTransicionContenidoV1,
    *,
    sesion: SesionDeHandler,
    reloj: Clock,
) -> ResultadoHandler:
    _exigir_permiso(sobre, sesion, PERMISO_GESTIONAR_DESCUENTOS)
    regla = descuentos_service.activar_regla(
        sobre.organizacion_id,
        sesion,
        reloj,
        regla_id=contenido.regla_id,
        actor_id=sobre.usuario_id,
    )
    return "ACEPTADO", {"regla_id": str(regla.id)}, None


registrar_handler("REGLA_DESCUENTO_ACTIVAR", 1, ReglaDescuentoTransicionContenidoV1)(
    manejar_regla_descuento_activar
)
declarar_tipo("REGLA_DESCUENTO_ACTIVAR", admite_online=True, admite_offline=False)


def manejar_regla_descuento_pausar(
    sobre: SobreComando,
    contenido: ReglaDescuentoTransicionContenidoV1,
    *,
    sesion: SesionDeHandler,
    reloj: Clock,
) -> ResultadoHandler:
    _exigir_permiso(sobre, sesion, PERMISO_GESTIONAR_DESCUENTOS)
    regla = descuentos_service.pausar_regla(
        sobre.organizacion_id,
        sesion,
        reloj,
        regla_id=contenido.regla_id,
        actor_id=sobre.usuario_id,
    )
    return "ACEPTADO", {"regla_id": str(regla.id)}, None


registrar_handler("REGLA_DESCUENTO_PAUSAR", 1, ReglaDescuentoTransicionContenidoV1)(
    manejar_regla_descuento_pausar
)
declarar_tipo("REGLA_DESCUENTO_PAUSAR", admite_online=True, admite_offline=False)
