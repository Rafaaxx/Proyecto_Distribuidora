/**
 * Error de dominio de `precios` tal como lo expone la API (Problem Details): `codigo` es el
 * campo estable (`REGLA_DUPLICADA`, `LISTA_EN_USO`, `VIGENCIA_INVALIDA`, `PERMISO_REQUERIDO`,
 * ...). Tener `codigo` es lo que `debeReintentar` usa para no reintentar un rechazo ya
 * resuelto por el servidor. Mismo criterio que `features/pagos-proveedores/errores.ts`.
 */
export class ErrorDePrecios extends Error {
  readonly codigo: string
  readonly estado: number

  constructor(codigo: string, mensaje: string, estado: number) {
    super(mensaje)
    this.name = 'ErrorDePrecios'
    this.codigo = codigo
    this.estado = estado
  }
}

/** El 403: falta `GESTIONAR_LISTAS` o `PUBLICAR_LISTAS` (SEG-06). */
export class PermisoRequeridoPreciosError extends ErrorDePrecios {
  constructor(mensaje: string) {
    super('PERMISO_REQUERIDO', mensaje, 403)
    this.name = 'PermisoRequeridoPreciosError'
  }
}

interface ProblemDetails {
  title?: string
  codigo?: string
}

const MENSAJE_GENERICO_DE_RESERVA = 'No se pudo completar la operación.'

/** Traduce una `Response` no-ok de la API de precios al error de dominio. */
export async function errorDesdeRespuesta(respuesta: Response): Promise<ErrorDePrecios> {
  let problema: ProblemDetails = {}
  try {
    problema = (await respuesta.json()) as ProblemDetails
  } catch {
    // Cuerpo no-JSON o vacío: se usa el mensaje de reserva.
  }
  const mensaje = problema.title ?? MENSAJE_GENERICO_DE_RESERVA
  if (respuesta.status === 403) return new PermisoRequeridoPreciosError(mensaje)
  return new ErrorDePrecios(problema.codigo ?? 'ERROR_DESCONOCIDO', mensaje, respuesta.status)
}
