/**
 * Error de dominio de `configuracion` tal como lo expone la API (Problem Details): `codigo`
 * es el campo estable (`CONDICION_IVA_SIN_CAMBIO`, `MODO_IMPOSITIVO_INCOMPATIBLE`,
 * `PERMISO_REQUERIDO`, ...). Mismo criterio que `features/compras/errores.ts`. Tener
 * `codigo` es lo que `debeReintentar` usa para no reintentar un rechazo ya resuelto.
 */
export class ErrorDeConfiguracion extends Error {
  readonly codigo: string
  readonly estado: number
  /** Cantidad de productos que informa ALICUOTA_EN_USO (change 20c, D8). */
  readonly productos: number | undefined

  constructor(codigo: string, mensaje: string, estado: number, productos?: number) {
    super(mensaje)
    this.name = 'ErrorDeConfiguracion'
    this.codigo = codigo
    this.estado = estado
    this.productos = productos
  }
}

interface ProblemDetails {
  title?: string
  codigo?: string
  productos?: number
}

const MENSAJE_GENERICO_DE_RESERVA = 'No se pudo completar la operación.'

/** Traduce una `Response` no-ok de la API de configuración al error de dominio. */
export async function errorDesdeRespuesta(respuesta: Response): Promise<ErrorDeConfiguracion> {
  let problema: ProblemDetails = {}
  try {
    problema = (await respuesta.json()) as ProblemDetails
  } catch {
    // Cuerpo no-JSON o vacío: se usa el mensaje de reserva.
  }
  return new ErrorDeConfiguracion(
    problema.codigo ?? 'ERROR_DESCONOCIDO',
    problema.title ?? MENSAJE_GENERICO_DE_RESERVA,
    respuesta.status,
    typeof problema.productos === 'number' ? problema.productos : undefined,
  )
}
