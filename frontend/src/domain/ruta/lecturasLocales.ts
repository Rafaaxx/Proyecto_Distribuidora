import { formatearImporte, parsearImporteDesdeApi } from '../../lib/money'
import type { ClienteLocal, PrecioLocal, VersionLocal } from '../../lib/dispositivo/db'
import { precioPorPresentacion } from '../precios/presentacion'

/**
 * Lecturas locales puras del área `/ruta` (change 21, `design.md` D6, D19; PRC-20, PRC-22,
 * `01` §19, INV-03, INV-04). Reciben filas de la base local y devuelven resultados: sin Dexie,
 * sin React y sin `number` para importes.
 */

/**
 * PRC-20: la versión vigente de una lista en `momento` es una publicada con
 * `desde <= momento` y `hasta` nulo o posterior (hasta exclusive, igual que el servidor). Si hay
 * varias, la de mayor número. Sin ninguna, `null` ("sin precio"). El bootstrap manda el estado
 * DERIVADO por el servidor (`VIGENTE`, `PROGRAMADA`, `HISTORICA`: todas publicadas) y ya excluye
 * anuladas y borradores; por defensa se descartan `BORRADOR` y `ANULADA`, sin exigir `PUBLICADA`.
 */
export function versionVigente(versiones: VersionLocal[], momento: Date): VersionLocal | null {
  const t = momento.getTime()
  let elegida: VersionLocal | null = null
  for (const v of versiones) {
    if (v.estado === 'BORRADOR' || v.estado === 'ANULADA') continue
    if (new Date(v.vigencia_desde).getTime() > t) continue
    if (v.vigencia_hasta !== null && new Date(v.vigencia_hasta).getTime() <= t) continue
    if (elegida === null || v.numero > elegida.numero) elegida = v
  }
  return elegida
}

/**
 * PRC-22: precio (string, 2 decimales) de una presentación de `unidadesBase` unidades. Solo
 * para mostrar. `null` si el producto no tiene precio en la versión.
 */
export function precioDePresentacion(
  precio: PrecioLocal | undefined,
  unidadesBase: number,
): string | null {
  if (precio === undefined) return null
  return precioPorPresentacion(precio.precio_referencia, precio.unidades_referencia, unidadesBase)
}

function normalizar(texto: string): string {
  return texto
    .normalize('NFD')
    .replace(/\p{Diacritic}/gu, '')
    .toLowerCase()
}

function soloAlfanumericos(texto: string): string {
  return normalizar(texto).replace(/[^a-z0-9]/g, '')
}

function coincide(cliente: ClienteLocal, busqueda: string): boolean {
  const q = normalizar(busqueda.trim())
  const qCompacta = soloAlfanumericos(busqueda)
  const campos = [cliente.nombre, cliente.razon_social, cliente.codigo]
  if (campos.some((c) => c !== null && normalizar(c).includes(q))) return true
  const documento = cliente.documento_numero
  return documento !== null && qCompacta !== '' && soloAlfanumericos(documento).includes(qCompacta)
}

function grupo(cliente: ClienteLocal): number {
  if (cliente.es_consumidor_final) return 0
  return cliente.en_cartera ? 1 : 2
}

/**
 * `01` §19 (CLI-02, INV-17): la búsqueda recorre TODOS los clientes bajados; el orden pone al
 * consumidor final y la cartera primero, y cada grupo va por nombre.
 */
export function filtrarYOrdenarClientes(clientes: ClienteLocal[], busqueda: string): ClienteLocal[] {
  const filtrados = busqueda.trim() === '' ? clientes : clientes.filter((c) => coincide(c, busqueda))
  return [...filtrados].sort(
    (a, b) => grupo(a) - grupo(b) || a.nombre.localeCompare(b.nombre, 'es', { sensitivity: 'base' }),
  )
}

/** Disponible = límite - saldo (CRE-01); `null` sin límite. Exacto con decimal.js (INV-03). */
export function disponibleDeCredito(limite: string | null, saldo: string): string | null {
  if (limite === null) return null
  return parsearImporteDesdeApi(limite).minus(parsearImporteDesdeApi(saldo)).toFixed(2)
}

/** INV-04: cantidad base en cajas completas y unidades sueltas (`unidadesPorCaja <= 1`: todo unidades). */
export function stockEnCajasYUnidades(
  cantidadBase: number,
  unidadesPorCaja: number,
): { cajas: number; unidades: number } {
  if (unidadesPorCaja <= 1) return { cajas: 0, unidades: cantidadBase }
  return { cajas: Math.floor(cantidadBase / unidadesPorCaja), unidades: cantidadBase % unidadesPorCaja }
}

/** Importe del bootstrap (string) para mostrar: `$ 125.000,00`. Nunca pasa por `number` (INV-03). */
export function formatearDinero(valor: string): string {
  return `$ ${formatearImporte(parsearImporteDesdeApi(valor))}`
}

/** INV-04, CAT-08: "3 cajas y 2 unidades"; sin nada, "Sin stock". */
export function describirStock(cajas: number, unidades: number): string {
  const partes: string[] = []
  if (cajas > 0) partes.push(cajas === 1 ? '1 caja' : `${cajas} cajas`)
  if (unidades > 0) partes.push(unidades === 1 ? '1 unidad' : `${unidades} unidades`)
  return partes.length === 0 ? 'Sin stock' : partes.join(' y ')
}
