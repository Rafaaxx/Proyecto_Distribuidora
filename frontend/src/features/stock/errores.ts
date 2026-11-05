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
  /**
   * Lo que el servidor suma a la respuesta de un error (Problem Details con extensión): los
   * `productos` que faltan de `CONTEO_INCOMPLETO`, los `distintos` y los `esperados` de
   * `ESPERADO_DIFIERE` (change 24, D2). Vacío si no trae nada.
   */
  readonly extension: Readonly<Record<string, unknown>>

  constructor(codigo: string, mensaje: string, linea?: number, extension: Readonly<Record<string, unknown>> = {}) {
    super(mensaje)
    this.name = 'ErrorDeStock'
    this.codigo = codigo
    this.linea = linea
    this.extension = extension
  }

  /** Los ids que trae la extensión bajo `campo` (`productos`, `distintos`); vacío si no hay. */
  idsDe(campo: string): string[] {
    const valor = this.extension[campo]
    return Array.isArray(valor) ? valor.filter((v): v is string => typeof v === 'string') : []
  }

  /** Los esperados actuales de `ESPERADO_DIFIERE`, por producto, en unidad base. */
  esperadosActuales(): Record<string, number> {
    const valor = this.extension['esperados']
    if (typeof valor !== 'object' || valor === null || Array.isArray(valor)) return {}
    return Object.fromEntries(Object.entries(valor).filter((par): par is [string, number] => typeof par[1] === 'number'))
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
  [extension: string]: unknown
}

const CAMPOS_ESTANDAR = new Set(['type', 'title', 'status', 'codigo', 'instance', 'linea', 'detail'])

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
  const extension = Object.fromEntries(Object.entries(problema).filter(([campo]) => !CAMPOS_ESTANDAR.has(campo)))
  return new ErrorDeStock(codigo, mensaje, typeof problema.linea === 'number' ? problema.linea : undefined, extension)
}

/** Qué operación falló: cambia el texto de algunos códigos (`STOCK_INSUFICIENTE`, 403). */
export type ContextoDeError = 'transferencia' | 'ajuste' | 'anulacion' | 'apertura' | 'jornada' | 'ubicacion'

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
  UBICACION_SIN_TOMA: 'Esa ubicación no requiere toma: no hace falta abrir una jornada.',
  USUARIO_CON_JORNADA: 'Ya tenés una jornada abierta. Cerrala o pedí que la liberen antes de abrir otra.',
  DISPOSITIVO_CON_JORNADA:
    'Hay una jornada abierta en este dispositivo. Cerrala o pedí que la liberen antes de abrir otra.',
  JORNADA_ESTADO_INVALIDO: 'La jornada ya cambió de estado. Actualizá la pantalla para ver cómo quedó.',
  OBSERVACION_INVALIDA: 'La observación admite hasta 500 caracteres.',
  // Change 24 (D11, aprobados en 0.2): la rendición y el cierre con devolución.
  JORNADA_SIN_ENTREGA: 'El vendedor todavía no terminó el día en el teléfono.',
  ESPERADO_DIFIERE:
    'El stock del vehículo cambió mientras contabas. Revisá los esperados marcados y volvé a confirmar.',
  UBICACION_CON_TOMA: 'El destino es un vehículo con jornada; elegí un depósito.',
  // Sin los nombres (la pantalla arma «Falta contar: {productos}.» con ellos): texto de reserva.
  CONTEO_INCOMPLETO: 'Falta contar algún producto.',
}

const STOCK_INSUFICIENTE: Record<ContextoDeError, string> = {
  transferencia: 'No hay stock suficiente en el origen para transferir esa cantidad.',
  ajuste: 'Un ajuste no puede dejar stock negativo.',
  anulacion: 'No se puede anular: el stock actual no alcanza para revertir la operación.',
  apertura: 'No hay stock suficiente.',
  jornada: 'No hay stock suficiente para devolver esa cantidad.',
  ubicacion: 'No hay stock suficiente.',
}

const TEXTO_MOVER_STOCK_TOMADA =
  'La ubicación está tomada por una jornada abierta. Solo quien la tiene, o quien puede liberarla, puede mover su stock.'
const TEXTO_ABRIR_TOMADA = 'Esa ubicación ya la tomó otra jornada. Elegí otra.'

/** `UBICACION_TOMADA` (STK-09, INV-16) se explica distinto según lo que se intentaba hacer. */
const UBICACION_TOMADA: Record<ContextoDeError, string> = {
  apertura: TEXTO_ABRIR_TOMADA,
  jornada: TEXTO_ABRIR_TOMADA,
  transferencia: TEXTO_MOVER_STOCK_TOMADA,
  ajuste: TEXTO_MOVER_STOCK_TOMADA,
  anulacion: TEXTO_MOVER_STOCK_TOMADA,
  ubicacion:
    'La ubicación está tomada por una jornada abierta: no se puede desactivar ni cambiar su tipo o su toma hasta que se cierre o se libere.',
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
    if (error.codigo === 'UBICACION_TOMADA') return UBICACION_TOMADA[contexto]
    return MENSAJES_POR_CODIGO[error.codigo] ?? error.message
  }
  if (esErrorDeRed(error)) return AVISO_SIN_CONEXION
  return MENSAJE_GENERICO_DE_RESERVA
}
