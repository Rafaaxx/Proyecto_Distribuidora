import type { components } from '../../api/schema.gen'
import { apiFetch } from '../../lib/api/httpClient'
import type {
  FiltrosDePeriodo,
  FiltrosDeRendiciones,
  FiltrosDeSaldosDeClientes,
  FiltrosDeSaldosDeProveedores,
  FiltrosDeVentas,
} from './claves'
import { errorDesdeRespuesta } from './errores'

/**
 * Funciones de acceso a `/api/v1/reportes/*` (change 26, D1, D3, D7 a D10). Tipadas contra `schema.gen.ts`, nunca
 * `any`. Solo lectura: ningún reporte escribe (REP-01).
 */

export type ReporteDeVentas = components['schemas']['ReporteDeVentasResponse']
export type CifrasDeVentas = components['schemas']['CifrasDeVentasResponse']
export type VentasPorDia = components['schemas']['VentasPorDiaResponse']
export type VentasPorVendedor = components['schemas']['VentasPorVendedorResponse']
export type VentasPorProducto = components['schemas']['VentasPorProductoResponse']
export type PresentacionVendida = components['schemas']['PresentacionVendidaResponse']
export type VentaAnulada = components['schemas']['VentaAnuladaResponse']

export type ReporteDeRendiciones = components['schemas']['ReporteDeRendicionesResponse']
export type JornadaDeRendicion = components['schemas']['JornadaDeRendicionResponse']
export type VendedorDeRendicion = components['schemas']['VendedorDeRendicionResponse']
export type ResumenDeJornadaDeReporte = components['schemas']['ResumenDeJornadaDeReporteResponse']
export type ReporteDeObservaciones = components['schemas']['ReporteDeObservacionesResponse']
export type ObservacionesDeVendedor = components['schemas']['ObservacionesDeVendedorResponse']
export type ReporteDeAjustes = components['schemas']['ReporteDeAjustesResponse']
export type MotivoDeAjuste = components['schemas']['MotivoDeAjusteResponse']
export type ProductoAjustado = components['schemas']['ProductoAjustadoResponse']
export type ReporteDeSaldosDeClientes = components['schemas']['ReporteDeSaldosDeClientesResponse']
export type ClienteConSaldo = components['schemas']['ClienteConSaldoResponse']
export type ReporteDeSaldosDeProveedores = components['schemas']['ReporteDeSaldosDeProveedoresResponse']
export type ProveedorConSaldo = components['schemas']['ProveedorConSaldoResponse']

async function leerJsonOLanzar<T>(respuesta: Response): Promise<T> {
  if (!respuesta.ok) {
    throw await errorDesdeRespuesta(respuesta)
  }
  return (await respuesta.json()) as T
}

/** La página solo viaja desde la segunda: sin ella el servidor trae la primera (D14). */
function paginaComoParametro(pagina: number | undefined): string | undefined {
  return pagina !== undefined && pagina > 1 ? String(pagina) : undefined
}

/** Solo viajan los filtros elegidos: sin fechas, el servidor usa el mes en curso (D1). */
function consulta(campos: Readonly<Record<string, string | undefined>>): string {
  const params = new URLSearchParams()
  for (const [nombre, valor] of Object.entries(campos)) {
    if (valor) params.set(nombre, valor)
  }
  const texto = params.toString()
  return texto === '' ? '' : `?${texto}`
}

export async function obtenerReporteDeVentas(filtros: FiltrosDeVentas = {}): Promise<ReporteDeVentas> {
  const params = consulta({
    desde: filtros.desde,
    hasta: filtros.hasta,
    vendedor_id: filtros.vendedorId,
    pagina_por_dia: paginaComoParametro(filtros.paginaPorDia),
    pagina_por_producto: paginaComoParametro(filtros.paginaPorProducto),
    pagina_anuladas: paginaComoParametro(filtros.paginaAnuladas),
  })
  const respuesta = await apiFetch(`/reportes/ventas${params}`)
  return leerJsonOLanzar(respuesta)
}

export async function obtenerReporteDeRendiciones(filtros: FiltrosDeRendiciones = {}): Promise<ReporteDeRendiciones> {
  const params = consulta({
    desde: filtros.desde,
    hasta: filtros.hasta,
    vendedor_id: filtros.vendedorId,
    estado: filtros.estado,
    pagina: paginaComoParametro(filtros.pagina),
  })
  return leerJsonOLanzar(await apiFetch(`/reportes/rendiciones${params}`))
}

/** El resumen de RUT-07 de una jornada con `VER_REPORTES`; un 404 no distingue una ajena (INV-21). */
export async function obtenerDetalleDeRendicion(jornadaId: string): Promise<ResumenDeJornadaDeReporte> {
  return leerJsonOLanzar(await apiFetch(`/reportes/rendiciones/${jornadaId}`))
}

export async function obtenerReporteDeObservaciones(filtros: FiltrosDePeriodo = {}): Promise<ReporteDeObservaciones> {
  const params = consulta({ desde: filtros.desde, hasta: filtros.hasta })
  return leerJsonOLanzar(await apiFetch(`/reportes/observaciones${params}`))
}

export async function obtenerReporteDeAjustes(filtros: FiltrosDePeriodo = {}): Promise<ReporteDeAjustes> {
  const params = consulta({ desde: filtros.desde, hasta: filtros.hasta })
  return leerJsonOLanzar(await apiFetch(`/reportes/ajustes${params}`))
}

export async function obtenerReporteDeSaldosDeClientes(
  filtros: FiltrosDeSaldosDeClientes = {},
): Promise<ReporteDeSaldosDeClientes> {
  const params = consulta({
    saldo: filtros.saldo,
    vendedor_id: filtros.vendedorId,
    estado: filtros.estado,
    texto: filtros.texto,
    pagina: paginaComoParametro(filtros.pagina),
  })
  return leerJsonOLanzar(await apiFetch(`/reportes/saldos/clientes${params}`))
}

export async function obtenerReporteDeSaldosDeProveedores(
  filtros: FiltrosDeSaldosDeProveedores = {},
): Promise<ReporteDeSaldosDeProveedores> {
  const params = consulta({
    saldo: filtros.saldo,
    estado: filtros.estado,
    texto: filtros.texto,
    pagina: paginaComoParametro(filtros.pagina),
  })
  return leerJsonOLanzar(await apiFetch(`/reportes/saldos/proveedores${params}`))
}
