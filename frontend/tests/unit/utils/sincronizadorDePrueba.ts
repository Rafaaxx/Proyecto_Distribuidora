import { ESPERA_INICIAL } from '../../../src/sync/espera'
import type { OrigenDeSincronizacion, ResultadoDeSincronizacion, Sincronizador } from '../../../src/sync/sincronizar'

/**
 * Sincronizador de espía para las pruebas de pantallas (change 22b): registra el origen de cada
 * disparo y responde lo que se le indique (por omisión, completa sin enviar nada).
 */
export function sincronizadorDePrueba() {
  const origenes: OrigenDeSincronizacion[] = []
  let responder: () => Promise<ResultadoDeSincronizacion> = async () => ({ tipo: 'completa', enviadas: 0 })
  const sincronizador: Sincronizador = {
    sincronizar: async (entrada) => {
      origenes.push(entrada.origen)
      return responder()
    },
    reiniciarEspera: () => undefined,
    estadoDeEspera: () => ESPERA_INICIAL,
  }
  return {
    origenes,
    sincronizador,
    responderCon: (nuevo: () => Promise<ResultadoDeSincronizacion>) => {
      responder = nuevo
    },
  }
}
