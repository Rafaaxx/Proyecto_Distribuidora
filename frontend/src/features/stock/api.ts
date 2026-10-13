import type { components } from '../../api/schema.gen'
import { apiFetch } from '../../lib/api/httpClient'
import type { FiltrosAjustes, FiltrosJornadas, FiltrosKardex, FiltrosTransferencias } from './claves'
import { errorDesdeRespuesta } from './errores'

/**
 * Acceso a la API de stock (change 09, grupo 8, tarea 8.1). Tipado contra
 * `schema.gen.ts` -- nunca `any`.
 *
 * Escrituras (`ONLINE`, sin cola): `POST /stock/ubicaciones`,
 * `PUT /stock/ubicaciones/{id}` y `POST /stock/iniciales`. El `Operation-Id` lo
 * genera y conserva quien llama para que el reintento reenvíe el mismo valor
 * (INV-06). Lecturas: ubicaciones, saldos y kardex de `/stock`, y el costo
 * promedio de `/catalogo/productos/{id}/costo` (enmienda a D3, solo `VER_COSTOS`).
 * Los costos viajan y vuelven como string (INV-03); las cantidades, como enteros
 * en unidad base (INV-04).
 */

export type Ubicacion = components['schemas']['UbicacionResponse']
export type PaginaUbicaciones = components['schemas']['PaginaUbicaciones']
export type UbicacionCrearDatos = components['schemas']['UbicacionCrearRequest']
export type UbicacionModificarDatos = components['schemas']['UbicacionModificarRequest']
export type StockDeUbicacion = components['schemas']['StockDeUbicacionResponse']
export type LineaDeStock = components['schemas']['LineaDeStockResponse']
export type Kardex = components['schemas']['KardexResponse']
export type LineaDeKardex = components['schemas']['LineaDeKardexResponse']
export type StockInicialDatos = components['schemas']['StockInicialRegistrarRequest']
export type StockInicialResultado = components['schemas']['StockInicialResponse']
export type CostoPromedio = components['schemas']['CostoPromedioResponse']
export type TransferenciaDatos = components['schemas']['TransferenciaCrearRequest']
export type TransferenciaResultado = components['schemas']['TransferenciaResponse']
export type TransferenciaAnuladaResultado = components['schemas']['TransferenciaAnuladaResponse']
export type TransferenciaDelListado = components['schemas']['TransferenciaDelListadoResponse']
export type PaginaTransferencias = components['schemas']['PaginaDeTransferenciasResponse']
export type TransferenciaDetalle = components['schemas']['DetalleDeTransferenciaResponse']
export type LineaDeTransferencia = components['schemas']['LineaDelDetalleDeTransferenciaResponse']
export type AjusteDatos = components['schemas']['AjusteCrearRequest']
export type AjusteResultado = components['schemas']['AjusteResponse']
export type AjusteAnuladoResultado = components['schemas']['AjusteAnuladoResponse']
export type AjusteDelListado = components['schemas']['AjusteDelListadoResponse']
export type PaginaAjustes = components['schemas']['PaginaDeAjustesResponse']
export type AjusteDetalle = components['schemas']['DetalleDeAjusteResponse']
export type LineaDeAjuste = components['schemas']['LineaDelDetalleDeAjusteResponse']
export type Jornada = components['schemas']['JornadaResponse']
export type JornadaDelListado = components['schemas']['JornadaDelListadoResponse']
export type PaginaJornadas = components['schemas']['PaginaDeJornadasResponse']
export type JornadaDetalle = components['schemas']['DetalleDeJornadaResponse']
export type TomaDeUbicacion = components['schemas']['TomaDeUbicacionResponse']

/** Tamaño de página por defecto (ADR-034 punto 6). */
export const LIMITE_POR_DEFECTO = 50

async function leerJsonOLanzar<T>(respuesta: Response): Promise<T> {
  if (!respuesta.ok) {
    throw await errorDesdeRespuesta(respuesta)
  }
  return (await respuesta.json()) as T
}

function conOperationId(operationId: string): HeadersInit {
  return { 'Content-Type': 'application/json', 'Operation-Id': operationId }
}

// --- ubicaciones ------------------------------------------------------------

export async function listarUbicaciones(
  activo?: boolean,
  cursor?: string,
  limite: number = LIMITE_POR_DEFECTO,
): Promise<PaginaUbicaciones> {
  const params = new URLSearchParams()
  params.set('limite', String(limite))
  if (cursor) params.set('cursor', cursor)
  if (activo !== undefined) params.set('activo', String(activo))
  const respuesta = await apiFetch(`/stock/ubicaciones?${params.toString()}`)
  return leerJsonOLanzar(respuesta)
}

