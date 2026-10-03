/**
 * Error de dominio de compras tal como lo expone la API (Problem Details,
 * `backend/app/main.py::_domain_error_a_problem_details`): `codigo` es el campo estable
 * (`CANTIDAD_INVALIDA`, `COMPRA_YA_ANULADA`, `PERMISO_REQUERIDO`, ...). `linea` es el
 * índice 0-based de la línea que causó el error cuando el error es de una línea
 * (`extension["linea"]`, TR-10); `null` en cualquier otro caso. Mismo criterio que
 * `features/proveedores/errores.ts`.
 */
export class ErrorDeCompras extends Error {
  readonly codigo: string
  readonly linea: number | null

  constructor(codigo: string, mensaje: string, linea: number | null = null) {
    super(mensaje)
    this.name = 'ErrorDeCompras'
    this.codigo = codigo
    this.linea = linea
  }
}

/** El 403: `REGISTRAR_COMPRA` / `ANULAR_COMPRA` (SEG-06). */
export class PermisoRequeridoComprasError extends ErrorDeCompras {
  constructor(mensaje: string) {
    super('PERMISO_REQUERIDO', mensaje)
    this.name = 'PermisoRequeridoComprasError'
  }
}

interface ProblemDetails {
  title?: string
  codigo?: string
  linea?: number
}

const MENSAJE_GENERICO_DE_RESERVA = 'No se pudo completar la operación.'

/** Traduce una `Response` no-ok de la API de compras al error de dominio. */
export async function errorDesdeRespuesta(respuesta: Response): Promise<ErrorDeCompras> {
  let problema: ProblemDetails = {}
  try {
    problema = (await respuesta.json()) as ProblemDetails
  } catch {
    // Cuerpo no-JSON o vacío: se usa el mensaje de reserva.
  }

  const mensaje = problema.title ?? MENSAJE_GENERICO_DE_RESERVA
  if (respuesta.status === 403) return new PermisoRequeridoComprasError(mensaje)
  const linea = typeof problema.linea === 'number' ? problema.linea : null
  return new ErrorDeCompras(problema.codigo ?? 'ERROR_DESCONOCIDO', mensaje, linea)
}
