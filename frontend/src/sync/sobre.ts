import type { ContenidoDeVentaLocal, SobreEnCola } from '../lib/dispositivo/db'

/**
 * Sobre del comando `VENTA_CONFIRMAR` sin conexión (change 22a, `design.md` D2; `02` §6.2;
 * SYN-01, ADR-056, INV-03). Función pura: arma el ítem del lote tal como lo guarda la cola y
 * lo acepta `POST /api/v1/sync/comandos`. El fixture `shared/fixtures/sync/venta-confirmar-offline.json`
 * fija su forma para el frontend y el backend.
 *
 * - `modo = OFFLINE`, `version = 1`.
 * - El contenido NUNCA lleva `credenciales` ni PIN: el lote las rechaza (ADR-056). La venta
 *   conserva solo el `autorizador_id`.
 * - El objeto `credito` del dispositivo es obligatorio sin conexión (CRE-09).
 * - `occurred_at` en ISO UTC; `app_version` la pasa quien llama (compilación, ver `appVersion.ts`).
 */
export interface EntradaDeSobre {
  operationId: string
  usuarioId: string
  dispositivoId: string
  jornadaId: string
  occurredAt: Date
  secuencia: number
  appVersion: string
  contenido: ContenidoDeVentaLocal
}

export function armarSobreDeVenta(entrada: EntradaDeSobre): SobreEnCola {
  // `credenciales` se descarta por completo: ni el PIN ni su rastro viajan ni se guardan.
  const { credenciales: _credenciales, ...contenido } = entrada.contenido
  void _credenciales
  if (contenido.credito === undefined || contenido.credito === null) {
    throw new Error('Una venta sin conexión necesita su evaluación de crédito (CRE-09).')
  }
  return {
    operation_id: entrada.operationId,
    tipo: 'VENTA_CONFIRMAR',
    version: 1,
    modo: 'OFFLINE',
    usuario_id: entrada.usuarioId,
    dispositivo_id: entrada.dispositivoId,
    jornada_id: entrada.jornadaId,
    occurred_at: entrada.occurredAt.toISOString(),
    secuencia: entrada.secuencia,
    app_version: entrada.appVersion,
    contenido,
  }
}
