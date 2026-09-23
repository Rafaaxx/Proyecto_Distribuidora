import { apiFetch } from '../../lib/api/httpClient'
import type { components } from '../../api/schema.gen'
import { errorDesdeRespuesta } from './errores'
import type { FiltrosProductos } from './claves'

/**
 * Funciones de acceso a `/api/v1/catalogo/*` (tarea 10.2). Tipadas contra
 * `schema.gen.ts` (generado del OpenAPI real, tarea 9.4) -- nunca `any`.
 * El `Operation-Id` de cada escritura lo genera y conserva quien llama
 * (los hooks de mutación, tarea 10.2) para que el reintento automático de
 * TanStack Query reenvíe exactamente el mismo valor (INV-06): estas
 * funciones solo lo pasan como encabezado explícito.
 */

export type Categoria = components['schemas']['CategoriaResponse']
export type Marca = components['schemas']['MarcaResponse']
export type Producto = components['schemas']['ProductoResponse']
export type ProductoDetalle = components['schemas']['ProductoDetalleResponse']
export type Presentacion = components['schemas']['PresentacionResponse']
export type PaginaCategorias = components['schemas']['PaginaCategorias']
export type PaginaMarcas = components['schemas']['PaginaMarcas']
export type PaginaProductos = components['schemas']['PaginaProductos']
export type CategoriaCrearDatos = components['schemas']['CategoriaCrearRequest']
export type CategoriaModificarDatos = components['schemas']['CategoriaModificarRequest']
export type MarcaCrearDatos = components['schemas']['MarcaCrearRequest']
export type MarcaModificarDatos = components['schemas']['MarcaModificarRequest']
export type ProductoCrearDatos = components['schemas']['ProductoCrearRequest']
export type ProductoModificarDatos = components['schemas']['ProductoModificarRequest']
export type PresentacionAgregarDatos = components['schemas']['PresentacionAgregarRequest']
export type PresentacionModificarDatos = components['schemas']['PresentacionModificarRequest']

async function leerJsonOLanzar<T>(respuesta: Response): Promise<T> {
  if (!respuesta.ok) {
    throw await errorDesdeRespuesta(respuesta)
  }
  return (await respuesta.json()) as T
}

function paramsPagina(cursor: string | undefined, limite: number): string {
  const params = new URLSearchParams()
  params.set('limite', String(limite))
  if (cursor) {
    params.set('cursor', cursor)
  }
  return params.toString()
}

// --- Categorías ---

export async function listarCategorias(cursor?: string, limite = 30): Promise<PaginaCategorias> {
  const respuesta = await apiFetch(`/catalogo/categorias?${paramsPagina(cursor, limite)}`)
  return leerJsonOLanzar(respuesta)
}

export async function crearCategoria(datos: CategoriaCrearDatos, operationId: string): Promise<Categoria> {
  const respuesta = await apiFetch('/catalogo/categorias', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Operation-Id': operationId },
    body: JSON.stringify(datos),
  })
  return leerJsonOLanzar(respuesta)
}

export async function modificarCategoria(
  categoriaId: string,
  datos: CategoriaModificarDatos,
  operationId: string,
): Promise<Categoria> {
  const respuesta = await apiFetch(`/catalogo/categorias/${categoriaId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json', 'Operation-Id': operationId },
    body: JSON.stringify(datos),
  })
  return leerJsonOLanzar(respuesta)
}

// --- Marcas ---

export async function listarMarcas(cursor?: string, limite = 30): Promise<PaginaMarcas> {
  const respuesta = await apiFetch(`/catalogo/marcas?${paramsPagina(cursor, limite)}`)
  return leerJsonOLanzar(respuesta)
}

export async function crearMarca(datos: MarcaCrearDatos, operationId: string): Promise<Marca> {
  const respuesta = await apiFetch('/catalogo/marcas', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Operation-Id': operationId },
    body: JSON.stringify(datos),
  })
  return leerJsonOLanzar(respuesta)
}

export async function modificarMarca(
  marcaId: string,
  datos: MarcaModificarDatos,
  operationId: string,
): Promise<Marca> {
  const respuesta = await apiFetch(`/catalogo/marcas/${marcaId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json', 'Operation-Id': operationId },
    body: JSON.stringify(datos),
  })
  return leerJsonOLanzar(respuesta)
}

// --- Productos ---

function paramsProductos(cursor: string | undefined, limite: number, filtros: FiltrosProductos): string {
  const params = new URLSearchParams()
  params.set('limite', String(limite))
  if (cursor) params.set('cursor', cursor)
  if (filtros.texto) params.set('texto', filtros.texto)
  if (filtros.categoriaId) params.set('categoria_id', filtros.categoriaId)
  if (filtros.marcaId) params.set('marca_id', filtros.marcaId)
  if (filtros.activo !== undefined) params.set('activo', String(filtros.activo))
  return params.toString()
}

export async function listarProductos(
  filtros: FiltrosProductos,
  cursor?: string,
  limite = 30,
): Promise<PaginaProductos> {
  const respuesta = await apiFetch(`/catalogo/productos?${paramsProductos(cursor, limite, filtros)}`)
  return leerJsonOLanzar(respuesta)
}

export async function obtenerProducto(productoId: string): Promise<ProductoDetalle> {
  const respuesta = await apiFetch(`/catalogo/productos/${productoId}`)
  return leerJsonOLanzar(respuesta)
}

export async function crearProducto(datos: ProductoCrearDatos, operationId: string): Promise<ProductoDetalle> {
  const respuesta = await apiFetch('/catalogo/productos', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Operation-Id': operationId },
    body: JSON.stringify(datos),
  })
  return leerJsonOLanzar(respuesta)
}

export async function modificarProducto(
  productoId: string,
  datos: ProductoModificarDatos,
  operationId: string,
): Promise<Producto> {
  const respuesta = await apiFetch(`/catalogo/productos/${productoId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json', 'Operation-Id': operationId },
    body: JSON.stringify(datos),
  })
  return leerJsonOLanzar(respuesta)
}

// --- Presentaciones ---

export async function agregarPresentacion(
  productoId: string,
  datos: PresentacionAgregarDatos,
  operationId: string,
): Promise<Presentacion> {
  const respuesta = await apiFetch(`/catalogo/productos/${productoId}/presentaciones`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Operation-Id': operationId },
    body: JSON.stringify(datos),
  })
  return leerJsonOLanzar(respuesta)
}

export async function modificarPresentacion(
  presentacionId: string,
  datos: PresentacionModificarDatos,
  operationId: string,
): Promise<Presentacion> {
  const respuesta = await apiFetch(`/catalogo/presentaciones/${presentacionId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json', 'Operation-Id': operationId },
    body: JSON.stringify(datos),
  })
  return leerJsonOLanzar(respuesta)
}

export async function cambiarReferencia(
  productoId: string,
  presentacionId: string,
  operationId: string,
): Promise<Presentacion> {
  const respuesta = await apiFetch(`/catalogo/productos/${productoId}/referencia`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json', 'Operation-Id': operationId },
    body: JSON.stringify({ presentacion_id: presentacionId }),
  })
  return leerJsonOLanzar(respuesta)
}
