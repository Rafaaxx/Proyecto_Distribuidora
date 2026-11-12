import { siguienteSecuencia } from '../domain/ruta/numeracionLocal'
import { baseLocal, type CobranzaLocal, type ComandoEnCola, type MovimientoLocal } from '../lib/dispositivo/db'
import { CLAVE_ULTIMA_SECUENCIA } from './confirmarVentaLocal'
import { armarSobreDeCobranza, type MedioDeSobreDeCobranza } from './sobre'

/**
 * Cobranza atómica de `/ruta` (change 23, `design.md` D1, D5; **INV-01**, INV-06, COB-01, COB-04,
 * SYN-01, SYN-02, SYN-03, `02` §13.2).
 *
 * UNA transacción `rw` de Dexie sobre `sesion`, `meta`, `clientes`, `catalogos`, `cobranzas`,
 * `movimientos_locales` y `cola`: escribe la cobranza (origen `INDEPENDIENTE`, «Sin enviar»), un
 * `COBRANZA_CREDITO` con el `operation_id` de la cobranza y el comando `COBRANZA_REGISTRAR`
 * `OFFLINE` con la siguiente secuencia, y avanza la última secuencia. Si algo falla no queda
 * nada. Quien llama valida ANTES el formulario (`domain/ruta/cobranzaLocal.ts`) y dispara la
 * sincronización DESPUÉS (`dispararTrasVenta`), como la venta y la anulación: acá adentro solo
 * hay lecturas y escrituras locales.
 *
 * Confirmar otra vez la misma cobranza (doble toque, reintento) no crea otra cobranza ni otro
 * comando: devuelve la existente (`repetida`); los identificadores se generan al abrir el
 * formulario y se reutilizan al reintentar.
 */
export interface EntradaDeCobranzaConfirmada {
  /** UUIDv7 de la cobranza, generado al abrir el formulario. */
  cobranzaId: string
  /** UUIDv7 de la operación: se reutiliza al reintentar. */
  operationId: string
  clienteId: string
  /** Importe ya validado, string de dos decimales (INV-03). */
  importe: string
  medios: MedioDeSobreDeCobranza[]
  observacion: string | null
  usuarioId: string
  dispositivoId: string
  ahora: Date
  appVersion: string
}

export interface ResultadoDeCobranzaLocal {
  cobranza: CobranzaLocal
  comando: ComandoEnCola
  /** `true` si la cobranza ya estaba registrada y no se escribió nada. */
  repetida: boolean
}

export async function registrarCobranzaLocal(entrada: EntradaDeCobranzaConfirmada): Promise<ResultadoDeCobranzaLocal> {
  const tablas = [
    baseLocal.sesion,
    baseLocal.meta,
    baseLocal.clientes,
    baseLocal.catalogos,
    baseLocal.cobranzas,
    baseLocal.movimientos_locales,
    baseLocal.cola,
  ]

  return baseLocal.transaction('rw', tablas, async (): Promise<ResultadoDeCobranzaLocal> => {
    const existente = await baseLocal.cobranzas.get(entrada.cobranzaId)
    if (existente !== undefined) {
      const comando = await baseLocal.cola.where('operation_id').equals(existente.operation_id).first()
      if (comando === undefined) throw new Error('La cobranza local existe pero su comando no está en la cola.')
      return { cobranza: existente, comando, repetida: true }
    }

    const sesion = await baseLocal.sesion.get('actual')
    if (sesion === undefined) throw new Error('No hay sesión local: no se puede registrar la cobranza.')

    const cliente = await baseLocal.clientes.get(entrada.clienteId)
    const catalogo = await baseLocal.catalogos.get('medios_pago')
    const nombresDeMedios = new Map((catalogo?.clave === 'medios_pago' ? catalogo.items : []).map((m) => [m.id, m.nombre]))

    const ultimaSecuencia = (await baseLocal.meta.get(CLAVE_ULTIMA_SECUENCIA))?.valor
    const secuencia = siguienteSecuencia(ultimaSecuencia === undefined ? null : Number(ultimaSecuencia))
    const jornadaId = sesion.jornada.id

    const cobranza: CobranzaLocal = {
      cobranza_id: entrada.cobranzaId,
      venta_id: null,
      operation_id: entrada.operationId,
      jornada_id: jornadaId,
      origen: 'INDEPENDIENTE',
      cliente_id: entrada.clienteId,
      cliente_nombre: cliente?.nombre ?? '—',
      vendedor_nombre: sesion.usuario.nombre,
      occurred_at: entrada.ahora.toISOString(),
      observacion: entrada.observacion,
      estado_envio: 'PENDIENTE',
      medios: entrada.medios.map((m) => ({ medio_pago_id: m.medio_pago_id, importe: m.importe, referencia: m.referencia })),
      medios_nombres: entrada.medios.map((m) => ({
        medio_pago_id: m.medio_pago_id,
        nombre: nombresDeMedios.get(m.medio_pago_id) ?? '—',
      })),
      total: entrada.importe,
    }
    const movimiento: MovimientoLocal = {
      operation_id: entrada.operationId,
      jornada_id: jornadaId,
      tipo: 'COBRANZA_CREDITO',
      producto_id: null,
      cliente_id: entrada.clienteId,
      cantidad_base: null,
      importe: entrada.importe,
      estado_operacion: 'PENDIENTE',
    }
    const sobre = armarSobreDeCobranza({
      operationId: entrada.operationId,
      usuarioId: entrada.usuarioId,
      dispositivoId: entrada.dispositivoId,
      jornadaId,
      occurredAt: entrada.ahora,
      secuencia,
      appVersion: entrada.appVersion,
      cobranzaId: entrada.cobranzaId,
      clienteId: entrada.clienteId,
      importe: entrada.importe,
      medios: entrada.medios,
      observacion: entrada.observacion,
    })
    const comando: ComandoEnCola = { secuencia, operation_id: entrada.operationId, estado: 'PENDIENTE', sobre }

    await baseLocal.cobranzas.add(cobranza)
    await baseLocal.movimientos_locales.add(movimiento)
    await baseLocal.cola.add(comando)
    await baseLocal.meta.put({ clave: CLAVE_ULTIMA_SECUENCIA, valor: String(secuencia) })

    return { cobranza, comando, repetida: false }
  })
}
