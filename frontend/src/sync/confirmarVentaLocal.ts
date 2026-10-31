import type { ResultadoVenta } from '../domain/calculo'
import { siguienteNumeroLocal, siguienteSecuencia } from '../domain/ruta/numeracionLocal'
import { derivarOperacionesLocales, type LineaBaseDeVenta } from '../domain/ruta/ventaLocal'
import { baseLocal, type ComandoEnCola, type ContenidoDeVentaLocal, type NotaCongelada, type VentaLocal } from '../lib/dispositivo/db'
import { armarSobreDeVenta } from './sobre'

/**
 * Confirmación atómica de una venta de `/ruta` (change 22a, `design.md` D4; INV-01, INV-06,
 * VTA-06, SYN-02, SYN-03, `02` §13.2).
 *
 * UNA transacción `rw` de Dexie sobre `sesion`, `meta`, `ventas`, `cobranzas`,
 * `movimientos_locales` y `cola`: lee los dos contadores, asigna número y secuencia, escribe
 * venta, cobranza, movimientos y comando y actualiza los contadores. Si algo falla no queda
 * nada y los contadores no avanzan. Quien llama resuelve ANTES, fuera de la transacción, el
 * cálculo, las reglas y la verificación del PIN (Dexie no admite esperas ajenas dentro de
 * ella): acá adentro solo hay lecturas y escrituras de Dexie.
 *
 * Reconfirmar con el mismo `venta_id` (doble toque, reintento tras un error) no crea otra venta
 * ni otro comando: devuelve la existente (`repetida`).
 */
export const CLAVE_ULTIMO_CORRELATIVO = 'ultimo_correlativo'
export const CLAVE_ULTIMA_SECUENCIA = 'ultima_secuencia'

export interface EntradaDeConfirmacion {
  /** Contenido del comando, ya armado; su `numero` se reasigna dentro de la transacción. */
  contenido: ContenidoDeVentaLocal
  calculo: ResultadoVenta
  lineas: readonly LineaBaseDeVenta[]
  /** UUIDv7 del carrito: se reutiliza al reintentar. */
  operationId: string
  usuarioId: string
  dispositivoId: string
  ahora: Date
  appVersion: string
  /** Datos congelados de la nota (D15); los completa el Lote 4. */
  nota: NotaCongelada | null
}

export interface ResultadoDeConfirmacion {
  venta: VentaLocal
  comando: ComandoEnCola
  /** `true` si la venta ya estaba confirmada y no se escribió nada. */
  repetida: boolean
}

function contador(valor: string | undefined): number | null {
  return valor === undefined ? null : Number(valor)
}

export async function confirmarVentaLocal(entrada: EntradaDeConfirmacion): Promise<ResultadoDeConfirmacion> {
  const tablas = [
    baseLocal.sesion,
    baseLocal.meta,
    baseLocal.ventas,
    baseLocal.cobranzas,
    baseLocal.movimientos_locales,
    baseLocal.cola,
  ]

  return baseLocal.transaction('rw', tablas, async (): Promise<ResultadoDeConfirmacion> => {
    const existente = await baseLocal.ventas.get(entrada.contenido.venta_id)
    if (existente !== undefined) {
      const comando = await baseLocal.cola.where('operation_id').equals(existente.operation_id).first()
      if (comando === undefined) throw new Error('La venta local existe pero su comando no está en la cola.')
      return { venta: existente, comando, repetida: true }
    }

    const sesion = await baseLocal.sesion.get('actual')
    if (sesion === undefined) throw new Error('No hay sesión local: no se puede numerar la venta.')

    const ultimoCorrelativo = contador((await baseLocal.meta.get(CLAVE_ULTIMO_CORRELATIVO))?.valor)
    const ultimaSecuencia = contador((await baseLocal.meta.get(CLAVE_ULTIMA_SECUENCIA))?.valor)
    const { numero, correlativo } = siguienteNumeroLocal({
      prefijo: sesion.numeracion.prefijo,
      ultimoCorrelativoBootstrap: sesion.numeracion.ultimo_correlativo,
      ultimoCorrelativoLocal: ultimoCorrelativo,
    })
    const secuencia = siguienteSecuencia(ultimaSecuencia)

    const contenido: ContenidoDeVentaLocal = { ...entrada.contenido, numero }
    const { venta, cobranza, movimientos } = derivarOperacionesLocales({
      contenido,
      calculo: entrada.calculo,
      lineas: entrada.lineas,
      jornadaId: sesion.jornada.id,
      operationId: entrada.operationId,
      occurredAt: entrada.ahora.toISOString(),
      nota: entrada.nota,
    })
    const sobre = armarSobreDeVenta({
      operationId: entrada.operationId,
      usuarioId: entrada.usuarioId,
      dispositivoId: entrada.dispositivoId,
      jornadaId: sesion.jornada.id,
      occurredAt: entrada.ahora,
      secuencia,
      appVersion: entrada.appVersion,
      contenido,
    })
    const comando: ComandoEnCola = { secuencia, operation_id: entrada.operationId, estado: 'PENDIENTE', sobre }

    await baseLocal.ventas.add(venta)
    if (cobranza !== null) await baseLocal.cobranzas.add(cobranza)
    await baseLocal.movimientos_locales.bulkAdd(movimientos)
    await baseLocal.cola.add(comando)
    await baseLocal.meta.bulkPut([
      { clave: CLAVE_ULTIMO_CORRELATIVO, valor: String(correlativo) },
      { clave: CLAVE_ULTIMA_SECUENCIA, valor: String(secuencia) },
    ])

    return { venta, comando, repetida: false }
  })
}
