/**
 * Error de la API de descuentos y de topes por rol tal como la devuelve el servidor (Problem
 * Details): `codigo` es el campo estable (`UMBRAL_INVALIDO`, `REGLA_ESTADO_INVALIDO`,
 * `IDENTIDAD_TOPE_DESCUENTO_FUERA_DE_RANGO`, ...). Tener `codigo` es lo que `debeReintentar` usa
 * para no reintentar un rechazo ya resuelto por el servidor. Mismo criterio que
 * `features/precios/errores.ts`.
 */
export class ErrorDeApiDescuentos extends Error {
  readonly codigo: string
  readonly estado: number

  constructor(codigo: string, mensaje: string, estado: number) {
    super(mensaje)
    this.name = 'ErrorDeApiDescuentos'
    this.codigo = codigo
    this.estado = estado
  }
}

/** El 403: falta `GESTIONAR_DESCUENTOS` o `ADMIN_USUARIOS` (SEG-06). */
export class PermisoRequeridoDescuentosError extends ErrorDeApiDescuentos {
  constructor(mensaje: string) {
    super('PERMISO_REQUERIDO', mensaje, 403)
    this.name = 'PermisoRequeridoDescuentosError'
  }
}

interface ProblemDetails {
  title?: string
  codigo?: string
}

const MENSAJE_GENERICO_DE_RESERVA = 'No se pudo completar la operación.'

/** Traduce una `Response` no-ok de la API de descuentos o de roles al error de dominio. */
export async function errorDesdeRespuesta(respuesta: Response): Promise<ErrorDeApiDescuentos> {
  let problema: ProblemDetails = {}
  try {
    problema = (await respuesta.json()) as ProblemDetails
  } catch {
    // Cuerpo no-JSON o vacío: se usa el mensaje de reserva.
  }
  const mensaje = problema.title ?? MENSAJE_GENERICO_DE_RESERVA
  if (respuesta.status === 403) return new PermisoRequeridoDescuentosError(mensaje)
  return new ErrorDeApiDescuentos(problema.codigo ?? 'ERROR_DESCONOCIDO', mensaje, respuesta.status)
}
