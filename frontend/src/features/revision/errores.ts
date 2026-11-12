import { esErrorDeRed } from '../../lib/api/reintentoDeRed'

/**
 * Error de dominio de la revision de observaciones y rechazos tal como lo expone la API (Problem Details):
 * `codigo` es el campo estable (`OBSERVACION_YA_RESUELTA`, `RECHAZO_YA_RESUELTO`, `VINCULO_INVALIDO`, ...), no el
 * texto de `title` (change 25, D12; SYN-08). Mismo criterio que `features/cobranzas/errores.ts`.
 */
export class ErrorDeRevision extends Error {
  readonly codigo: string

  constructor(codigo: string, mensaje: string) {
    super(mensaje)
    this.name = 'ErrorDeRevision'
    this.codigo = codigo
  }
}

/** El 403: `REVISAR_OBSERVACIONES` (SEG-06). */
export class PermisoRequeridoRevisionError extends ErrorDeRevision {
  constructor(mensaje: string) {
    super('PERMISO_REQUERIDO', mensaje)
    this.name = 'PermisoRequeridoRevisionError'
  }
}

/** El 404 no distingue una operacion ajena de una inexistente (INV-21). */
export class RecursoNoEncontradoRevisionError extends ErrorDeRevision {
  constructor(mensaje: string) {
    super('RECURSO_NO_ENCONTRADO', mensaje)
    this.name = 'RecursoNoEncontradoRevisionError'
  }
}

interface ProblemDetails {
  title?: string
  codigo?: string
}

const MENSAJE_GENERICO_DE_RESERVA = 'No se pudo completar la operación.'

/** Traduce una `Response` no-ok de la API de revision al error de dominio. */
export async function errorDesdeRespuesta(respuesta: Response): Promise<ErrorDeRevision> {
  let problema: ProblemDetails = {}
  try {
    problema = (await respuesta.json()) as ProblemDetails
  } catch {
    // Cuerpo no-JSON o vacío: se usa el mensaje de reserva.
  }
  const mensaje = problema.title ?? MENSAJE_GENERICO_DE_RESERVA
  if (respuesta.status === 403) return new PermisoRequeridoRevisionError(mensaje)
  if (respuesta.status === 404) return new RecursoNoEncontradoRevisionError(mensaje)
  return new ErrorDeRevision(problema.codigo ?? 'ERROR_DESCONOCIDO', mensaje)
}

const AVISO_SIN_CONEXION = 'Se necesita conexión para completar esta operación. Probá de nuevo cuando tengas conexión.'

/** Textos aprobados en 0.2 (D12). */
const MENSAJES_POR_CODIGO: Record<string, string> = {
  OBSERVACION_YA_RESUELTA: 'Alguno de los avisos ya lo resolvió otra persona. Actualizá la lista.',
  OBSERVACIONES_INVALIDAS: 'Elegí entre 1 y 100 avisos.',
  COMENTARIO_INVALIDO: 'Escribí un comentario de hasta 500 caracteres.',
  RECHAZO_YA_RESUELTO: 'Esta operación ya la resolvió otra persona.',
  VINCULO_INVALIDO: 'La operación elegida no corresponde a lo rechazado.',
}

const TEXTO_NO_ENCONTRADA = 'No se encontró la operación.'

/** El mensaje para quien revisa ante el rechazo (o el corte de red) de una resolución. */
export function mensajeDeErrorDeRevision(error: unknown): string {
  if (error instanceof PermisoRequeridoRevisionError) return 'No tenés permiso para hacer esta operación.'
  if (error instanceof RecursoNoEncontradoRevisionError) return TEXTO_NO_ENCONTRADA
  if (error instanceof ErrorDeRevision) return MENSAJES_POR_CODIGO[error.codigo] ?? error.message
  if (esErrorDeRed(error)) return AVISO_SIN_CONEXION
  return MENSAJE_GENERICO_DE_RESERVA
}
