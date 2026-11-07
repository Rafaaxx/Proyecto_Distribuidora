import { formatearImporte, parsearImporteDesdeApi } from '../../lib/money'

/**
 * Presentación de los reportes (change 26, D1, D5, D12; TR-04, INV-03). Lógica pura, sin React: todo sale del
 * string de la API y nunca pasa por `number` para calcular. Los textos son los aprobados en 0.2 (D12).
 */

/** Un importe `"31250.00"` de la API como «31.250,00» (INV-03). */
export function formatearImporteDeReporte(valorApi: string): string {
  return formatearImporte(parsearImporteDesdeApi(valorApi))
}

/** Cajas equivalentes `"2.50"` de la API como «2,50» (REP-03): dos decimales, como las manda el servidor. */
export function formatearCajas(valorApi: string): string {
  return formatearImporte(parsearImporteDesdeApi(valorApi))
}

/** Unidades base (entero) con miles agrupados. */
export function formatearUnidades(unidades: number): string {
  return String(unidades).replace(/\B(?=(\d{3})+(?!\d))/g, '.')
}

/** Una fecha de negocio `aaaa-mm-dd` como `dd/mm/aaaa`, sin construir un `Date` (TR-04). */
export function formatearFechaDeNegocio(fecha: string): string {
  const [anio = '', mes = '', dia = ''] = fecha.split('-')
  return `${dia}/${mes}/${anio}`
}

/** El día `dd/mm/aaaa` de un momento ISO en la zona horaria de la organización (TR-04). */
export function formatearMomento(momento: string, zonaHoraria: string): string {
  return new Intl.DateTimeFormat('es-AR', {
    timeZone: zonaHoraria,
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  }).format(new Date(momento))
}

/** «Período: {desde} al {hasta}» (D12). */
export function textoDePeriodo(desde: string, hasta: string): string {
  return `Período: ${formatearFechaDeNegocio(desde)} al ${formatearFechaDeNegocio(hasta)}`
}

/** La nota de las líneas sin costo (D5, D12). */
export function textoDeLineasSinCosto(sinCosto: { lineas: number; importe_neto: string }): string {
  return (
    `Líneas sin costo: ${String(sinCosto.lineas)}, con un neto de ${formatearImporteDeReporte(sinCosto.importe_neto)}. ` +
    'No entran en el costo vendido ni en la utilidad.'
  )
}

/** La nota de la sección de anuladas (D2, D12). */
export function textoDeAnuladas(cantidad: number, total: string): string {
  return `${String(cantidad)} ventas anuladas por ${formatearImporteDeReporte(total)}. No entran en los totales.`
}

/** La nota de los ajustes anulados (D10, D12). */
export function textoDeAjustesAnulados(cantidad: number): string {
  return `Ajustes anulados: ${String(cantidad)}. No entran en los totales.`
}

/**
 * Un saldo de cuenta corriente (CC-04): el negativo es saldo a favor y se muestra sin signo con la marca
 * «a favor» (D12). Sale del string de la API, sin pasar por `number` (INV-03).
 */
export function formatearSaldoDeCuenta(saldoApi: string): string {
  const saldo = parsearImporteDesdeApi(saldoApi)
  return saldo.isNegative() && !saldo.isZero() ? `${formatearImporte(saldo.abs())} a favor` : formatearImporte(saldo)
}

/** El «Total a favor» llega negativo (suma de los saldos negativos): se muestra sin signo. */
export function formatearTotalAFavor(totalApi: string): string {
  return formatearImporte(parsearImporteDesdeApi(totalApi).abs())
}

/** ABIERTA se marca «En curso» (D7, D12); el resto con su etiqueta. */
const ETIQUETAS_DE_JORNADA: Readonly<Record<string, string>> = {
  ABIERTA: 'En curso',
  EN_RENDICION: 'En rendición',
  CERRADA: 'Cerrada',
  LIBERADA: 'Liberada',
}

/** El estado de una jornada con su etiqueta aprobada (D12); uno desconocido se muestra tal cual. */
export function etiquetaDeEstadoDeJornada(estado: string): string {
  return ETIQUETAS_DE_JORNADA[estado] ?? estado
}