export async function crearUbicacion(datos: UbicacionCrearDatos, operationId: string): Promise<Ubicacion> {
  const respuesta = await apiFetch('/stock/ubicaciones', {
    method: 'POST',
    headers: conOperationId(operationId),
    body: JSON.stringify(datos),
  })
  return leerJsonOLanzar(respuesta)
}

export async function modificarUbicacion(
  ubicacionId: string,
  datos: UbicacionModificarDatos,
  operationId: string,
): Promise<Ubicacion> {
  const respuesta = await apiFetch(`/stock/ubicaciones/${ubicacionId}`, {
    method: 'PUT',
    headers: conOperationId(operationId),
    body: JSON.stringify(datos),
  })
  return leerJsonOLanzar(respuesta)
}

// --- stock inicial ----------------------------------------------------------

export async function registrarStockInicial(
  datos: StockInicialDatos,
  operationId: string,
): Promise<StockInicialResultado> {
  const respuesta = await apiFetch('/stock/iniciales', {
    method: 'POST',
    headers: conOperationId(operationId),
    body: JSON.stringify(datos),
  })
  return leerJsonOLanzar(respuesta)
}

// --- lecturas ---------------------------------------------------------------

export async function obtenerSaldos(
  ubicacionId: string,
  cursor?: string,
  limite: number = LIMITE_POR_DEFECTO,
): Promise<StockDeUbicacion> {
  const params = new URLSearchParams()
  params.set('limite', String(limite))
  if (cursor) params.set('cursor', cursor)
  const respuesta = await apiFetch(`/stock/ubicaciones/${ubicacionId}/saldos?${params.toString()}`)
  return leerJsonOLanzar(respuesta)
}

export async function obtenerKardex(
  productoId: string,
  ubicacionId: string,
  filtros: FiltrosKardex = {},
  cursor?: string,
  limite: number = LIMITE_POR_DEFECTO,
): Promise<Kardex> {
  const params = new URLSearchParams()
  params.set('producto_id', productoId)
  params.set('ubicacion_id', ubicacionId)
  params.set('limite', String(limite))
  if (cursor) params.set('cursor', cursor)
  if (filtros.desde) params.set('desde', filtros.desde)
  if (filtros.hasta) params.set('hasta', filtros.hasta)
  const respuesta = await apiFetch(`/stock/kardex?${params.toString()}`)
  return leerJsonOLanzar(respuesta)
}

export async function obtenerCostoPromedio(productoId: string): Promise<CostoPromedio> {
  const respuesta = await apiFetch(`/catalogo/productos/${productoId}/costo`)
  return leerJsonOLanzar(respuesta)
}

// --- transferencias y ajustes (change 14) -----------------------------------

function parametrosDeListado(
  filtros: FiltrosTransferencias & { motivoId?: string },
  cursor: string | undefined,
  limite: number,
): URLSearchParams {
  const params = new URLSearchParams()
  params.set('limite', String(limite))
  if (cursor) params.set('cursor', cursor)
  if (filtros.ubicacionId) params.set('ubicacion_id', filtros.ubicacionId)
  if (filtros.motivoId) params.set('motivo_id', filtros.motivoId)
  if (filtros.desde) params.set('desde', filtros.desde)
  if (filtros.hasta) params.set('hasta', filtros.hasta)
  return params
}

export async function listarTransferencias(
  filtros: FiltrosTransferencias = {},
  cursor?: string,
  limite: number = LIMITE_POR_DEFECTO,
): Promise<PaginaTransferencias> {
  const respuesta = await apiFetch(`/stock/transferencias?${parametrosDeListado(filtros, cursor, limite).toString()}`)
  return leerJsonOLanzar(respuesta)
}

export async function obtenerTransferencia(id: string): Promise<TransferenciaDetalle> {
  const respuesta = await apiFetch(`/stock/transferencias/${id}`)
  return leerJsonOLanzar(respuesta)
}

export async function registrarTransferencia(
  datos: TransferenciaDatos,
  operationId: string,
): Promise<TransferenciaResultado> {
  const respuesta = await apiFetch('/stock/transferencias', {
    method: 'POST',
    headers: conOperationId(operationId),
    body: JSON.stringify(datos),
  })
  return leerJsonOLanzar(respuesta)
}

