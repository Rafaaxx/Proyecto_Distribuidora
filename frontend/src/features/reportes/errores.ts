/**
 * Error de dominio de los reportes tal como lo expone la API (Problem Details): `codigo` es el campo estable
 * (`RANGO_DE_FECHAS_INVALIDO`, `PERIODO_DEMASIADO_LARGO`), no el texto de `title` (change 26, D1, D12). Mismo
 * criterio que `features/revision/errores.ts`.
 */
export class ErrorDeReportes extends Error {
  readonly codigo: string

  constructor(codigo: string, mensaje: string) {
    super(mensaje)
    this.name = 'ErrorDeReportes'
    this.codigo = codigo
  }
}

/** El 403: `VER_REPORTES` o la regla de los saldos de proveedores (SEG-06). */
export class PermisoRequeridoReportesError extends ErrorDeReportes {
  constructor(mensaje: string) {
    super('PERMISO_REQUERIDO', mensaje)
    this.name = 'PermisoRequeridoReportesError'
  }
}

/** El 404 no distingue un recurso ajeno de uno inexistente (INV-21). */
export class RecursoNoEncontradoReportesError extends ErrorDeReportes {
  constructor(mensaje: string) {
    super('RECURSO_NO_ENCONTRADO', mensaje)
    this.name = 'RecursoNoEncontradoReportesError'
  }
}

interface ProblemDetails {
  title?: string
  codigo?: string
}

const MENSAJE_GENERICO_DE_RESERVA = 'No se pudo completar la operación.'

/** Traduce una `Response` no-ok de la API de reportes al error de dominio. */
export async function errorDesdeRespuesta(respuesta: Response): Promise<ErrorDeReportes> {
  let problema: ProblemDetails = {}
  try {
    problema = (await respuesta.json()) as ProblemDetails
  } catch {
    // Cuerpo no-JSON o vacío: se usa el mensaje de reserva.
  }
  const mensaje = problema.title ?? MENSAJE_GENERICO_DE_RESERVA
  if (respuesta.status === 403) return new PermisoRequeridoReportesError(mensaje)
  if (respuesta.status === 404) return new RecursoNoEncontradoReportesError(mensaje)
  return new ErrorDeReportes(problema.codigo ?? 'ERROR_DESCONOCIDO', mensaje)
}

/** Textos aprobados en 0.2 (D12). */
const TEXTO_RANGO_INVALIDO = '"Desde" no puede ser posterior a "Hasta".'
const TEXTO_PERIODO_LARGO = 'El período no puede superar los 366 días.'
const TEXTO_NO_ENCONTRADA = 'No se encontró la jornada.'
const TEXTO_ERROR_DE_CARGA = 'No se pudo cargar el reporte. Probá de nuevo.'

const MENSAJES_POR_CODIGO: Readonly<Record<string, string>> = {
  RANGO_DE_FECHAS_INVALIDO: TEXTO_RANGO_INVALIDO,
  PERIODO_DEMASIADO_LARGO: TEXTO_PERIODO_LARGO,
}

/** El mensaje para quien mira un reporte ante un error (cualquier otro se informa como error de carga). */
export function mensajeDeErrorDeReportes(error: unknown): string {
  if (error instanceof RecursoNoEncontradoReportesError) return TEXTO_NO_ENCONTRADA
  if (error instanceof ErrorDeReportes) return MENSAJES_POR_CODIGO[error.codigo] ?? TEXTO_ERROR_DE_CARGA
  return TEXTO_ERROR_DE_CARGA
}
