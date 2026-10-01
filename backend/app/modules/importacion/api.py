"""Endpoints de `importacion` (change 10, grupo 4, tarea 4.3; `design.md` D1, D2, D9,
D11, D14).

**Escritura** (una, con su ruta DEDICADA, mismo patrón que `stock/api.py`):
`POST /importaciones/{tipo}` (`IMPORTACION_REGISTRAR`), multipart con el archivo en el
campo `archivo`. El despacho genérico de `POST /sync/comandos` no ejecuta handlers
`ONLINE` (deuda nominada al change 17), así que la ruta declara `requiere_comando_online`
(exige `Operation-Id`, SYN-01/TR-07) y delega en `sync_service.procesar_comando`. El
permiso `IMPORTAR_DATOS` se declara en la ruta para el ratchet y el handler lo vuelve a
comprobar primero (un lote de sincronización llega por otro camino).

La API lee el archivo (CSV o `.xlsx`), valida el encabezado y arma las filas como TEXTO
(`{fila, valores}`); ese JSON es el contenido del sobre, así que el mismo archivo da la
misma huella (D2). La conversión a decimales y enteros y las reglas de cada fila las
aplica el importador del tipo por los servicios de los demás módulos. Un archivo que no
se puede leer, con otras columnas, vacío o demasiado grande se rechaza completo antes de
tocar la base (422).

**Lecturas**: `GET /importaciones` (historial paginado por cursor, límite 1 a 200 como
error de validación y no recorte silencioso) y `GET /importaciones/plantillas/{tipo}` (CSV
con solo el encabezado). Todas con `IMPORTAR_DATOS` (`01` §19).

`organizacion_id` sale siempre del token (INV-21): el historial solo lista las
importaciones de la organización del token.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, Query, Response, UploadFile
from sqlalchemy.orm import Session

from app.api_v1.dependencias import get_session
from app.commands import registro
from app.commands.huella import ContenidoComando, calcular_huella
from app.commands.sobre import construir_sobre_online
from app.core.autenticacion import (
    ContextoAutenticado,
    EntradaComandoOnline,
    requiere_comando_online,
    requiere_permiso,
)
from app.core.clock import SystemClock
from app.modules.importacion import commands as importacion_commands
from app.modules.importacion import queries
from app.modules.importacion.domain.errores import (
    ArchivoDemasiadoGrandeError,
    TipoImportacionInvalidoError,
)
from app.modules.importacion.domain.historial import LIMITE_DEFAULT, LIMITE_MAXIMO
from app.modules.importacion.domain.planilla import (
    LIMITE_DE_BYTES,
    armar_planilla,
    columnas_de,
    nombre_de_archivo,
    plantilla_csv,
)
from app.modules.importacion.importadores import IMPORTADORES
from app.modules.importacion.lectores import leer_archivo
from app.modules.importacion.schemas import (
    ImportacionResponse,
    PaginaImportaciones,
    item_de,
)
from app.modules.sync import service as sync_service

PERMISO_IMPORTAR = "IMPORTAR_DATOS"

router = APIRouter(prefix="/importaciones", tags=["importacion"])

_BOM_UTF8 = b"\xef\xbb\xbf"


@router.post("/{tipo}", response_model=ImportacionResponse, status_code=201)
def importar(
    tipo: str,
    archivo: Annotated[UploadFile, File()],
    entrada: Annotated[EntradaComandoOnline, Depends(requiere_comando_online(PERMISO_IMPORTAR))],
    sesion: Annotated[Session, Depends(get_session)],
) -> ImportacionResponse:
    """Importa una planilla. Todo o nada (D1): 201 con el resultado, o 422
    `IMPORTACION_CON_ERRORES` con todos los errores por fila y ningún efecto."""
    if tipo not in IMPORTADORES:
        # `PRECIOS` (hasta el change 13), los desconocidos y los tipos que todavía no
        # tienen importador (D9): se rechazan sin leer el archivo.
        raise TipoImportacionInvalidoError(
            f"El tipo de importación {tipo!r} no es válido o todavía no está disponible."
        )
    nombre = nombre_de_archivo(archivo.filename)
    # Un byte de más que el límite basta para saber que se pasó, sin leer el resto.
    datos = archivo.file.read(LIMITE_DE_BYTES + 1)
    if len(datos) > LIMITE_DE_BYTES:
        raise ArchivoDemasiadoGrandeError(
            f"El archivo supera el máximo de {LIMITE_DE_BYTES // (1024 * 1024)} MB."
        )
    planilla = armar_planilla(tipo, leer_archivo(nombre, datos))

    reloj = SystemClock()
    contenido: dict[str, ContenidoComando] = {
        "tipo": tipo,
        "archivo_nombre": nombre,
        "filas": [{"fila": f.fila, "valores": dict(f.valores)} for f in planilla],
    }
    sobre = construir_sobre_online(
        operation_id=entrada.operation_id,
        tipo="IMPORTACION_REGISTRAR",
        version=1,
        modo="ONLINE",
        organizacion_id=entrada.contexto.organizacion_id,
        usuario_id=entrada.contexto.usuario_id,
        dispositivo_id=entrada.contexto.dispositivo_id,
        occurred_at=reloj.now(),
        secuencia=1,
        app_version="server",
        contenido=contenido,
    )
    huella = calcular_huella(sobre.contenido)
    handler_registrado = registro.resolver_handler(sobre.tipo, sobre.version)
    contenido_validado = registro.validar_contenido(handler_registrado, sobre.contenido)

    def _ejecutar_handler(sesion_protegida: object) -> sync_service.ResultadoHandler:
        return importacion_commands.manejar_importacion_registrar(
            sobre,
            contenido_validado,  # type: ignore[arg-type]
            sesion=sesion_protegida,
            reloj=reloj,
        )

    comando = sync_service.procesar_comando(
        sesion, reloj, sobre=sobre, huella=huella, ejecutar_handler=_ejecutar_handler
    )
    assert comando.resultado is not None
    return ImportacionResponse.model_validate(comando.resultado)


@router.get("", response_model=PaginaImportaciones)
def listar_importaciones(
    contexto: Annotated[ContextoAutenticado, Depends(requiere_permiso(PERMISO_IMPORTAR))],
    sesion: Annotated[Session, Depends(get_session)],
    cursor: str | None = None,
    limite: Annotated[int, Query(ge=1, le=LIMITE_MAXIMO)] = LIMITE_DEFAULT,
) -> PaginaImportaciones:
    """Historial de importaciones de la organización, la más reciente primero,
    paginado por cursor. Un `limite` fuera de 1 a 200 es un error de validación (422),
    no un recorte silencioso."""
    pagina = queries.listar_importaciones(
        contexto.organizacion_id, sesion, cursor=cursor, limite=limite
    )
    return PaginaImportaciones(
        items=[item_de(i) for i in pagina.items],
        cursor_siguiente=pagina.cursor_siguiente,
        zona_horaria=pagina.zona_horaria,
    )


@router.get("/plantillas/{tipo}")
def descargar_plantilla(
    tipo: str,
    contexto: Annotated[ContextoAutenticado, Depends(requiere_permiso(PERMISO_IMPORTAR))],
) -> Response:
    """Plantilla CSV del tipo: solo el encabezado exacto, en UTF-8 con BOM y `;` para
    que Excel en español la abra bien. La plantilla se puede importar sin errores de
    columnas."""
    del contexto  # el permiso es lo único que se necesita de la sesión
    columnas_de(tipo)  # `TIPO_IMPORTACION_INVALIDO` si no existe (p. ej. `PRECIOS`)
    cuerpo = _BOM_UTF8 + plantilla_csv(tipo).encode("utf-8")
    return Response(
        content=cuerpo,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="plantilla-{tipo.lower()}.csv"'},
    )