export async function anularTransferencia(
  id: string,
  motivoId: string,
  operationId: string,
): Promise<TransferenciaAnuladaResultado> {
  const respuesta = await apiFetch(`/stock/transferencias/${id}/anulacion`, {
    method: 'POST',
    headers: conOperationId(operationId),
    body: JSON.stringify({ motivo_id: motivoId }),
  })
  return leerJsonOLanzar(respuesta)
}

export async function listarAjustes(
  filtros: FiltrosAjustes = {},
  cursor?: string,
  limite: number = LIMITE_POR_DEFECTO,
): Promise<PaginaAjustes> {
  const respuesta = await apiFetch(`/stock/ajustes?${parametrosDeListado(filtros, cursor, limite).toString()}`)
  return leerJsonOLanzar(respuesta)
}

export async function obtenerAjuste(id: string): Promise<AjusteDetalle> {
  const respuesta = await apiFetch(`/stock/ajustes/${id}`)
  return leerJsonOLanzar(respuesta)
}

export async function registrarAjuste(datos: AjusteDatos, operationId: string): Promise<AjusteResultado> {
  const respuesta = await apiFetch('/stock/ajustes', {
    method: 'POST',
    headers: conOperationId(operationId),
    body: JSON.stringify(datos),
  })
  return leerJsonOLanzar(respuesta)
}

export async function anularAjuste(id: string, motivoId: string, operationId: string): Promise<AjusteAnuladoResultado> {
  const respuesta = await apiFetch(`/stock/ajustes/${id}/anulacion`, {
    method: 'POST',
    headers: conOperationId(operationId),
    body: JSON.stringify({ motivo_id: motivoId }),
  })
  return leerJsonOLanzar(respuesta)
}

// --- jornadas (change 15) ----------------------------------------------------

export async function listarJornadas(
  filtros: FiltrosJornadas = {},
  cursor?: string,
  limite: number = LIMITE_POR_DEFECTO,
): Promise<PaginaJornadas> {
  const params = new URLSearchParams()
  params.set('limite', String(limite))
  if (cursor) params.set('cursor', cursor)
  if (filtros.ubicacionId) params.set('ubicacion_id', filtros.ubicacionId)
  if (filtros.usuarioId) params.set('usuario_id', filtros.usuarioId)
  if (filtros.estado) params.set('estado', filtros.estado)
  if (filtros.desde) params.set('desde', filtros.desde)
  if (filtros.hasta) params.set('hasta', filtros.hasta)
  const respuesta = await apiFetch(`/stock/jornadas?${params.toString()}`)
  return leerJsonOLanzar(respuesta)
}

export async function obtenerJornada(id: string): Promise<JornadaDetalle> {
  const respuesta = await apiFetch(`/stock/jornadas/${id}`)
  return leerJsonOLanzar(respuesta)
}

/** La jornada no cerrada del usuario y el dispositivo del token; el 404 es "no tiene" (`null`). */
export async function obtenerJornadaActual(): Promise<JornadaDetalle | null> {
  const respuesta = await apiFetch('/stock/jornadas/actual')
  if (respuesta.status === 404) return null
  return leerJsonOLanzar(respuesta)
}

export async function abrirJornada(ubicacionId: string, operationId: string): Promise<Jornada> {
  const respuesta = await apiFetch('/stock/jornadas', {
    method: 'POST',
    headers: conOperationId(operationId),
    body: JSON.stringify({ ubicacion_id: ubicacionId }),
  })
  return leerJsonOLanzar(respuesta)
}

export async function rendirJornada(id: string, operationId: string): Promise<Jornada> {
  const respuesta = await apiFetch(`/stock/jornadas/${id}/rendicion`, {
    method: 'POST',
    headers: conOperationId(operationId),
    body: JSON.stringify({}),
  })
  return leerJsonOLanzar(respuesta)
}

export async function cerrarJornada(id: string, operationId: string): Promise<Jornada> {
  const respuesta = await apiFetch(`/stock/jornadas/${id}/cierre`, {
    method: 'POST',
    headers: conOperationId(operationId),
    body: JSON.stringify({}),
  })
  return leerJsonOLanzar(respuesta)
}

export async function liberarJornada(
  id: string,
  motivoId: string,
  observacion: string | undefined,
  operationId: string,
): Promise<Jornada> {
  const respuesta = await apiFetch(`/stock/jornadas/${id}/liberacion`, {
    method: 'POST',
    headers: conOperationId(operationId),
    body: JSON.stringify({ motivo_id: motivoId, ...(observacion ? { observacion } : {}) }),
  })
  return leerJsonOLanzar(respuesta)
}
