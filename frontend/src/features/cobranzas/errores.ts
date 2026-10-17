/**
 * Error de dominio de cobranzas tal como lo expone la API (Problem Details,
 * `backend/app/main.py::_domain_error_a_problem_details`): `codigo` es el campo estable
 * (`MEDIOS_NO_SUMAN_IMPORTE`, `COBRANZA_YA_ANULADA`, `REFERENCIA_OBLIGATORIA`, ...). `medio` es el
 * índice 0-based del medio que causó el error cuando es de un medio (`extension["medio"]`,
 * TR-10); `null` en cualquier otro caso. Mismo criterio que `features/pagos-proveedores/errores.ts`.
 */
export class ErrorDeCobranzas extends Error {
  readonly codigo: string
  readonly medio: number | null

  constructor(codigo: string, mensaje: string, medio: number | null = null) {
    super(mensaje)
    this.name = 'ErrorDeCobranzas'
    this.codigo = codigo
    this.medio = medio
  }
}

/** El 403: `REGISTRAR_COBRANZA` / `ANULAR_COBRANZA` (SEG-06). */
export class PermisoRequeridoCobranzasError extends ErrorDeCobranzas {
  constructor(mensaje: string) {
    super('PERMISO_REQUERIDO', mensaje)
    this.name = 'PermisoRequeridoCobranzasError'
  }
}

export type CampoDelFormulario = 'cliente' | 'importe' | 'observacion'

const CAMPO_POR_CODIGO: Record<string, CampoDelFormulario> = {
  CONSUMIDOR_FINAL_SIN_CUENTA: 'cliente',
  IMPORTE_INVALIDO: 'importe',
  MEDIOS_NO_SUMAN_IMPORTE: 'importe',
  OBSERVACION_INVALIDA: 'observacion',
}

/**
 * Campo del formulario al que pertenece un error que no es de una línea de medios (los de un
 * medio traen su posición en `medio`). `null` es un error general (jornada, duplicada, ...).
 */
export function campoDelError(error: ErrorDeCobranzas): CampoDelFormulario | null {
  return CAMPO_POR_CODIGO[error.codigo] ?? null
}

interface ProblemDetails {
  title?: string
  codigo?: string
  medio?: number
}

const MENSAJE_GENERICO_DE_RESERVA = 'No se pudo completar la operación.'

/** Traduce una `Response` no-ok de la API de cobranzas al error de dominio. */
export async function errorDesdeRespuesta(respuesta: Response): Promise<ErrorDeCobranzas> {
  let problema: ProblemDetails = {}
  try {
    problema = (await respuesta.json()) as ProblemDetails
  } catch {
    // Cuerpo no-JSON o vacío: se usa el mensaje de reserva.
  }

  const mensaje = problema.title ?? MENSAJE_GENERICO_DE_RESERVA
  if (respuesta.status === 403) return new PermisoRequeridoCobranzasError(mensaje)
  const medio = typeof problema.medio === 'number' ? problema.medio : null
  return new ErrorDeCobranzas(problema.codigo ?? 'ERROR_DESCONOCIDO', mensaje, medio)
}
