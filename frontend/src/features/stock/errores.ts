/**
 * Error de dominio de stock tal como lo expone la API (Problem Details,
 * `backend/app/main.py::_domain_error_a_problem_details`): `codigo` es el campo
 * estable (`VEHICULO_REQUIERE_TOMA`, `NOMBRE_DUPLICADO`, `UBICACION_CON_STOCK`,
 * `STOCK_INSUFICIENTE`, `PRODUCTO_CON_OPERACIONES`, `COSTO_INVALIDO`,
 * `PERMISO_REQUERIDO`, `RECURSO_NO_ENCONTRADO`, ...), no el texto de `title`.
 * Mismo criterio que `features/cuentas-corrientes/errores.ts`.
 */
export class ErrorDeStock extends Error {
  readonly codigo: string

  constructor(codigo: string, mensaje: string) {
    super(mensaje)
    this.name = 'ErrorDeStock'
    this.codigo = codigo
  }
}

/** El 403: `TRANSFERIR_STOCK` (lecturas), `ADMIN_CONFIGURACION` (ubicaciones),
 * `IMPORTAR_DATOS` (stock inicial) o `VER_COSTOS` (promedio). */
export class PermisoRequeridoStockError extends ErrorDeStock {
  constructor(mensaje: string) {
    super('PERMISO_REQUERIDO', mensaje)
    this.name = 'PermisoRequeridoStockError'
  }
}

/** Ubicación o producto ajeno o inexistente (INV-21, SEG-07): el 404 no
 * distingue "ajeno" de "no existe". */
export class RecursoNoEncontradoStockError extends ErrorDeStock {
  constructor(mensaje: string) {
    super('RECURSO_NO_ENCONTRADO', mensaje)
    this.name = 'RecursoNoEncontradoStockError'
  }
}

interface ProblemDetails {
  title?: string
  codigo?: string
}

const MENSAJE_GENERICO_DE_RESERVA = 'No se pudo completar la operación.'

/** Traduce una `Response` no-ok de la API de stock al error de dominio. */
export async function errorDesdeRespuesta(respuesta: Response): Promise<ErrorDeStock> {
  let problema: ProblemDetails = {}
  try {
    problema = (await respuesta.json()) as ProblemDetails
  } catch {
    // Cuerpo no-JSON o vacío: se usa el mensaje de reserva.
  }

  const mensaje = problema.title ?? MENSAJE_GENERICO_DE_RESERVA
  const codigo = problema.codigo ?? 'ERROR_DESCONOCIDO'

  if (respuesta.status === 403) return new PermisoRequeridoStockError(mensaje)
  if (respuesta.status === 404) return new RecursoNoEncontradoStockError(mensaje)
  return new ErrorDeStock(codigo, mensaje)
}
