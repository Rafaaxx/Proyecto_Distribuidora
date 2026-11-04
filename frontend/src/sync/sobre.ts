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

/**
 * Sobre del comando `VENTA_ANULAR` sin conexión (change 22d, `design.md` D1, D4, D6; VTA-24,
 * VTA-22, SYN-01, SYN-03). Función pura; el fixture `shared/fixtures/sync/venta-anular-offline.json`
 * fija su forma. `devuelve_dinero` se OMITE cuando la venta no tuvo cobro en el acto (`null`).
 * El contenido nunca lleva credenciales ni importes: el servidor deriva todo de la venta.
 */
export interface EntradaDeSobreDeAnulacion {
  operationId: string
  usuarioId: string
  dispositivoId: string
  jornadaId: string
  occurredAt: Date
  secuencia: number
  appVersion: string
  ventaId: string
  motivoId: string
  observacion: string | null
  devuelveDinero: boolean | null
}

export function armarSobreDeAnulacion(entrada: EntradaDeSobreDeAnulacion): SobreEnCola {
  return {
    operation_id: entrada.operationId,
    tipo: 'VENTA_ANULAR',
    version: 1,
    modo: 'OFFLINE',
    usuario_id: entrada.usuarioId,
    dispositivo_id: entrada.dispositivoId,
    jornada_id: entrada.jornadaId,
    occurred_at: entrada.occurredAt.toISOString(),
    secuencia: entrada.secuencia,
    app_version: entrada.appVersion,
    contenido: {
      venta_id: entrada.ventaId,
      motivo_id: entrada.motivoId,
      observacion: entrada.observacion,
      ...(entrada.devuelveDinero === null ? {} : { devuelve_dinero: entrada.devuelveDinero }),
    },
  }
}

/**
 * Sobre del comando `COBRANZA_REGISTRAR` sin conexión (change 23, `design.md` D1, D2; COB-01,
 * COB-02, SYN-01, SYN-03, INV-03). Función pura; el fixture
 * `shared/fixtures/sync/cobranza-registrar-offline.json` fija su forma. Los importes viajan como
 * string; la referencia vacía y la observación ausente, como `null`. El contenido nunca lleva
 * credenciales ni la organización (sale del token, INV-21).
 */
export interface MedioDeSobreDeCobranza {
  medio_pago_id: string
  importe: string
  referencia: string | null
}

export interface EntradaDeSobreDeCobranza {
  operationId: string
  usuarioId: string
  dispositivoId: string
  jornadaId: string
  occurredAt: Date
  secuencia: number
  appVersion: string
  cobranzaId: string
  clienteId: string
  importe: string
  medios: MedioDeSobreDeCobranza[]
  observacion: string | null
}

export function armarSobreDeCobranza(entrada: EntradaDeSobreDeCobranza): SobreEnCola {
  return {
    operation_id: entrada.operationId,
    tipo: 'COBRANZA_REGISTRAR',
    version: 1,
    modo: 'OFFLINE',
    usuario_id: entrada.usuarioId,
    dispositivo_id: entrada.dispositivoId,
    jornada_id: entrada.jornadaId,
    occurred_at: entrada.occurredAt.toISOString(),
    secuencia: entrada.secuencia,
    app_version: entrada.appVersion,
    contenido: {
      cobranza_id: entrada.cobranzaId,
      cliente_id: entrada.clienteId,
      importe: entrada.importe,
      medios: entrada.medios.map((medio) => ({
        medio_pago_id: medio.medio_pago_id,
        importe: medio.importe,
        referencia: medio.referencia,
      })),
      observacion: entrada.observacion,
    },
  }
}
