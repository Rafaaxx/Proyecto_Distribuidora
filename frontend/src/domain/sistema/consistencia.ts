import { formatearCosto, formatearImporte, parsearImporteDesdeApi } from '../../lib/money'

/**
 * El aviso de consistencia de `/admin` (change 28, tarea 3.2; D5; ADR-015, INV-12, INV-13): cómo se cuenta cada
 * diferencia. Lógica pura, sin React. Los importes vienen como string de la API y salen de `lib/money.ts`, nunca
 * de `number` (INV-03); las cantidades de stock son enteros en unidad base.
 */

export interface DiferenciaParaAviso {
  tipo: string
  cuenta_tipo: string | null
  entidad_nombre: string | null
  saldo_materializado: string | null
  suma_del_libro: string | null
  producto_nombre: string | null
  ubicacion_nombre: string | null
  materializado: number | null
  esperado: number | null
  promedio_vigente: string | null
  promedio_historia: string | null
}

export interface ConsistenciaParaAviso {
  resultado: string | null
  ejecutada_en: string | null
  diferencias: readonly unknown[]
}

const SIN_NOMBRE = 'nombre no disponible'

/** El aviso se muestra solo si la última corrida encontró diferencias. */
export function hayDiferencias(consistencia: ConsistenciaParaAviso | undefined): boolean {
  return consistencia?.resultado === 'CON_DIFERENCIAS'
}

function importe(valor: string | null): string {
  return valor === null ? '—' : `$ ${formatearImporte(parsearImporteDesdeApi(valor))}`
}

function costo(valor: string | null): string {
  return valor === null ? '—' : `$ ${formatearCosto(parsearImporteDesdeApi(valor))}`
}

function cantidad(valor: number | null): string {
  return valor === null ? '—' : String(valor)
}

function descripcionDeCuenta(diferencia: DiferenciaParaAviso): string {
  const clase = diferencia.cuenta_tipo === 'CLIENTE' ? 'cliente' : 'proveedor'
  const de =
    diferencia.entidad_nombre === null
      ? `de un ${clase} (${SIN_NOMBRE})`
      : `del ${clase} ${diferencia.entidad_nombre}`
  return `Cuenta ${de}: saldo guardado ${importe(diferencia.saldo_materializado)}, suma de sus movimientos ${importe(diferencia.suma_del_libro)}.`
}

/** Una línea de texto para una diferencia, con los nombres que resolvió el servidor al mostrar. */
export function descripcionDeDiferencia(diferencia: DiferenciaParaAviso): string {
  const producto = diferencia.producto_nombre ?? `un producto (${SIN_NOMBRE})`
  switch (diferencia.tipo) {
    case 'SALDO_CUENTA':
      return descripcionDeCuenta(diferencia)
    case 'STOCK_SALDO': {
      const ubicacion = diferencia.ubicacion_nombre ?? `una ubicación (${SIN_NOMBRE})`
      return `Stock de ${producto} en ${ubicacion}: guardado ${cantidad(diferencia.materializado)}, según sus movimientos ${cantidad(diferencia.esperado)}.`
    }
    case 'STOCK_TOTAL':
      return `Stock total de ${producto}: guardado ${cantidad(diferencia.materializado)}, suma de sus ubicaciones ${cantidad(diferencia.esperado)}.`
    case 'PROMEDIO_COSTO': {
      const historia =
        diferencia.promedio_historia === null
          ? 'sin historial para compararlo'
          : `según su historial ${costo(diferencia.promedio_historia)}`
      return `Costo promedio de ${producto}: vigente ${costo(diferencia.promedio_vigente)}, ${historia}.`
    }
    default:
      return `Diferencia de tipo ${diferencia.tipo} en ${producto}.`
  }
}
