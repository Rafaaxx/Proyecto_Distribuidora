import type { components } from '../../api/schema.gen'
import { apiFetch } from '../../lib/api/httpClient'
import { errorDesdeRespuesta } from './errores'

/**
 * Funciones de acceso a `/api/v1/precios/*` (change 13, tarea 12.2). Tipadas contra
 * `schema.gen.ts`, nunca `any`. El `Operation-Id` de cada escritura lo genera y conserva quien
 * llama (hooks, INV-06). Importes, múltiplos y márgenes viajan como string (INV-03).
 */

export type Lista = components['schemas']['ListaResponse']
export type ListaDetalle = components['schemas']['ListaDetalleResponse']
export type ListasResultado = components['schemas']['ListasResponse']
export type ListaOpciones = components['schemas']['ListaOpcionesResponse']
export type ListaCrearDatos = components['schemas']['ListaCrearRequest']
export type ListaModificarDatos = components['schemas']['ListaModificarRequest']
export type Regla = components['schemas']['ReglaResponse']
export type ReglasResultado = components['schemas']['ReglasResponse']
export type ReglaCrearDatos = components['schemas']['ReglaCrearRequest']
export type ReglaModificarDatos = components['schemas']['ReglaModificarRequest']
export type RedondeoCategoria = components['schemas']['RedondeoCategoriaResponse']
export type RedondeoCategoriaDatos = components['schemas']['RedondeoCategoriaDefinirRequest']
export type Borrador = components['schemas']['BorradorResponse']
export type Generacion = components['schemas']['GeneracionResponse']
export type PrecioDeVersion = components['schemas']['PrecioDeVersionResponse']
export type PreciosDeVersion = components['schemas']['PreciosDeVersionResponse']
export type PrecioFijado = components['schemas']['PrecioFijadoResponse']
export type ProductoSinPrecio = components['schemas']['ProductoSinPrecioResponse']
export type Version = components['schemas']['VersionResponse']
export type VersionesResultado = components['schemas']['VersionesResponse']
export type PublicarDatos = components['schemas']['PublicarRequest']
export type ListaPredeterminada = components['schemas']['ListaPredeterminadaResponse']
export type ListaPredeterminadaDatos = components['schemas']['ListaPredeterminadaDefinirRequest']

const LIMITE_POR_PAGINA = 100

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

function paramsDePagina(cursor: string | undefined, limite: number): string {
  const params = new URLSearchParams()
  params.set('limite', String(limite))
  if (cursor) params.set('cursor', cursor)
  return params.toString()
}

// --- lecturas ----------------------------------------------------------------------------

export async function listarListas(): Promise<ListasResultado> {
  return leerJsonOLanzar(await apiFetch('/precios/listas'))
}

export async function listarOpcionesDeListas(): Promise<ListaOpciones> {
  return leerJsonOLanzar(await apiFetch('/precios/listas/opciones'))
}

export async function obtenerLista(listaId: string): Promise<ListaDetalle> {
  return leerJsonOLanzar(await apiFetch(`/precios/listas/${listaId}`))
}

export async function listarReglas(listaId: string): Promise<ReglasResultado> {
  return leerJsonOLanzar(await apiFetch(`/precios/listas/${listaId}/reglas`))
}

export async function obtenerBorrador(
  listaId: string,
  cursor?: string,
  limite = LIMITE_POR_PAGINA,
): Promise<Borrador> {
  return leerJsonOLanzar(await apiFetch(`/precios/listas/${listaId}/borrador?${paramsDePagina(cursor, limite)}`))
}

export async function listarVersiones(listaId: string): Promise<VersionesResultado> {
  return leerJsonOLanzar(await apiFetch(`/precios/listas/${listaId}/versiones`))
}

export async function listarPreciosDeVersion(
  listaId: string,
  versionId: string,
  cursor?: string,
  limite = LIMITE_POR_PAGINA,
): Promise<PreciosDeVersion> {
  return leerJsonOLanzar(
    await apiFetch(`/precios/listas/${listaId}/versiones/${versionId}/precios?${paramsDePagina(cursor, limite)}`),
  )
}

export async function obtenerListaPredeterminada(): Promise<ListaPredeterminada> {
  return leerJsonOLanzar(await apiFetch('/precios/lista-predeterminada'))
}

// --- escrituras --------------------------------------------------------------------------

export async function crearLista(datos: ListaCrearDatos, operationId: string): Promise<Lista> {
  return leerJsonOLanzar(await apiFetch('/precios/listas', escritura('POST', operationId, datos)))
}

export async function modificarLista(
  listaId: string,
  datos: ListaModificarDatos,
  operationId: string,
): Promise<Lista> {
  return leerJsonOLanzar(await apiFetch(`/precios/listas/${listaId}`, escritura('PUT', operationId, datos)))
}

export async function crearRegla(listaId: string, datos: ReglaCrearDatos, operationId: string): Promise<Regla> {
  return leerJsonOLanzar(await apiFetch(`/precios/listas/${listaId}/reglas`, escritura('POST', operationId, datos)))
}

export async function modificarRegla(
  listaId: string,
  reglaId: string,
  datos: ReglaModificarDatos,
  operationId: string,
): Promise<Regla> {
  return leerJsonOLanzar(
    await apiFetch(`/precios/listas/${listaId}/reglas/${reglaId}`, escritura('PUT', operationId, datos)),
  )
}

export async function definirRedondeoDeCategoria(
  listaId: string,
  categoriaId: string,
  datos: RedondeoCategoriaDatos,
  operationId: string,
): Promise<RedondeoCategoria> {
  return leerJsonOLanzar(
    await apiFetch(
      `/precios/listas/${listaId}/redondeos-categoria/${categoriaId}`,
      escritura('PUT', operationId, datos),
    ),
  )
}

export async function generarBorrador(listaId: string, operationId: string): Promise<Generacion> {
  return leerJsonOLanzar(await apiFetch(`/precios/listas/${listaId}/borrador`, escritura('POST', operationId)))
}

/** `precio_final` nulo quita la marca manual y el precio vuelve a calcularse (D7). */
export async function fijarPrecioManual(
  listaId: string,
  versionId: string,
  productoId: string,
  precioFinal: string | null,
  operationId: string,
): Promise<PrecioFijado> {
  return leerJsonOLanzar(
    await apiFetch(
      `/precios/listas/${listaId}/versiones/${versionId}/precios/${productoId}`,
      escritura('PUT', operationId, { precio_final: precioFinal }),
    ),
  )
}

export async function publicarVersion(
  listaId: string,
  versionId: string,
  datos: PublicarDatos,
  operationId: string,
): Promise<Version> {
  return leerJsonOLanzar(
    await apiFetch(`/precios/listas/${listaId}/versiones/${versionId}/publicar`, escritura('POST', operationId, datos)),
  )
}

export async function anularVersion(listaId: string, versionId: string, operationId: string): Promise<Version> {
  return leerJsonOLanzar(
    await apiFetch(`/precios/listas/${listaId}/versiones/${versionId}/anular`, escritura('POST', operationId)),
  )
}

export async function definirListaPredeterminada(
  datos: ListaPredeterminadaDatos,
  operationId: string,
): Promise<ListaPredeterminada> {
  return leerJsonOLanzar(await apiFetch('/precios/lista-predeterminada', escritura('PUT', operationId, datos)))
}
