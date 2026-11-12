/**
 * Error de dominio de clientes tal como lo expone la API (Problem Details,
 * `backend/app/main.py::_domain_error_a_problem_details`): `codigo` es el
 * campo estable (`DOCUMENTO_INVALIDO`, `CODIGO_DUPLICADO`,
 * `TRANSICION_ESTADO_INVALIDA`, `CONSUMIDOR_FINAL_SIN_CREDITO`,
 * `PERMISO_REQUERIDO`, `RECURSO_NO_ENCONTRADO`, …), no el texto de `title`
 * (puede cambiar de redacción). Mismo criterio que
 * `features/proveedores/errores.ts`.
 */
export class ErrorDeClientes extends Error {
  readonly codigo: string

  constructor(codigo: string, mensaje: string) {
    super(mensaje)
    this.name = 'ErrorDeClientes'
    this.codigo = codigo
  }
}

/** Distingue "no tengo el permiso" del resto (mismo criterio que
 * `PermisoRequeridoProveedoresError`): cubre tanto el 403 de las lecturas
 * (`GESTIONAR_CLIENTES`) como el `PERMISO_REQUERIDO` que puede devolver un
 * comando del bus (`GESTIONAR_CLIENTES`/`GESTIONAR_CREDITO`/
 * `ADMIN_CONFIGURACION` según D3/D4). */
export class PermisoRequeridoClientesError extends ErrorDeClientes {
  constructor(mensaje: string) {
    super('PERMISO_REQUERIDO', mensaje)
    this.name = 'PermisoRequeridoClientesError'
  }
}

/** Recurso ajeno o inexistente (INV-21): mismo código en los dos casos, el
 * 404 no distingue "ajeno" de "no existe" (`CLAUDE.md` §4). */
export class RecursoNoEncontradoClientesError extends ErrorDeClientes {
  constructor(mensaje: string) {
    super('RECURSO_NO_ENCONTRADO', mensaje)
    this.name = 'RecursoNoEncontradoClientesError'
  }
}

interface ProblemDetails {
  title?: string
  codigo?: string
}

const MENSAJE_GENERICO_DE_RESERVA = 'No se pudo completar la operación.'

/** Traduce una `Response` no-ok de la API de clientes al error de dominio
 * correspondiente. No consume el cuerpo si `respuesta.ok`. */
export async function errorDesdeRespuesta(respuesta: Response): Promise<ErrorDeClientes> {
  let problema: ProblemDetails = {}
  try {
    problema = (await respuesta.json()) as ProblemDetails
  } catch {
    // Cuerpo no-JSON o vacío: se usa el mensaje de reserva.
  }

  const mensaje = problema.title ?? MENSAJE_GENERICO_DE_RESERVA
  const codigo = problema.codigo ?? 'ERROR_DESCONOCIDO'

  if (respuesta.status === 403) {
    return new PermisoRequeridoClientesError(mensaje)
  }
  if (respuesta.status === 404) {
    return new RecursoNoEncontradoClientesError(mensaje)
  }
  return new ErrorDeClientes(codigo, mensaje)
}
