import type { EstadoDeEnvio, ObservacionLocal } from '../../lib/dispositivo/db'

/**
 * Textos de pantalla de las observaciones y los rechazos de una venta enviada (change 22c,
 * `design.md` D4 y D5, aprobados en 0.2; SYN-04, SYN-06, SYN-07). Funciones puras: reciben el
 * código, el detalle y los nombres de la base local; las pantallas solo los muestran.
 *
 * Los códigos que traduce son los de `shared/fixtures/sync/codigos-de-sincronizacion.json`; una
 * prueba exige que todos tengan su texto.
 */
export const AVISO_DE_RECHAZO = 'Sigue guardada en el teléfono; avisá a administración.'
export const TEXTO_SIN_DETALLE = 'El detalle no está en el teléfono; consultalo con administración.'
export const TEXTO_DE_RECHAZO_GENERAL = 'El sistema no aceptó esta venta.'
export const TEXTO_DE_OBSERVACION_GENERAL = 'El sistema anotó algo para que administración lo revise.'

/** Nombres que la base local todavía conoce, por id. */
export interface NombresLocales {
  productos: ReadonlyMap<string, string>
  medios: ReadonlyMap<string, string>
  autorizadores: ReadonlyMap<string, string>
}

type Detalle = ObservacionLocal['detalle']

function texto(detalle: Detalle, campo: string): string | null {
  const valor = detalle?.[campo]
  return typeof valor === 'string' ? valor : null
}

function nombreDe(nombres: ReadonlyMap<string, string>, detalle: Detalle, campoId: string, reemplazo: string): string {
  const id = texto(detalle, campoId)
  return (id === null ? undefined : nombres.get(id)) ?? reemplazo
}

/** El medio: la base local; si ya no está, el nombre que anotó el servidor; si no, «un medio». */
function medioDe(nombres: NombresLocales, detalle: Detalle): string {
  return nombreDe(nombres.medios, detalle, 'medio_pago_id', texto(detalle, 'nombre') ?? 'un medio')
}

function conMayuscula(valor: string): string {
  return valor.charAt(0).toUpperCase() + valor.slice(1)
}

function tipoDeAutorizacion(detalle: Detalle): string {
  const tipo = texto(detalle, 'tipo')
  if (tipo === 'DESCUENTO') return 'descuento'
  if (tipo === 'CREDITO') return 'exceso de crédito'
  return 'descuento o exceso de crédito'
}

const FIJOS_DE_OBSERVACION: Readonly<Record<string, string>> = {
  EXCESO_CREDITO_ADVERTIDO: 'La venta superó el crédito del cliente.',
  EXCESO_CREDITO_AUTORIZADO_OFFLINE: 'La venta superó el crédito dentro de la tolerancia sin señal.',
  EXCESO_CREDITO_DETECTADO_SYNC: 'Con la deuda real del cliente, la venta superó su crédito.',
  LISTA_NO_VIGENTE: 'Los precios no eran los de la versión vigente de la lista en ese momento.',
  DESCUENTO_DIFIERE: 'El descuento no coincide con el que calcula el sistema.',
  CLIENTE_NO_HABILITADO: 'El cliente estaba suspendido o inactivo cuando llegó la venta.',
  PERMISO_REVOCADO: 'Cuando llegó la operación, tu usuario ya no tenía el permiso.',
  JORNADA_LIBERADA: 'La jornada había sido liberada cuando llegó la venta.',
  ANULACION_COMPRA_SIN_RECALCULO: 'La anulación de la compra no recalculó el costo.',
  CONSUMIDOR_FINAL_CON_DEUDA: 'La venta al consumidor final quedó con deuda.',
  UBICACION_TOMADA_AL_SINCRONIZAR:
    'Cuando llegó la venta, el vehículo estaba en rendición o en la jornada de otro vendedor.',
}

/** SYN-07: el texto de pantalla de una observación, con los nombres de la base local. */
export function textoDeObservacion(observacion: ObservacionLocal, nombres: NombresLocales): string {
  const { codigo, detalle } = observacion
  const fijo = FIJOS_DE_OBSERVACION[codigo]
  if (fijo !== undefined) return fijo
  switch (codigo) {
    case 'STOCK_NEGATIVO':
      return `Quedó stock negativo de ${nombreDe(nombres.productos, detalle, 'producto_id', 'un producto')}.`
    case 'VENTA_SIN_COSTO':
      return `${conMayuscula(nombreDe(nombres.productos, detalle, 'producto_id', 'un producto'))} no tenía costo; la línea quedó sin costo.`
    case 'MEDIO_INACTIVO': {
      const medio = medioDe(nombres, detalle)
      return medio === 'un medio'
        ? 'Un medio estaba dado de baja cuando llegó el cobro.'
        : `El medio ${medio} estaba dado de baja cuando llegó el cobro.`
    }
    case 'REFERENCIA_FALTANTE':
      return `El cobro con ${medioDe(nombres, detalle)} llegó sin la referencia que pide ese medio.`
    case 'AUTORIZACION_OFFLINE': {
      const autorizador = nombreDe(nombres.autorizadores, detalle, 'autorizador_id', 'un supervisor')
      return `${conMayuscula(autorizador)} autorizó el ${tipoDeAutorizacion(detalle)} sin señal.`
    }
    default:
      return TEXTO_DE_OBSERVACION_GENERAL
  }
}

