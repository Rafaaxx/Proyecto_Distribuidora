/**
 * Error de dominio de cuentas corrientes tal como lo expone la API (Problem
 * Details, `backend/app/main.py::_domain_error_a_problem_details`): `codigo`
 * es el campo estable (`CUENTA_CON_OPERACIONES`, `IMPORTE_INVALIDO`,
 * `CONSUMIDOR_FINAL_SIN_CUENTA`, `CURSOR_INVALIDO`,
 * `RANGO_DE_FECHAS_INVALIDO`, `PERMISO_REQUERIDO`, `RECURSO_NO_ENCONTRADO`,
 * ...), no el texto de `title`. Mismo criterio que
 * `features/clientes/errores.ts` y `features/proveedores/errores.ts`.
 */
export class ErrorDeCuentasCorrientes extends Error {
  readonly codigo: string

  constructor(codigo: string, mensaje: string) {
    super(mensaje)
    this.name = 'ErrorDeCuentasCorrientes'
    this.codigo = codigo
  }
}

/** "No tengo el permiso": el 403 de la lectura (`GESTIONAR_CLIENTES` /
 * `GESTIONAR_PROVEEDORES`, D2) o del comando (`IMPORTAR_DATOS`, D1). */
export class PermisoRequeridoCuentasCorrientesError extends ErrorDeCuentasCorrientes {
  constructor(mensaje: string) {
    super('PERMISO_REQUERIDO', mensaje)
    this.name = 'PermisoRequeridoCuentasCorrientesError'
  }
}

/** Entidad ajena o inexistente (INV-21, SEG-07): mismo código en los dos
 * casos, el 404 no distingue "ajena" de "no existe". */
export class RecursoNoEncontradoCuentasCorrientesError extends ErrorDeCuentasCorrientes {
  constructor(mensaje: string) {
    super('RECURSO_NO_ENCONTRADO', mensaje)
    this.name = 'RecursoNoEncontradoCuentasCorrientesError'
  }
}

interface ProblemDetails {
  title?: string
  codigo?: string
}

const MENSAJE_GENERICO_DE_RESERVA = 'No se pudo completar la operación.'

/** Traduce una `Response` no-ok de la API de cuentas corrientes al error de
 * dominio correspondiente. */
export async function errorDesdeRespuesta(respuesta: Response): Promise<ErrorDeCuentasCorrientes> {
  let problema: ProblemDetails = {}
  try {
    problema = (await respuesta.json()) as ProblemDetails
  } catch {
    // Cuerpo no-JSON o vacío: se usa el mensaje de reserva.
  }

  const mensaje = problema.title ?? MENSAJE_GENERICO_DE_RESERVA
  const codigo = problema.codigo ?? 'ERROR_DESCONOCIDO'

  if (respuesta.status === 403) {
    return new PermisoRequeridoCuentasCorrientesError(mensaje)
  }
  if (respuesta.status === 404) {
    return new RecursoNoEncontradoCuentasCorrientesError(mensaje)
  }
  return new ErrorDeCuentasCorrientes(codigo, mensaje)
}
