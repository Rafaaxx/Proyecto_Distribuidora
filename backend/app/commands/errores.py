"""Errores de dominio del bus de comandos (`CLAUDE.md` §5: clases propias
con código estable, no excepciones genéricas).

No importa FastAPI ni SQLAlchemy (`design.md` D3): son errores de dominio
puro, traducidos a HTTP por la capa de API (`docs/02-arquitectura.md` §11).
"""

from __future__ import annotations

from app.core.errors import DomainError


class TipoDeComandoDesconocidoError(DomainError):
    """El tipo de comando no tiene ninguna versión registrada (SYN-06)."""

    codigo = "TIPO_DE_COMANDO_DESCONOCIDO"


class VersionDeComandoSinHandlerError(DomainError):
    """El tipo existe pero la versión pedida no tiene handler (`02` §6.6,
    SYN-06)."""

    codigo = "VERSION_DE_COMANDO_SIN_HANDLER"


class ContenidoDeComandoInvalidoError(DomainError):
    """El contenido no cumple el esquema declarado para su tipo y versión
    (SYN-06, `02` §6.3): se rechaza como malformado, sin efectos."""

    codigo = "CONTENIDO_DE_COMANDO_INVALIDO"


class ComandoInconsistenteError(DomainError):
    """Mismo `operation_id`, huella distinta (SYN-02, SYN-06): el resultado
    original queda intacto."""

    codigo = "COMANDO_INCONSISTENTE"
    status_http = 409


class CodigoDeObservacionInvalidoError(DomainError):
    """El handler intentó producir una observación con un código fuera del
    catálogo de SYN-07 (`docs/01-dominio.md` §17, change 04, grupo 9, tarea
    9.4). La observación no se registra: se trata como un error de
    programación del handler (mismo criterio que `ComandoInconsistenteError`
    -- la transacción entera se revierte, así que tampoco queda el comando
    con un estado final espurio)."""

    codigo = "CODIGO_DE_OBSERVACION_INVALIDO"


class ModoNoAdmitidoParaTipoError(DomainError):
    """El catálogo (`app.commands.catalogo`) declara que el tipo de este
    comando no admite el modo (`ONLINE`/`OFFLINE`) en el que llegó (`02`
    §6.5, change 04, tarea 8.10). Distinto de `ModoNoAdmitidoPorRestError`
    (`sobre.py`): ese rechaza CUALQUIER modo que no sea `ONLINE` en un
    endpoint REST directo, sin mirar el catálogo; este rechaza según lo que
    el tipo concreto declaró, y solo aplica dentro de un lote (`sync/
    comandos`), donde `OFFLINE` sí es un modo válido en general."""

    codigo = "MODO_NO_ADMITIDO_PARA_TIPO"
