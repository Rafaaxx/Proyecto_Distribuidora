import type { components } from '../../api/schema.gen'
import type { CuentaTipo } from '../../domain/cuentas-corrientes/presentacion'
import { apiFetch } from '../../lib/api/httpClient'
import type { FiltrosEstadoDeCuenta } from './claves'
import { errorDesdeRespuesta } from './errores'

/**
 * Acceso a la API de cuentas corrientes (change 08, grupo 7, tarea 7.1).
 * Tipado contra `schema.gen.ts` -- nunca `any`.
 *
 * La lectura vive con su entidad (`02` §11): el estado de cuenta de un cliente
 * en `/clientes/{id}/cuenta-corriente` y el de un proveedor en
 * `/proveedores/{id}/cuenta-corriente`. La única escritura es
 * `POST /cuentas-corrientes/saldos-iniciales` (`SALDO_INICIAL_REGISTRAR`,
 * `ONLINE`): el `Operation-Id` lo genera y conserva quien llama (el hook de
 * mutación) para que el reintento reenvíe exactamente el mismo valor
 * (INV-06). Los importes viajan y vuelven como string (INV-03).
 */

export type EstadoDeCuenta = components['schemas']['EstadoDeCuentaResponse']
export type MovimientoDeCuenta = components['schemas']['MovimientoEstadoDeCuentaResponse']
export type SaldoInicialDatos = components['schemas']['SaldoInicialRegistrarRequest']
export type SaldoInicialResultado = components['schemas']['SaldoInicialResponse']

/** Tamaño de página por defecto del estado de cuenta (`design.md` D9). */
export const LIMITE_POR_DEFECTO = 50

async function leerJsonOLanzar<T>(respuesta: Response): Promise<T> {
  if (!respuesta.ok) {
    throw await errorDesdeRespuesta(respuesta)
  }
  return (await respuesta.json()) as T
}

function rutaDeCuenta(cuentaTipo: CuentaTipo, entidadId: string): string {
  const coleccion = cuentaTipo === 'CLIENTE' ? 'clientes' : 'proveedores'
  return `/${coleccion}/${entidadId}/cuenta-corriente`
}

export async function obtenerEstadoDeCuenta(
  cuentaTipo: CuentaTipo,
  entidadId: string,
  filtros: FiltrosEstadoDeCuenta = {},
  cursor?: string,
  limite: number = LIMITE_POR_DEFECTO,
): Promise<EstadoDeCuenta> {
  const params = new URLSearchParams()
  params.set('limite', String(limite))
  if (cursor) params.set('cursor', cursor)
  if (filtros.desde) params.set('desde', filtros.desde)
  if (filtros.hasta) params.set('hasta', filtros.hasta)
  const respuesta = await apiFetch(`${rutaDeCuenta(cuentaTipo, entidadId)}?${params.toString()}`)
  return leerJsonOLanzar(respuesta)
}

export async function registrarSaldoInicial(
  datos: SaldoInicialDatos,
  operationId: string,
): Promise<SaldoInicialResultado> {
  const respuesta = await apiFetch('/cuentas-corrientes/saldos-iniciales', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Operation-Id': operationId },
    body: JSON.stringify(datos),
  })
  return leerJsonOLanzar(respuesta)
}
