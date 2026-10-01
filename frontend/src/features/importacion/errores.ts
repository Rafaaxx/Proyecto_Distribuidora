/**
 * Un error del informe de una importación rechazada (`IMPORTACION_CON_ERRORES`): la fila de
 * la planilla (el encabezado es la 1), la columna si aplica, el código de dominio estable y
 * el mensaje, tal como los arma el servidor (`importacion/domain/informe.py`).
 */
export interface ErrorDeFilaDeImportacion {
  fila: number
  columna: string | null
  codigo: string
  mensaje: string
}

/**
 * Error de dominio de importación tal como lo expone la API (Problem Details): `codigo` es el
 * campo estable (`IMPORTACION_CON_ERRORES`, `COLUMNAS_INVALIDAS`, `ARCHIVO_INVALIDO`,
 * `TIPO_IMPORTACION_INVALIDO`, `PERMISO_REQUERIDO`, ...). `errores` trae el informe por fila
 * y está vacío en los errores de archivo. Mismo criterio que `features/stock/errores.ts`.
 */
export class ErrorDeImportacion extends Error {
  readonly codigo: string
  readonly errores: ErrorDeFilaDeImportacion[]

  constructor(codigo: string, mensaje: string, errores: ErrorDeFilaDeImportacion[] = []) {
    super(mensaje)
    this.name = 'ErrorDeImportacion'
    this.codigo = codigo
    this.errores = errores
  }
}

/** El 403: falta `IMPORTAR_DATOS`. */
export class PermisoRequeridoImportacionError extends ErrorDeImportacion {
  constructor(mensaje: string) {
    super('PERMISO_REQUERIDO', mensaje)
    this.name = 'PermisoRequeridoImportacionError'
  }
}

interface ProblemDetails {
  title?: string
  codigo?: string
  errores?: unknown
}

const MENSAJE_GENERICO_DE_RESERVA = 'No se pudo completar la operación.'

function esErrorDeFila(valor: unknown): valor is ErrorDeFilaDeImportacion {
  if (typeof valor !== 'object' || valor === null) return false
  const candidato = valor as Record<string, unknown>
  return (
    typeof candidato.fila === 'number' &&
    (candidato.columna === null || typeof candidato.columna === 'string') &&
    typeof candidato.codigo === 'string' &&
    typeof candidato.mensaje === 'string'
  )
}

/** Traduce una `Response` no-ok de la API de importación al error de dominio. */
export async function errorDesdeRespuesta(respuesta: Response): Promise<ErrorDeImportacion> {
  let problema: ProblemDetails = {}
  try {
    problema = (await respuesta.json()) as ProblemDetails
  } catch {
    // Cuerpo no-JSON o vacío: se usa el mensaje de reserva.
  }

  const mensaje = problema.title ?? MENSAJE_GENERICO_DE_RESERVA
  if (respuesta.status === 403) return new PermisoRequeridoImportacionError(mensaje)
  const errores = Array.isArray(problema.errores) ? problema.errores.filter(esErrorDeFila) : []
  return new ErrorDeImportacion(problema.codigo ?? 'ERROR_DESCONOCIDO', mensaje, errores)
}
