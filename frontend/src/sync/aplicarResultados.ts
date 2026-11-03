import { baseLocal, type EstadoDeComando, type EstadoDeEnvio } from '../lib/dispositivo/db'
import type { ResultadoDeItem } from './clienteLote'
import { marcarJornadaNoAbierta } from './estadoDeJornada'

/**
 * Escribe en el teléfono el resultado de cada operación del lote (change 22b, `design.md` D3, D4;
 * **INV-01**, SYN-04, SYN-09). Una transacción `rw` por respuesta: o se aplican todos o ninguno.
 * Se busca por `operation_id`, nunca por posición. Nada se borra: la cola queda como constancia y
 * `estado_operacion` de los movimientos NO se toca (desde el 22c ni se usa): el stock y el saldo
 * locales siguen contando la venta hasta que un bootstrap la incluya (marca de secuencia, D1).
 *
 * Change 22d (D6): el resultado de un `VENTA_ANULAR` cambia el estado de la ANULACIÓN (tabla
 * `anulaciones`, por `operation_id`) y el de su comando; el estado de envío de la venta anulada no
 * se toca. Todo en la misma transacción.
 */
const DESTINO_POR_ESTADO: Record<string, { comando: EstadoDeComando; venta: EstadoDeEnvio }> = {
  ACEPTADO: { comando: 'ACEPTADO', venta: 'ACEPTADA' },
  ACEPTADO_CON_OBSERVACIONES: { comando: 'ACEPTADO_CON_OBSERVACIONES', venta: 'CON_OBSERVACIONES' },
  RECHAZADO: { comando: 'RECHAZADO', venta: 'RECHAZADA' },
}

const TIPO_DE_ANULACION = 'VENTA_ANULAR'
const OBSERVACION_JORNADA_LIBERADA = 'JORNADA_LIBERADA'

export interface ResumenDeAplicacion {
  aplicados: number
  ignorados: number
}

export async function aplicarResultados(resultados: ResultadoDeItem[], ahora: Date): Promise<ResumenDeAplicacion> {
  const tablas = [baseLocal.cola, baseLocal.ventas, baseLocal.anulaciones, baseLocal.sesion, baseLocal.meta]
  return baseLocal.transaction('rw', tablas, async (): Promise<ResumenDeAplicacion> => {
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
        // Change 22c, D3: las observaciones viajan en la misma escritura (INV-01); sin la lista no hay dato.
        ...(item.observaciones === undefined ? {} : { observaciones: item.observaciones }),
      })
      if (comando.sobre.tipo === TIPO_DE_ANULACION) {
        await baseLocal.anulaciones.where('operation_id').equals(item.operation_id).modify({ estado_envio: destino.venta })
      } else {
        await baseLocal.ventas.where('operation_id').equals(item.operation_id).modify({ estado_envio: destino.venta })
      }
      // Change 22d (D8): una `JORNADA_LIBERADA` sobre una operación de la jornada de la sesión.
      if (item.observaciones?.some((o) => o.codigo === OBSERVACION_JORNADA_LIBERADA) === true && comando.sobre.jornada_id) {
        await marcarJornadaNoAbierta(comando.sobre.jornada_id, 'LIBERADA', ahora)
      }
      aplicados += 1
    }
    return { aplicados, ignorados }
  })
}
