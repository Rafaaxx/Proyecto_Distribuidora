import { baseLocal, type EstadoDeComando, type EstadoDeEnvio } from '../lib/dispositivo/db'
import type { ResultadoDeItem } from './clienteLote'

/**
 * Escribe en el teléfono el resultado de cada operación del lote (change 22b, `design.md` D3, D4;
 * **INV-01**, SYN-04, SYN-09). Una transacción `rw` por respuesta: o se aplican todos o ninguno.
 * Se busca por `operation_id`, nunca por posición. Nada se borra: la cola queda como constancia y
 * `estado_operacion` de los movimientos NO se toca (lo concilia el 22c): el stock y el saldo
 * locales siguen contando la venta.
 */
const DESTINO_POR_ESTADO: Record<string, { comando: EstadoDeComando; venta: EstadoDeEnvio }> = {
  ACEPTADO: { comando: 'ACEPTADO', venta: 'ACEPTADA' },
  ACEPTADO_CON_OBSERVACIONES: { comando: 'ACEPTADO_CON_OBSERVACIONES', venta: 'CON_OBSERVACIONES' },
  RECHAZADO: { comando: 'RECHAZADO', venta: 'RECHAZADA' },
}

export interface ResumenDeAplicacion {
  aplicados: number
  ignorados: number
}

export async function aplicarResultados(resultados: ResultadoDeItem[], ahora: Date): Promise<ResumenDeAplicacion> {
  return baseLocal.transaction('rw', [baseLocal.cola, baseLocal.ventas], async (): Promise<ResumenDeAplicacion> => {
    let aplicados = 0
    let ignorados = 0
    for (const item of resultados) {
      const comando = await baseLocal.cola.where('operation_id').equals(item.operation_id).first()
      if (comando === undefined) {
        console.warn(`Sincronización: resultado de una operación desconocida (${item.operation_id}); se ignora.`)
        ignorados += 1
        continue
      }
      // `ERROR_TRANSITORIO` y cualquier estado no final dejan la operación PENDIENTE.
      const destino = DESTINO_POR_ESTADO[item.estado]
      if (destino === undefined || comando.estado === destino.comando) continue

      await baseLocal.cola.put({
        ...comando,
        estado: destino.comando,
        error_codigo: item.error_codigo,
        resultado_en: ahora.toISOString(),
      })
      await baseLocal.ventas.where('operation_id').equals(item.operation_id).modify({ estado_envio: destino.venta })
      aplicados += 1
    }
    return { aplicados, ignorados }
  })
}
