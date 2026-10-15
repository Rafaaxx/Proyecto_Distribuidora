import type { components } from '../../api/schema.gen'
import { apiFetch } from '../../lib/api/httpClient'
import { errorDesdeRespuesta } from './errores'

/**
 * Acceso a `/api/v1/descuentos/reglas` y a los topes por rol (`/api/v1/identidad/roles`),
 * change 16, tarea 14.2. Tipado contra `schema.gen.ts`, nunca `any`. El `Operation-Id` de cada
 * escritura lo genera y conserva quien llama (hooks, INV-06). Porcentajes, umbrales e importes
 * viajan como string (INV-03).
 */

export type ReglaDescuento = components['schemas']['ReglaDescuentoResponse']
export type ReglasDescuentoPagina = components['schemas']['ReglasDescuentoResponse']
export type ReglaDescuentoCrearDatos = components['schemas']['ReglaDescuentoCrearRequest']
export type ReglaDescuentoModificarDatos = components['schemas']['ReglaDescuentoModificarRequest']
export type RolConTope = components['schemas']['RolConTopeResponse']
export type RolConTopeYPermisos = components['schemas']['RolConTopeYPermisosResponse']
export type TopeDeRolDatos = components['schemas']['TopeDescuentoRolRequest']

const LIMITE_POR_PAGINA = 50

async function leerJsonOLanzar<T>(respuesta: Response): Promise<T> {
  if (!respuesta.ok) {
    throw await errorDesdeRespuesta(respuesta)
  }
  return (await respuesta.json()) as T
}

function escritura(metodo: 'POST' | 'PUT', operationId: string, cuerpo?: unknown): RequestInit {
  return {
    method: metodo,
    headers: { 'Content-Type': 'application/json', 'Operation-Id': operationId },
    ...(cuerpo === undefined ? {} : { body: JSON.stringify(cuerpo) }),
  }
}

// --- lecturas ----------------------------------------------------------------------------

export async function listarReglasDescuento(
  estado: string | undefined,
  cursor?: string,
  limite = LIMITE_POR_PAGINA,
): Promise<ReglasDescuentoPagina> {
  const params = new URLSearchParams()
  params.set('limite', String(limite))
  if (estado) params.set('estado', estado)
  if (cursor) params.set('cursor', cursor)
  return leerJsonOLanzar(await apiFetch(`/descuentos/reglas?${params.toString()}`))
}

export async function obtenerReglaDescuento(reglaId: string): Promise<ReglaDescuento> {
  return leerJsonOLanzar(await apiFetch(`/descuentos/reglas/${reglaId}`))
}

export async function listarRolesConTope(): Promise<RolConTopeYPermisos[]> {
  return leerJsonOLanzar(await apiFetch('/identidad/roles'))
}

// --- escrituras --------------------------------------------------------------------------

export async function crearReglaDescuento(
  datos: ReglaDescuentoCrearDatos,
  operationId: string,
): Promise<ReglaDescuento> {
  return leerJsonOLanzar(await apiFetch('/descuentos/reglas', escritura('POST', operationId, datos)))
}

export async function modificarReglaDescuento(
  reglaId: string,
  datos: ReglaDescuentoModificarDatos,
  operationId: string,
): Promise<ReglaDescuento> {
  return leerJsonOLanzar(await apiFetch(`/descuentos/reglas/${reglaId}`, escritura('PUT', operationId, datos)))
}

export async function activarReglaDescuento(reglaId: string, operationId: string): Promise<ReglaDescuento> {
  return leerJsonOLanzar(await apiFetch(`/descuentos/reglas/${reglaId}/activacion`, escritura('POST', operationId)))
}

export async function pausarReglaDescuento(reglaId: string, operationId: string): Promise<ReglaDescuento> {
  return leerJsonOLanzar(await apiFetch(`/descuentos/reglas/${reglaId}/pausa`, escritura('POST', operationId)))
}

export async function definirTopeDeRol(
  rolId: string,
  datos: TopeDeRolDatos,
  operationId: string,
): Promise<RolConTope> {
  return leerJsonOLanzar(
    await apiFetch(`/identidad/roles/${rolId}/tope-descuento`, escritura('PUT', operationId, datos)),
  )
}
