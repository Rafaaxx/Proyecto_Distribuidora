import type { components } from '../../api/schema.gen'
import type { CredencialDePin } from '../../domain/ventas/autorizacionDeVenta'
import type { VentaConfirmarDatos } from '../../domain/ventas/formularioVenta'
import { apiFetch } from '../../lib/api/httpClient'
import type { ContextoDePrecios, FiltrosVentas } from './claves'
import { errorDesdeRespuesta } from './errores'

/**
 * Funciones de acceso a `/api/v1/ventas/*` (change 18a, tarea 12.2). Tipadas contra
 * `schema.gen.ts`, nunca `any`. El `Operation-Id` de la escritura lo genera y conserva quien
 * llama (hooks, INV-06). Los selectores de apoyo (clientes, saldo, listas, ubicaciones, medios y
 * motivos) se reutilizan de `features/cobranzas`, `features/precios`, `features/stock` y
 * `features/compras`.
 */

export type VentaConfirmarResultado = components['schemas']['VentaConfirmarResponse']
export type VentaResumen = components['schemas']['VentaResumenResponse']
export type VentaDetalle = components['schemas']['VentaDetalleResponse']
export type VentaLinea = components['schemas']['VentaLineaResponse']
export type VentaObservacion = components['schemas']['VentaObservacionResponse']
export type PaginaVentas = components['schemas']['PaginaVentas']
export type PreciosParaVender = components['schemas']['PreciosParaVenderResponse']
export type ProductoParaVender = components['schemas']['ProductoParaVenderResponse']
export type Numeracion = components['schemas']['NumeracionResponse']
export type VersionElegible = components['schemas']['VersionElegibleResponse']
export type ContextoDeVentaDeApi = components['schemas']['ContextoDeVentaResponse']
export type ReglaAplicable = components['schemas']['ReglaAplicableResponse']
export type CreditoParaVender = components['schemas']['CreditoParaVenderResponse']

const LIMITE_DE_PRECIOS = 20

async function leerJsonOLanzar<T>(respuesta: Response): Promise<T> {
  if (!respuesta.ok) {
    throw await errorDesdeRespuesta(respuesta)
  }
  return (await respuesta.json()) as T
}

function paramsVentas(cursor: string | undefined, limite: number, filtros: FiltrosVentas): string {
  const params = new URLSearchParams()
  params.set('limite', String(limite))
  if (cursor) params.set('cursor', cursor)
  if (filtros.clienteId) params.set('cliente_id', filtros.clienteId)
  if (filtros.usuarioId) params.set('usuario_id', filtros.usuarioId)
  if (filtros.jornadaId) params.set('jornada_id', filtros.jornadaId)
  if (filtros.ubicacionId) params.set('ubicacion_id', filtros.ubicacionId)
  if (filtros.desde) params.set('desde', filtros.desde)
  if (filtros.hasta) params.set('hasta', filtros.hasta)
  return params.toString()
}

export async function listarVentas(filtros: FiltrosVentas = {}, cursor?: string, limite = 30): Promise<PaginaVentas> {
  const respuesta = await apiFetch(`/ventas?${paramsVentas(cursor, limite, filtros)}`)
  return leerJsonOLanzar(respuesta)
}

export async function obtenerVenta(ventaId: string): Promise<VentaDetalle> {
  const respuesta = await apiFetch(`/ventas/${ventaId}`)
  return leerJsonOLanzar(respuesta)
}

export interface ConsultaDePrecios extends ContextoDePrecios {
  /** Búsqueda por nombre o código, en el servidor (D19). */
  texto?: string
  productoId?: string
  cursor?: string
  limite?: number
}

/** Precios para vender, de a una página; sin costos jamás (D19). */
export async function buscarPreciosParaVender(consulta: ConsultaDePrecios): Promise<PreciosParaVender> {
  const params = new URLSearchParams()
  params.set('limite', String(consulta.limite ?? LIMITE_DE_PRECIOS))
  if (consulta.clienteId) params.set('cliente_id', consulta.clienteId)
  if (consulta.listaId) params.set('lista_id', consulta.listaId)
  if (consulta.versionId) params.set('version_id', consulta.versionId)
  if (consulta.ubicacionId) params.set('ubicacion_id', consulta.ubicacionId)
  if (consulta.texto && consulta.texto.trim() !== '') params.set('q', consulta.texto.trim())
  if (consulta.productoId) params.set('producto_id', consulta.productoId)
  if (consulta.cursor) params.set('cursor', consulta.cursor)
  const respuesta = await apiFetch(`/ventas/precios?${params.toString()}`)
  return leerJsonOLanzar(respuesta)
}

/** Prefijo y último correlativo del dispositivo de la sesión (D4). */
export async function obtenerNumeracion(): Promise<Numeracion> {
  const respuesta = await apiFetch('/ventas/numeracion')
  return leerJsonOLanzar(respuesta)
}

/** Versiones elegibles de una lista (`USAR_LISTA_ANTERIOR`, D6). */
export async function listarVersionesElegibles(listaId: string): Promise<VersionElegible[]> {
  const respuesta = await apiFetch(`/ventas/versiones?${new URLSearchParams({ lista_id: listaId }).toString()}`)
  return (await leerJsonOLanzar<{ items: VersionElegible[] }>(respuesta)).items
}

/** Tope, motivos y autorizadores de quien vende (`VENDER`, change 18b, D15). */
export async function obtenerContextoDeVenta(): Promise<ContextoDeVentaDeApi> {
  const respuesta = await apiFetch('/ventas/contexto')
  return leerJsonOLanzar(respuesta)
}

/** Reglas de descuento activas y vigentes ahora (`VENDER`, DSC-01, ADR-050). */
export async function listarDescuentosAplicables(): Promise<ReglaAplicable[]> {
  const respuesta = await apiFetch('/ventas/descuentos-aplicables')
  return (await leerJsonOLanzar<{ items: ReglaAplicable[] }>(respuesta)).items
}

/** Límite, saldo, disponible, política y tolerancia de un cliente para vender (`VENDER`, D16). */
export async function obtenerCreditoParaVender(clienteId: string): Promise<CreditoParaVender> {
  const respuesta = await apiFetch(`/ventas/credito?${new URLSearchParams({ cliente_id: clienteId }).toString()}`)
  return leerJsonOLanzar(respuesta)
}

/**
 * `POST /ventas`. Las `credenciales` (PIN de quien autoriza) viajan en el cuerpo pero NO forman
 * parte del contenido del comando ni de su huella (D2): el servidor las separa. Esta función no
 * guarda nada: el PIN existe solo mientras dura la llamada.
 */
export async function confirmarVenta(
  datos: VentaConfirmarDatos,
  operationId: string,
  credenciales: readonly CredencialDePin[] = [],
): Promise<VentaConfirmarResultado> {
  const cuerpo = credenciales.length === 0 ? datos : { ...datos, credenciales }
  const respuesta = await apiFetch('/ventas', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Operation-Id': operationId },
    body: JSON.stringify(cuerpo),
  })
  return leerJsonOLanzar(respuesta)
}
