/**
 * Error de dominio de proveedores/costos tal como lo expone la API
 * (Problem Details, `backend/app/main.py::_domain_error_a_problem_details`):
 * `codigo` es el campo estable (`NOMBRE_DUPLICADO`, `PROVEEDOR_INACTIVO`,
 * `PERMISO_REQUERIDO`, …) que los formularios usan para decidir junto a
 * qué campo mostrar el mensaje (tarea 11.2), no el texto de `title` (que
 * puede cambiar de redacción). Mismo criterio que
 * `features/catalogo/errores.ts`.
 */
export class ErrorDeProveedores extends Error {
  readonly codigo: string
  /** contrato-api.md P9 (aprobado 2026-09-24): índice 0-based de la fila
   * del lote de `COSTO_INFORMAR` que causó el error, cuando el error es
   * específico de una fila; `null` en cualquier otro caso (permiso,
   * proveedor no encontrado/inactivo, lote vacío o con más de 200
   * costos). Reemplaza la heurística previa de buscar un UUID en el
   * mensaje del error. */
  readonly fila: number | null

  constructor(codigo: string, mensaje: string, fila: number | null = null) {
    super(mensaje)
    this.name = 'ErrorDeProveedores'
    this.codigo = codigo
    this.fila = fila
  }
}

/** Distingue "no tengo el permiso" del resto (tarea 11.3, igual criterio
 * que `PermisoRequeridoCatalogoError`). */
export class PermisoRequeridoProveedoresError extends ErrorDeProveedores {
  constructor(mensaje: string) {
    super('PERMISO_REQUERIDO', mensaje)
    this.name = 'PermisoRequeridoProveedoresError'
  }
}

interface ProblemDetails {
  title?: string
  codigo?: string
  fila?: number
}

const MENSAJE_GENERICO_DE_RESERVA = 'No se pudo completar la operación.'

/** Traduce una `Response` no-ok de la API de proveedores/costos al error
 * de dominio correspondiente. No consume el cuerpo si `respuesta.ok`. */
export async function errorDesdeRespuesta(respuesta: Response): Promise<ErrorDeProveedores> {
  let problema: ProblemDetails = {}
  try {
    problema = (await respuesta.json()) as ProblemDetails
  } catch {
    // Cuerpo no-JSON o vacío: se usa el mensaje de reserva.
  }

  const mensaje = problema.title ?? MENSAJE_GENERICO_DE_RESERVA
  const codigo = problema.codigo ?? 'ERROR_DESCONOCIDO'
  const fila = typeof problema.fila === 'number' ? problema.fila : null

  if (respuesta.status === 403) {
    return new PermisoRequeridoProveedoresError(mensaje)
  }
  return new ErrorDeProveedores(codigo, mensaje, fila)
}
