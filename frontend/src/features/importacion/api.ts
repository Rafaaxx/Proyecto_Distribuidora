import type { components } from '../../api/schema.gen'
import { apiFetch } from '../../lib/api/httpClient'
import { errorDesdeRespuesta } from './errores'

/**
 * Acceso a la API de importación (change 10, grupo 8, tarea 8.1). Tipado contra
 * `schema.gen.ts` -- nunca `any`.
 *
 * Escritura (`ONLINE`, sin cola): `POST /importaciones/{tipo}` con el archivo en multipart
 * (campo `archivo`). El cliente NO lee ni valida el contenido: lo envía tal cual y el
 * servidor valida todo (TR-10). El `Operation-Id` lo genera y conserva quien llama para que
 * el reintento reenvíe el mismo valor (INV-06). Lecturas: el historial paginado por cursor y
 * la plantilla CSV de cada tipo.
 */

export type ImportacionResultado = components['schemas']['ImportacionResponse']
export type ImportacionDelHistorial = components['schemas']['ImportacionItem']
export type PaginaDeImportaciones = components['schemas']['PaginaImportaciones']

/** Tamaño de página por defecto del historial. */
export const LIMITE_POR_DEFECTO = 50

async function leerJsonOLanzar<T>(respuesta: Response): Promise<T> {
  if (!respuesta.ok) {
    throw await errorDesdeRespuesta(respuesta)
  }
  return (await respuesta.json()) as T
}

export async function importarArchivo(tipo: string, archivo: File, operationId: string): Promise<ImportacionResultado> {
  const cuerpo = new FormData()
  cuerpo.append('archivo', archivo, archivo.name)
  // Sin `Content-Type`: el navegador lo fija como multipart con su `boundary`.
  const respuesta = await apiFetch(`/importaciones/${tipo}`, {
    method: 'POST',
    headers: { 'Operation-Id': operationId },
    body: cuerpo,
  })
  return leerJsonOLanzar(respuesta)
}

export async function listarImportaciones(cursor?: string, limite: number = LIMITE_POR_DEFECTO): Promise<PaginaDeImportaciones> {
  const params = new URLSearchParams()
  params.set('limite', String(limite))
  if (cursor) params.set('cursor', cursor)
  const respuesta = await apiFetch(`/importaciones?${params.toString()}`)
  return leerJsonOLanzar(respuesta)
}

export async function descargarPlantilla(tipo: string): Promise<Blob> {
  const respuesta = await apiFetch(`/importaciones/plantillas/${tipo}`)
  if (!respuesta.ok) {
    throw await errorDesdeRespuesta(respuesta)
  }
  return respuesta.blob()
}
