/**
 * Error de dominio de pagos a proveedores tal como lo expone la API (Problem Details,
 * `backend/app/main.py::_domain_error_a_problem_details`): `codigo` es el campo estable
 * (`MEDIOS_NO_SUMAN_IMPORTE`, `PAGO_YA_ANULADO`, `PERMISO_REQUERIDO`, ...). `medio` es el
 * índice 0-based del medio que causó el error cuando es de un medio (`extension["medio"]`,
 * TR-10); `null` en cualquier otro caso. Mismo criterio que `features/compras/errores.ts`.
 */
export class ErrorDePagos extends Error {
  readonly codigo: string
  readonly medio: number | null

  constructor(codigo: string, mensaje: string, medio: number | null = null) {
    super(mensaje)
    this.name = 'ErrorDePagos'
    this.codigo = codigo
    this.medio = medio
  }
}

/** El 403: `REGISTRAR_PAGO_PROVEEDOR` / `ANULAR_PAGO_PROVEEDOR` (SEG-06). */
export class PermisoRequeridoPagosError extends ErrorDePagos {
  constructor(mensaje: string) {
    super('PERMISO_REQUERIDO', mensaje)
    this.name = 'PermisoRequeridoPagosError'
  }
}

interface ProblemDetails {
  title?: string
  codigo?: string
  medio?: number
}

const MENSAJE_GENERICO_DE_RESERVA = 'No se pudo completar la operación.'

/** Traduce una `Response` no-ok de la API de pagos al error de dominio. */
export async function errorDesdeRespuesta(respuesta: Response): Promise<ErrorDePagos> {
  let problema: ProblemDetails = {}
  try {
    problema = (await respuesta.json()) as ProblemDetails
  } catch {
    // Cuerpo no-JSON o vacío: se usa el mensaje de reserva.
  }

  const mensaje = problema.title ?? MENSAJE_GENERICO_DE_RESERVA
  if (respuesta.status === 403) return new PermisoRequeridoPagosError(mensaje)
  const medio = typeof problema.medio === 'number' ? problema.medio : null
  return new ErrorDePagos(problema.codigo ?? 'ERROR_DESCONOCIDO', mensaje, medio)
}
