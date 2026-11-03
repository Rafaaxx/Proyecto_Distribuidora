import { derivarAnulacionLocal, ErrorDeAnulacionLocal } from '../domain/ruta/anulacionLocal'
import { siguienteSecuencia } from '../domain/ruta/numeracionLocal'
import { baseLocal, type AnulacionLocal, type ComandoEnCola } from '../lib/dispositivo/db'
import { CLAVE_ULTIMA_SECUENCIA } from './confirmarVentaLocal'
import { armarSobreDeAnulacion } from './sobre'

/**
 * Anulación atómica de una venta de `/ruta` (change 22d, `design.md` D4, D5, D6; **INV-01**,
 * INV-06, VTA-20, VTA-22, VTA-24, SYN-01, SYN-02, SYN-03, `02` §13.2).
 *
 * UNA transacción `rw` de Dexie sobre `sesion`, `meta`, `ventas`, `cobranzas`, `clientes`,
 * `movimientos_locales`, `cola` y `anulaciones`: escribe la anulación, sus movimientos inversos
 * y el comando `VENTA_ANULAR` `OFFLINE` con la siguiente secuencia, y avanza la última
 * secuencia. Si algo falla no queda nada. Quien llama resuelve ANTES, fuera de la transacción, lo
 * que no es de Dexie (el motivo, lo que eligió el vendedor): acá adentro solo hay lecturas y
 * escrituras locales.
 *
 * Anular otra vez la misma venta (doble toque, reintento) no crea otra anulación ni otro comando:
 * devuelve la existente (`repetida`). Una venta «Sin enviar» sí se anula: su anulación queda
 * detrás en la cola (SYN-03).
 */
export interface EntradaDeAnulacionConfirmada {
  ventaId: string
  motivo: { id: string; nombre: string }
  observacion: string | null
  /** Elección del vendedor; `null` si la venta no tuvo cobro. El consumidor final siempre devuelve. */
  devuelveDinero: boolean | null
  /** UUIDv7 de la anulación: se reutiliza al reintentar. */
  operationId: string
  usuarioId: string
  dispositivoId: string
  ahora: Date
  appVersion: string
}

export interface ResultadoDeAnulacion {
  anulacion: AnulacionLocal
  comando: ComandoEnCola
  /** `true` si la venta ya estaba anulada y no se escribió nada. */
  repetida: boolean
}

export async function anularVentaLocal(entrada: EntradaDeAnulacionConfirmada): Promise<ResultadoDeAnulacion> {
  const tablas = [
    baseLocal.sesion,
    baseLocal.meta,
    baseLocal.ventas,
    baseLocal.cobranzas,
    baseLocal.clientes,
    baseLocal.movimientos_locales,
    baseLocal.cola,
    baseLocal.anulaciones,
  ]

  return baseLocal.transaction('rw', tablas, async (): Promise<ResultadoDeAnulacion> => {
    const existente = await baseLocal.anulaciones.get(entrada.ventaId)
    if (existente !== undefined) {
      const comando = await baseLocal.cola.where('operation_id').equals(existente.operation_id).first()
      if (comando === undefined) throw new Error('La anulación local existe pero su comando no está en la cola.')
      return { anulacion: existente, comando, repetida: true }
    }

    const sesion = await baseLocal.sesion.get('actual')
    if (sesion === undefined) throw new Error('No hay sesión local: no se puede anular la venta.')

    const venta = await baseLocal.ventas.get(entrada.ventaId)
    if (venta === undefined || venta.jornada_id !== sesion.jornada.id || venta.estado_envio === 'RECHAZADA') {
      throw new ErrorDeAnulacionLocal('VENTA_NO_ANULABLE', 'La venta no se puede anular desde este teléfono.')
    }

    const cobranza = (await baseLocal.cobranzas.where('venta_id').equals(venta.venta_id).first()) ?? null
    const movimientosDeVenta = await baseLocal.movimientos_locales.where('operation_id').equals(venta.operation_id).toArray()
    const esConsumidorFinal =
      venta.nota?.cliente.es_consumidor_final ?? (await baseLocal.clientes.get(venta.cliente_id))?.es_consumidor_final ?? false

    const { anulacion, movimientos } = derivarAnulacionLocal({
      venta,
      cobranza,
      movimientosDeVenta,
      esConsumidorFinal,
      motivo: entrada.motivo,
      observacion: entrada.observacion,
      devuelveDinero: entrada.devuelveDinero,
      operationId: entrada.operationId,
      occurredAt: entrada.ahora.toISOString(),
    })

    const ultimaSecuencia = (await baseLocal.meta.get(CLAVE_ULTIMA_SECUENCIA))?.valor
    const secuencia = siguienteSecuencia(ultimaSecuencia === undefined ? null : Number(ultimaSecuencia))
    const sobre = armarSobreDeAnulacion({
      operationId: entrada.operationId,
      usuarioId: entrada.usuarioId,
      dispositivoId: entrada.dispositivoId,
      jornadaId: sesion.jornada.id,
      occurredAt: entrada.ahora,
      secuencia,
      appVersion: entrada.appVersion,
      ventaId: venta.venta_id,
      motivoId: anulacion.motivo_id,
      observacion: anulacion.observacion,
      devuelveDinero: anulacion.devuelve_dinero,
    })
    const comando: ComandoEnCola = { secuencia, operation_id: entrada.operationId, estado: 'PENDIENTE', sobre }

    await baseLocal.anulaciones.add(anulacion)
    await baseLocal.movimientos_locales.bulkAdd(movimientos)
    await baseLocal.cola.add(comando)
    await baseLocal.meta.put({ clave: CLAVE_ULTIMA_SECUENCIA, valor: String(secuencia) })

    return { anulacion, comando, repetida: false }
  })
}
