import { z } from 'zod'

import { aImporte, normalizarDecimal } from '../precios/decimales'
import { DIRECCIONES_REDONDEO, multiplo } from '../precios/listaSchema'

/**
 * Motivos, alícuotas de IVA y redondeo por defecto (change 20c, `design.md` D7, D12; TR-02,
 * TR-09, INV-03). Solo UX: el servidor valida igual. Todo el cálculo con decimal.js, nunca `number`.
 */

// --- ámbitos de motivo -----------------------------------------------------------------------

export const AMBITOS_DE_MOTIVO = [
  'AJUSTE_STOCK',
  'ANULACION_VENTA',
  'ANULACION_COMPRA',
  'ANULACION_COBRANZA',
  'ANULACION_PAGO',
  'ANULACION_TRANSFERENCIA',
  'ANULACION_AJUSTE',
  'DESCUENTO_MANUAL',
  'LISTA_ANTERIOR',
  'LIBERACION_JORNADA',
] as const
export type AmbitoDeMotivo = (typeof AMBITOS_DE_MOTIVO)[number]

export const NOMBRE_DE_AMBITO: Record<AmbitoDeMotivo, string> = {
  AJUSTE_STOCK: 'Ajuste de stock',
  ANULACION_VENTA: 'Anulación de venta',
  ANULACION_COMPRA: 'Anulación de compra',
  ANULACION_COBRANZA: 'Anulación de cobranza',
  ANULACION_PAGO: 'Anulación de pago a proveedor',
  ANULACION_TRANSFERENCIA: 'Anulación de transferencia',
  ANULACION_AJUSTE: 'Anulación de ajuste',
  DESCUENTO_MANUAL: 'Descuento manual',
  LISTA_ANTERIOR: 'Venta con lista anterior',
  LIBERACION_JORNADA: 'Liberación de jornada',
}

// --- porcentaje <-> fracción -----------------------------------------------------------------

const PATRON_PORCENTAJE = /^\d+(\.\d{1,4})?$/

/**
 * Porcentaje que escribe el usuario (`"10,5"`) a la fracción que viaja a la API (`"0.105000"`,
 * TR-02). División exacta por 100: con a lo sumo 4 decimales el resultado entra en 6. Devuelve
 * `null` si no es un número, es negativo, tiene más de 4 decimales o es 100 o más.
 */
export function porcentajeAFraccion(texto: string): string | null {
  const normalizado = normalizarDecimal(texto)
  if (!PATRON_PORCENTAJE.test(normalizado)) return null
  const porcentaje = aImporte(normalizado)
  if (porcentaje.gte(100)) return null
  return porcentaje.div(100).toFixed(6)
}

/** Fracción de la API (`"0.105000"`) al porcentaje para mostrar y editar (`"10,5"`). */
export function fraccionAPorcentaje(fraccion: string): string {
  return aImporte(fraccion).times(100).toFixed().replace('.', ',')
}

// --- formularios -----------------------------------------------------------------------------

export const esquemaMotivo = z.object({
  nombre: z.string().trim().min(1, 'Escribí un nombre para el motivo.'),
})
export type DatosDeMotivo = z.output<typeof esquemaMotivo>

export const esquemaAlicuota = z
  .object({
    nombre: z.string().trim().min(1, 'Escribí un nombre para la alícuota.'),
    porcentaje: z.string(),
  })
  .transform((datos, contexto) => {
    const valor = porcentajeAFraccion(datos.porcentaje)
    if (valor === null) {
      contexto.addIssue({
        code: 'custom',
        path: ['porcentaje'],
        message: 'Ingresá un porcentaje de 0 a menos de 100, con hasta cuatro decimales.',
      })
      return z.NEVER
    }
    return { nombre: datos.nombre, valor }
  })
export type DatosDeAlicuotaEntrada = z.input<typeof esquemaAlicuota>
export type DatosDeAlicuota = z.output<typeof esquemaAlicuota>

export const esquemaRedondeoPorDefecto = z.object({
  redondeo_multiplo: multiplo,
  redondeo_direccion: z.enum(DIRECCIONES_REDONDEO, { message: 'Elegí una dirección de redondeo.' }),
})
export type DatosDeRedondeoEntrada = z.input<typeof esquemaRedondeoPorDefecto>
export type DatosDeRedondeo = z.output<typeof esquemaRedondeoPorDefecto>

// --- mensajes de los rechazos del servidor ----------------------------------------------------

const MENSAJES_DE_MOTIVO: Record<string, string> = {
  NOMBRE_DUPLICADO:
    'Ya hay un motivo con ese nombre en este ámbito (aunque esté de baja). Elegí otro, o reactivá el que ya existe.',
  NOMBRE_INVALIDO: 'Escribí un nombre para el motivo.',
  ULTIMO_MOTIVO_ACTIVO:
    'Cada ámbito tiene que conservar al menos un motivo activo. Creá o reactivá otro antes de dar de baja este.',
}

export function mensajeDeErrorDeMotivo(codigo: string | null, mensajeDelServidor: string): string {
  return (codigo !== null ? MENSAJES_DE_MOTIVO[codigo] : undefined) ?? mensajeDelServidor
}

function productosEnUso(cantidad: number | undefined): string {
  if (cantidad === undefined) return 'productos activos'
  return cantidad === 1 ? '1 producto activo' : `${cantidad} productos activos`
}

/** `productos`: la cantidad que informa `ALICUOTA_EN_USO` en el Problem Details. */
export function mensajeDeErrorDeAlicuota(codigo: string | null, mensajeDelServidor: string, productos?: number): string {
  switch (codigo) {
    case 'NOMBRE_DUPLICADO':
      return 'Ya hay una alícuota con ese nombre (aunque esté de baja). Elegí otro, o reactivá la que ya existe.'
    case 'NOMBRE_INVALIDO':
      return 'Escribí un nombre para la alícuota.'
    case 'VALOR_DUPLICADO':
      return 'Ya hay una alícuota con ese porcentaje (aunque esté de baja). Reactivá esa en vez de crear otra.'
    case 'ULTIMA_ALICUOTA_ACTIVA':
      return 'Tiene que quedar al menos una alícuota activa. Creá o reactivá otra antes de dar de baja esta.'
    case 'ALICUOTA_EN_USO':
      return `No se puede dar de baja: la usan ${productosEnUso(productos)}. Pasá esos productos a otra alícuota primero.`
    case 'VALOR_NO_MODIFICABLE':
      return 'El porcentaje de una alícuota no se cambia. Creá una nueva con el porcentaje que necesitás.'
    default:
      return mensajeDelServidor
  }
}

export function mensajeDeErrorDeRedondeo(codigo: string | null, mensajeDelServidor: string): string {
  return codigo === 'REDONDEO_INVALIDO'
    ? 'Ingresá un múltiplo mayor que cero, con hasta dos decimales, y elegí la dirección.'
    : mensajeDelServidor
}
