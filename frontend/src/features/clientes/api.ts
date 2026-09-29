import { apiFetch } from '../../lib/api/httpClient'
import type { components } from '../../api/schema.gen'
import { errorDesdeRespuesta } from './errores'
import type { FiltrosClientes } from './claves'

/**
 * Funciones de acceso a `/api/v1/clientes/*` (change 07, grupo 5, tareas
 * 5.1 y 5.3/5.4/5.5). Tipadas contra `schema.gen.ts` -- nunca `any`.
 *
 * `design.md` D9 (enmienda 2026-09-29): las cuatro escrituras
 * (`CLIENTE_CREAR`, `CLIENTE_MODIFICAR`, `CLIENTE_CREDITO_MODIFICAR`,
 * `CLIENTE_CONSUMIDOR_FINAL_CONFIGURAR`) tienen ahora una ruta HTTP
 * dedicada cada una, mismo criterio que `features/proveedores/api.ts`: el
 * `Operation-Id` de cada escritura lo genera y conserva quien llama (los
 * hooks de mutación, `useMutaciones.ts`) para que el reintento automático
 * de TanStack Query reenvíe exactamente el mismo valor (INV-06); estas
 * funciones solo lo pasan como encabezado explícito.
 */

export type Cliente = components['schemas']['ClienteResponse']
export type PaginaClientes = components['schemas']['PaginaClientes']
export type ConsumidorFinal = components['schemas']['ConsumidorFinalResponse']
export type ClienteCrearDatos = components['schemas']['ClienteCrearRequest']
export type ClienteModificarDatos = components['schemas']['ClienteModificarRequest']
export type ClienteCreditoModificarDatos = components['schemas']['ClienteCreditoModificarRequest']
export type ConsumidorFinalConfigurarDatos = components['schemas']['ConsumidorFinalConfigurarRequest']

async function leerJsonOLanzar<T>(respuesta: Response): Promise<T> {
  if (!respuesta.ok) {
    throw await errorDesdeRespuesta(respuesta)
  }
  return (await respuesta.json()) as T
}

function paramsClientes(cursor: string | undefined, limite: number, filtros: FiltrosClientes): string {
  const params = new URLSearchParams()
  params.set('limite', String(limite))
  if (cursor) params.set('cursor', cursor)
  if (filtros.texto) params.set('texto', filtros.texto)
  if (filtros.estado) params.set('estado', filtros.estado)
  return params.toString()
}

export async function listarClientes(
  filtros: FiltrosClientes = {},
  cursor?: string,
  limite = 30,
): Promise<PaginaClientes> {
  const respuesta = await apiFetch(`/clientes?${paramsClientes(cursor, limite, filtros)}`)
  return leerJsonOLanzar(respuesta)
}

export async function obtenerCliente(clienteId: string): Promise<Cliente> {
  const respuesta = await apiFetch(`/clientes/${clienteId}`)
  return leerJsonOLanzar(respuesta)
}

export async function obtenerConsumidorFinal(): Promise<ConsumidorFinal> {
  const respuesta = await apiFetch('/clientes/consumidor-final')
  return leerJsonOLanzar(respuesta)
}

// --- escrituras (D9, enmienda 2026-09-29) -----------------------------------

export async function crearCliente(datos: ClienteCrearDatos, operationId: string): Promise<Cliente> {
  const respuesta = await apiFetch('/clientes', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Operation-Id': operationId },
    body: JSON.stringify(datos),
  })
  return leerJsonOLanzar(respuesta)
}

export async function modificarCliente(
  clienteId: string,
  datos: ClienteModificarDatos,
  operationId: string,
): Promise<Cliente> {
  const respuesta = await apiFetch(`/clientes/${clienteId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json', 'Operation-Id': operationId },
    body: JSON.stringify(datos),
  })
  return leerJsonOLanzar(respuesta)
}

export async function modificarCreditoCliente(
  clienteId: string,
  datos: ClienteCreditoModificarDatos,
  operationId: string,
): Promise<Cliente> {
  const respuesta = await apiFetch(`/clientes/${clienteId}/credito`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json', 'Operation-Id': operationId },
    body: JSON.stringify(datos),
  })
  return leerJsonOLanzar(respuesta)
}

export async function configurarConsumidorFinal(
  datos: ConsumidorFinalConfigurarDatos,
  operationId: string,
): Promise<Cliente> {
  const respuesta = await apiFetch('/clientes/consumidor-final', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Operation-Id': operationId },
    body: JSON.stringify(datos),
  })
  return leerJsonOLanzar(respuesta)
}
