import { baseLocal, type ComandoEnCola, type SobreEnCola, type VentaLocal } from '../../../src/lib/dispositivo/db'

/** Comando de cola mínimo para las pruebas del motor de sincronización (change 22b). */
export function comandoDePrueba(
  secuencia: number,
  opciones: {
    usuarioId?: string
    dispositivoId?: string
    jornadaId?: string
    estado?: ComandoEnCola['estado']
    operationId?: string
  } = {},
): ComandoEnCola {
  const operationId = opciones.operationId ?? `op-${secuencia}`
  const sobre = {
    operation_id: operationId,
    tipo: 'VENTA_CONFIRMAR',
    version: 1,
    modo: 'OFFLINE',
    usuario_id: opciones.usuarioId ?? 'u1',
    dispositivo_id: opciones.dispositivoId ?? 'd1',
    jornada_id: opciones.jornadaId ?? 'j1',
    occurred_at: '2026-11-01T10:00:00.000Z',
    secuencia,
    app_version: '1.0.0',
    contenido: { venta_id: `venta-${secuencia}` },
  } as SobreEnCola
  return { secuencia, operation_id: operationId, estado: opciones.estado ?? 'PENDIENTE', sobre }
}

/** Escribe el comando y, si se pide, una venta mínima con su mismo `operation_id`. */
export async function sembrarComando(comando: ComandoEnCola, conVenta = true): Promise<void> {
  await baseLocal.cola.put(comando)
  if (!conVenta) return
  const venta = {
    venta_id: `venta-${comando.secuencia}`,
    operation_id: comando.operation_id,
    numero: `0001-${String(comando.secuencia).padStart(6, '0')}`,
    cliente_id: 'c1',
    jornada_id: comando.sobre.jornada_id ?? 'j1',
    occurred_at: comando.sobre.occurred_at,
    estado_envio: 'PENDIENTE',
  } as unknown as VentaLocal
  await baseLocal.ventas.put(venta)
}
