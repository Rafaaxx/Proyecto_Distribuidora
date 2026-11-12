"""Errores de dominio de `importacion` (`CLAUDE.md` §5: clases propias con código
estable que heredan de `DomainError`).

Tres familias:

- Del ARCHIVO (`ARCHIVO_INVALIDO`, `COLUMNAS_INVALIDAS`, `ARCHIVO_SIN_FILAS`,
  `ARCHIVO_DEMASIADO_GRANDE`, `TIPO_IMPORTACION_INVALIDO`): rechazan el archivo
  completo antes de procesar ninguna fila (`design.md` D11, D9).
- De VALOR (`NUMERO_INVALIDO`, `CANTIDAD_INVALIDA`, `FECHA_INVALIDA`,
  `VALOR_INVALIDO`, `VALOR_OBLIGATORIO`, `REFERENCIA_NO_ENCONTRADA`,
  `REFERENCIA_AMBIGUA`): una celda que no se puede leer. Llevan la `columna` para
  que el informe señale fila y columna.
- Agregado (`IMPORTACION_CON_ERRORES`): la importación entera se rechaza con la
  lista completa de errores por fila (`design.md` D1).
"""

from __future__ import annotations

from typing import Any

from app.core.errors import DomainError


class ArchivoInvalidoError(DomainError):
    """El archivo no es un CSV ni un `.xlsx` legible, está vacío o está dañado."""

    codigo = "ARCHIVO_INVALIDO"
    status_http = 422


class ColumnasInvalidasError(DomainError):
    """Falta una columna obligatoria, o hay una desconocida o repetida (`design.md`
    D11). Indica cuáles en `faltantes`, `desconocidas` y `repetidas`."""

    codigo = "COLUMNAS_INVALIDAS"
    status_http = 422

    def __init__(
        self,
        mensaje: str,
        *,
        faltantes: list[str] | None = None,
        desconocidas: list[str] | None = None,
        repetidas: list[str] | None = None,
    ) -> None:
        self.faltantes = faltantes or []
        self.desconocidas = desconocidas or []
        self.repetidas = repetidas or []
        super().__init__(
            mensaje,
            extension={
                "columnas_faltantes": self.faltantes,
                "columnas_desconocidas": self.desconocidas,
                "columnas_repetidas": self.repetidas,
            },
        )


class ArchivoSinFilasError(DomainError):
    """La planilla solo tiene el encabezado (`design.md` D11)."""

    codigo = "ARCHIVO_SIN_FILAS"
    status_http = 422


class ArchivoDemasiadoGrandeError(DomainError):
    """Más filas o más bytes que el límite de `design.md` D11."""

    codigo = "ARCHIVO_DEMASIADO_GRANDE"
    status_http = 422


class TipoImportacionInvalidoError(DomainError):
    """Tipo de importación desconocido o sin importador (`PRECIOS` hasta el change
    13, `design.md` D9)."""

    codigo = "TIPO_IMPORTACION_INVALIDO"
    status_http = 422


class CursorInvalidoError(DomainError):
    """El cursor de paginación del historial está malformado."""

    codigo = "CURSOR_INVALIDO"
    status_http = 422


class ErrorDeValor(DomainError):
    """Base de los errores de una celda: guarda la `columna` que el informe de
    errores por fila señala."""

    status_http = 422

    def __init__(
        self, mensaje: str, *, columna: str, extension: dict[str, Any] | None = None
    ) -> None:
        super().__init__(mensaje, extension=extension)
        self.columna = columna


class NumeroInvalidoError(ErrorDeValor):
    """Decimal mal escrito: coma decimal, sin separador de miles; el punto se
    rechaza (`design.md` D12)."""

    codigo = "NUMERO_INVALIDO"


class CantidadInvalidaError(ErrorDeValor):
    """Cantidad con decimales distintos de cero, no numérica o fuera del rango de
    `integer` (INV-04)."""

    codigo = "CANTIDAD_INVALIDA"


class FechaInvalidaError(ErrorDeValor):
    """Fecha que no es `AAAA-MM-DD` ni `DD/MM/AAAA`, o que no existe."""

    codigo = "FECHA_INVALIDA"


class ValorInvalidoError(ErrorDeValor):
    """Booleano que no es `S`, `SI`, `SÍ`, `N` ni `NO`."""

    codigo = "VALOR_INVALIDO"


class ValorObligatorioError(ErrorDeValor):
    """Celda vacía en una columna que la regla del tipo exige (por ejemplo el nombre
    de un producto o el `codigo` de un cliente, `design.md` D6)."""

    codigo = "VALOR_OBLIGATORIO"


class CuentaTipoInvalidoError(ErrorDeValor):
    """`cuenta_tipo` que no es `CLIENTE` ni `PROVEEDOR`. Mismo código estable que el de
    `cuentas_corrientes` (`CUENTA_TIPO_INVALIDO`): la entidad no se puede buscar sin saber
    de qué cuenta es, así que se rechaza antes de llamar al servicio."""

    codigo = "CUENTA_TIPO_INVALIDO"


class ReferenciaNoEncontradaError(ErrorDeValor):
    """La clave natural no coincide con ningún registro de la organización
    (`design.md` D4). El mensaje no distingue "no existe" de "existe en otra
    organización" (INV-21)."""

    codigo = "REFERENCIA_NO_ENCONTRADA"


class ReferenciaAmbiguaError(ErrorDeValor):
    """La clave natural coincide con más de un registro (`design.md` D4)."""

    codigo = "REFERENCIA_AMBIGUA"


class ImportacionConErroresError(DomainError):
    """Al menos una fila falló: la importación entera se rechaza y no queda ningún
    efecto (INV-01, `design.md` D1). `errores` viaja en `extension` para que el
    Problem Details lo exponga como `errores`."""

    codigo = "IMPORTACION_CON_ERRORES"
    status_http = 422

    def __init__(self, errores: list[dict[str, Any]]) -> None:
        self.errores = errores
        super().__init__(
            f"La importación tiene {len(errores)} error(es); no se importó ninguna fila.",
            extension={"errores": errores},
        )