const TEXTO_DE_DUPLICADO = 'El sistema ya tenía otra venta con el mismo identificador o número.'
const TEXTO_DE_DATOS_INVALIDOS = 'La venta llegó con datos incompletos o inválidos.'

const TEXTOS_DE_RECHAZO: Readonly<Record<string, string>> = {
  JORNADA_INEXISTENTE: 'La jornada de la venta no existe en el sistema.',
  JORNADA_REQUERIDA: 'La venta llegó sin jornada.',
  JORNADA_AJENA: 'La jornada de la venta es de otro usuario o de otro teléfono.',
  DISPOSITIVO_REVOCADO: 'Este teléfono fue dado de baja; la venta quedó para revisión.',
  COMANDO_INCONSISTENTE: TEXTO_DE_DUPLICADO,
  VENTA_DUPLICADA: TEXTO_DE_DUPLICADO,
  NUMERO_DUPLICADO: TEXTO_DE_DUPLICADO,
  TOTALES_INCONSISTENTES: 'Los importes de la venta no cierran con el cálculo del sistema.',
  CREDITO_INCONSISTENTE: 'La evaluación de crédito del teléfono no es coherente.',
  // El resto (contenido, tipo, versión y modo del comando, y las validaciones de la venta).
  VENTA_SIN_LINEAS: TEXTO_DE_DATOS_INVALIDOS,
  LINEAS_INVALIDAS: TEXTO_DE_DATOS_INVALIDOS,
  CANTIDAD_INVALIDA: TEXTO_DE_DATOS_INVALIDOS,
  LINEA_DUPLICADA: TEXTO_DE_DATOS_INVALIDOS,
  NUMERO_INVALIDO: TEXTO_DE_DATOS_INVALIDOS,
  RECURSO_NO_ENCONTRADO: TEXTO_DE_DATOS_INVALIDOS,
  VERSION_NO_PERMITIDA: TEXTO_DE_DATOS_INVALIDOS,
  MOTIVO_INVALIDO: TEXTO_DE_DATOS_INVALIDOS,
  MODO_NO_ADMITIDO_PARA_TIPO: TEXTO_DE_DATOS_INVALIDOS,
  TIPO_DE_COMANDO_DESCONOCIDO: TEXTO_DE_DATOS_INVALIDOS,
  VERSION_DE_COMANDO_SIN_HANDLER: TEXTO_DE_DATOS_INVALIDOS,
  CONTENIDO_DE_COMANDO_INVALIDO: TEXTO_DE_DATOS_INVALIDOS,
}

export interface TextoDeRechazo {
  texto: string
  codigo: string | null
  /** `false` si el teléfono no conoce el código (texto general). */
  conocido: boolean
}

/** SYN-06: el texto del motivo de un rechazo; un código desconocido da el texto general y el código. */
export function textoDeRechazo(codigo: string | null): TextoDeRechazo {
  const propio = codigo === null ? undefined : TEXTOS_DE_RECHAZO[codigo]
  if (propio === undefined) return { texto: TEXTO_DE_RECHAZO_GENERAL, codigo, conocido: false }
  return { texto: propio, codigo, conocido: true }
}

/** D4: la primera observación y cuántas más hay («1 más», «N más»). */
export function resumenDeObservaciones(textos: readonly string[]): { primera: string; mas: string | null } | null {
  const [primera, ...resto] = textos
  if (primera === undefined) return null
  return { primera, mas: resto.length === 0 ? null : `${resto.length} más` }
}

export type ExplicacionDeEnvio =
  | { tipo: 'observaciones'; textos: string[] }
  | { tipo: 'sin_detalle'; texto: string }
  | { tipo: 'rechazo'; texto: string; codigo: string | null; aviso: string }

/** Lo que el resultado del servidor guardó en la fila de `cola` de la venta. */
export interface ResultadoGuardado {
  error_codigo?: string | null
  observaciones?: ObservacionLocal[]
}

/**
 * D3, D4: explicación de una venta según su estado de envío: sus observaciones traducidas, el
 * aviso de que el detalle no está (aceptada antes del 22c) o el motivo del rechazo. Una «Enviada»
 * o sin enviar no explica nada.
 */
export function explicarEnvio(
  estado: EstadoDeEnvio,
  resultado: ResultadoGuardado | undefined,
  nombres: NombresLocales,
): ExplicacionDeEnvio | null {
  if (estado === 'RECHAZADA') {
    const rechazo = textoDeRechazo(resultado?.error_codigo ?? null)
    return { tipo: 'rechazo', texto: rechazo.texto, codigo: rechazo.codigo, aviso: AVISO_DE_RECHAZO }
  }
  if (estado !== 'CON_OBSERVACIONES') return null
  const observaciones = resultado?.observaciones
  if (observaciones === undefined || observaciones.length === 0) return { tipo: 'sin_detalle', texto: TEXTO_SIN_DETALLE }
  return { tipo: 'observaciones', textos: observaciones.map((o) => textoDeObservacion(o, nombres)) }
}
