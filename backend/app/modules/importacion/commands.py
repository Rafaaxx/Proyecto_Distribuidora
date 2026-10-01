"""Handler del comando `IMPORTACION_REGISTRAR` v1 (change 10, grupo 4, tarea 4.1;
`design.md` D1, D10, D14; plantilla D7 del change 04 y `stock/commands.py`).

Un tipo, `ONLINE` y `admite_offline=False` (`02` §6.5): exige `sesion` y `reloj` como
parámetros de palabra clave y escribe en la base del servidor. Permiso
`IMPORTAR_DATOS` (`01` §19, ADR-033, ADR-036).

El permiso se comprueba ACÁ y primero: el catálogo de tipos no modela permisos y un
lote de sincronización trae tipos distintos, así que el punto donde se puede
comprobar es el handler (mismo criterio que `stock/commands.py`). Un rechazo de
permiso no deja efecto, ni reserva del `operation_id`, ni auditoría: el bus revierte
la transacción entera.

Todo o nada (D1, INV-01): el importador del tipo escribe cada fila por el servicio
del módulo dueño dentro de un savepoint y devuelve los errores por fila. Si hubo
alguno, el handler lanza `IMPORTACION_CON_ERRORES` con la lista completa y el bus
revierte TODO, incluida la reserva del `operation_id`; sin errores inserta la fila de
`importacion` y el bus confirma. Los handlers no atrapan errores de dominio ni
confirman: la única auditoría es la del bus (ADR-022).

`organizacion_id`, `usuario_id`, `dispositivo_id` y `occurred_at` salen del sobre
(TR-05, INV-21), nunca del contenido.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr

from app.commands.catalogo import declarar_tipo
from app.commands.registro import registrar_handler
from app.commands.sobre import SobreComando
from app.core.clock import Clock
from app.core.errors import PermisoRequeridoError
from app.core.ids import nuevo_id
from app.modules.identidad import service as identidad_service
from app.modules.importacion import repository
from app.modules.importacion.domain.errores import TipoImportacionInvalidoError
from app.modules.importacion.domain.informe import error_agregado
from app.modules.importacion.domain.planilla import (
    LIMITE_DE_FILAS,
    FilaPlanilla,
    verificar_columnas_de_filas,
)
from app.modules.importacion.importadores import IMPORTADORES
from app.modules.importacion.importadores.base import ContextoDeImportacion

ResultadoHandler = tuple[str, dict[str, object] | None, str | None]
"""Misma convención que `sync/service.py::ResultadoHandler` (ver
`catalogo/commands.py` para la justificación de no importarla de `sync`)."""

PERMISO_IMPORTAR = "IMPORTAR_DATOS"


def _exigir_permiso(sobre: SobreComando, sesion: object, codigo_permiso: str) -> None:
    """Falla con 403 `PERMISO_REQUERIDO` si el usuario del sobre no tiene el permiso
    (INV-01, SEG-06). Va PRIMERO: un rechazo no puede dejar nada escrito."""
    permitidos = identidad_service.listar_permisos_del_usuario(
        sobre.organizacion_id,
        sobre.usuario_id,
        sesion,  # type: ignore[arg-type]
    )
    if codigo_permiso not in permitidos:
        raise PermisoRequeridoError(f"Falta el permiso {codigo_permiso}.")


class FilaContenidoV1(BaseModel):
    """Una fila de la planilla: su número tal como la ve el usuario (el encabezado es
    la 1) y un texto por columna. La conversión a decimal, entero o fecha ocurre en el
    importador (INV-03)."""

    model_config = ConfigDict(extra="forbid")

    fila: StrictInt
    valores: dict[str, StrictStr]


class ImportacionRegistrarContenidoV1(BaseModel):
    """`tipo`, `archivo_nombre` y `filas` (1 a 2.000, `design.md` D11).
    `extra="forbid"`: `organizacion_id` sale del token y el estado lo decide el
    handler. `tipo` es texto libre acá: lo valida el handler contra los importadores
    registrados (`PRECIOS` y los desconocidos son `TIPO_IMPORTACION_INVALIDO`)."""

    model_config = ConfigDict(extra="forbid")

    tipo: StrictStr
    archivo_nombre: StrictStr = Field(min_length=1, max_length=255)
    filas: list[FilaContenidoV1] = Field(min_length=1, max_length=LIMITE_DE_FILAS)


def manejar_importacion_registrar(
    sobre: SobreComando,
    contenido: ImportacionRegistrarContenidoV1,
    *,
    sesion: object,
    reloj: Clock,
) -> ResultadoHandler:
    _exigir_permiso(sobre, sesion, PERMISO_IMPORTAR)
    importador = IMPORTADORES.get(contenido.tipo)
    if importador is None:
        raise TipoImportacionInvalidoError(
            f"El tipo de importación {contenido.tipo!r} no es válido o todavía no está disponible."
        )
    filas = [FilaPlanilla(fila=f.fila, valores=dict(f.valores)) for f in contenido.filas]
    verificar_columnas_de_filas(contenido.tipo, filas)

    errores = importador(
        ContextoDeImportacion(
            organizacion_id=sobre.organizacion_id,
            sesion=sesion,  # type: ignore[arg-type]
            reloj=reloj,
            usuario_id=sobre.usuario_id,
            dispositivo_id=sobre.dispositivo_id,
            operation_id=sobre.operation_id,
            occurred_at=sobre.occurred_at,
        ),
        filas,
    )
    if errores:
        raise error_agregado(errores)

    importacion = repository.crear_importacion(
        sobre.organizacion_id,
        sesion,  # type: ignore[arg-type]
        importacion_id=nuevo_id(),
        tipo=contenido.tipo,
        archivo_nombre=contenido.archivo_nombre,
        filas_total=len(filas),
        filas_ok=len(filas),
        operation_id=sobre.operation_id,
        usuario_id=sobre.usuario_id,
        dispositivo_id=sobre.dispositivo_id,
        occurred_at=sobre.occurred_at,
        registered_at=reloj.now(),
    )
    return (
        "ACEPTADO",
        {
            "importacion_id": str(importacion.id),
            "filas_total": importacion.filas_total,
            "filas_ok": importacion.filas_ok,
        },
        None,
    )


registrar_handler("IMPORTACION_REGISTRAR", 1, ImportacionRegistrarContenidoV1)(
    manejar_importacion_registrar  # type: ignore[arg-type]
)
declarar_tipo("IMPORTACION_REGISTRAR", admite_online=True, admite_offline=False)
