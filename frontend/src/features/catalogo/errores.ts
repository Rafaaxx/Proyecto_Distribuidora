/**
 * Error de dominio de catálogo tal como lo expone la API (Problem Details,
 * `backend/app/main.py::_domain_error_a_problem_details`): `codigo` es el
 * campo estable (`CODIGO_DUPLICADO`, `UNIDADES_CONGELADAS`,
 * `PERMISO_REQUERIDO`, …) que los formularios usan para decidir junto a
 * qué campo mostrar el mensaje (tarea 10.5), no el texto de `title` (que
 * puede cambiar de redacción).
 */
export class ErrorDeCatalogo extends Error {
  readonly codigo: string

  constructor(codigo: string, mensaje: string) {
    super(mensaje)
    this.name = 'ErrorDeCatalogo'
    this.codigo = codigo
  }
}

/** Distingue "no tengo el permiso" del resto (tarea 10.4, igual criterio
 * que `PermisoRequeridoError` de dispositivos). */
export class PermisoRequeridoCatalogoError extends ErrorDeCatalogo {
  constructor(mensaje: string) {
    super('PERMISO_REQUERIDO', mensaje)
    this.name = 'PermisoRequeridoCatalogoError'
  }
}

interface ProblemDetails {
  title?: string
  codigo?: string
}

const MENSAJE_GENERICO_DE_RESERVA = 'No se pudo completar la operación.'

/** Traduce una `Response` no-ok de la API de catálogo al error de dominio
 * correspondiente. No consume el cuerpo si `respuesta.ok`. */
export async function errorDesdeRespuesta(respuesta: Response): Promise<ErrorDeCatalogo> {
  let problema: ProblemDetails = {}
  try {
    problema = (await respuesta.json()) as ProblemDetails
  } catch {
    // Cuerpo no-JSON o vacío: se usa el mensaje de reserva.
  }

  const mensaje = problema.title ?? MENSAJE_GENERICO_DE_RESERVA
  const codigo = problema.codigo ?? 'ERROR_DESCONOCIDO'

  if (respuesta.status === 403) {
    return new PermisoRequeridoCatalogoError(mensaje)
  }
  return new ErrorDeCatalogo(codigo, mensaje)
}
