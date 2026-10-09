import { esErrorDeRed } from '../../lib/api/reintentoDeRed'

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
  /** Índice 0-based de la línea que causó el error, si el servidor lo informó (contrato P9). */
  readonly linea: number | undefined

  constructor(codigo: string, mensaje: string, linea?: number) {
    super(mensaje)
    this.name = 'ErrorDeStock'
    this.codigo = codigo
    this.linea = linea
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
  linea?: number
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
  return new ErrorDeStock(codigo, mensaje, typeof problema.linea === 'number' ? problema.linea : undefined)
}

/** Qué operación falló: cambia el texto de algunos códigos (`STOCK_INSUFICIENTE`, 403). */
export type ContextoDeError = 'transferencia' | 'ajuste' | 'anulacion'

const AVISO_SIN_CONEXION = 'Se necesita conexión para completar esta operación. Probá de nuevo cuando tengas conexión.'

const MENSAJES_POR_CODIGO: Record<string, string> = {
  UBICACIONES_IGUALES: 'El origen y el destino tienen que ser distintos.',
  MOTIVO_INVALIDO: 'El motivo elegido no es válido. Elegí otro.',
  PRODUCTO_SIN_COSTO:
    'Ese producto todavía no tiene costo, así que su stock no se puede aumentar con un ajuste. Cargalo con stock inicial o con una compra.',
  PRODUCTO_INACTIVO: 'Hay un producto inactivo en la operación. Reactivalo antes de seguir.',
  UBICACION_INACTIVA: 'Hay una ubicación inactiva en la operación. Reactivala antes de seguir.',
  TRANSFERENCIA_YA_ANULADA: 'La transferencia ya fue anulada.',
  AJUSTE_YA_ANULADO: 'El ajuste ya fue anulado.',
}

const STOCK_INSUFICIENTE: Record<ContextoDeError, string> = {
  transferencia: 'No hay stock suficiente en el origen para transferir esa cantidad.',
  ajuste: 'Un ajuste no puede dejar stock negativo.',
  anulacion: 'No se puede anular: el stock actual no alcanza para revertir la operación.',
}

/**
 * Mensaje para el usuario ante el rechazo (o el corte de red) de una transferencia, un ajuste o
 * una anulación (change 14, tarea 12.2). Un código sin texto propio muestra el del servidor.
 */
export function mensajeDeErrorDeStock(error: unknown, contexto: ContextoDeError): string {
  if (error instanceof PermisoRequeridoStockError) {
    return contexto === 'anulacion'
      ? 'Solo podés anular las transferencias que cargaste vos. Para anular la de otro usuario hace falta un permiso adicional.'
      : 'No tenés permiso para hacer esta operación.'
  }
  if (error instanceof ErrorDeStock) {
    if (error.codigo === 'STOCK_INSUFICIENTE') return STOCK_INSUFICIENTE[contexto]
    return MENSAJES_POR_CODIGO[error.codigo] ?? error.message
  }
  if (esErrorDeRed(error)) return AVISO_SIN_CONEXION
  return MENSAJE_GENERICO_DE_RESERVA
}
