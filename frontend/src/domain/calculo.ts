/**
 * Motor de cálculo de la venta (VTA-04, INV-14; `design.md` D13 y D14 del change 18a, ADR-016,
 * ADR-050). Espejo de `backend/app/modules/ventas/domain/calculo.py`: mismos casos de
 * `shared/fixtures/calculo/vta-04-totales.json` (`"motor": "vta04"`).
 *
 * Función pura que orquesta, por línea, el bruto de PRC-22 (`domain/precios/brutoDeLinea`) y los
 * descuentos de DSC-05 (`domain/descuentos/motor`), y aplica VTA-04 en modo impositivo `A`: el IVA
 * de cada línea es cero y
 *
 *     neto de línea = bruto - descuentos
 *     totalNeto     = suma de netos
 *     totalIva      = suma de IVA (cero en modo A)
 *     total         = totalNeto + totalIva                                       (INV-14)
 *
 * Los modos `B` y `C` son de la etapa 4 y se rechazan con `ErrorDeCalculoDeVenta`
 * (`MODO_IMPOSITIVO_NO_SOPORTADO`). Cada línea conserva la alícuota del producto con que se
 * calculó (FAC-08). Un solo redondeo por línea, el del bruto (TR-03). Nada se convierte a `number`
 * para calcular (INV-03).
 */

import type { Importe } from '../lib/money'
import { parsearImporteDesdeApi, redondearImporte } from '../lib/money'
import { calcularDescuentos } from './descuentos/motor'
import type { DescuentoAplicado, LineaVenta, ReglaDescuento } from './descuentos/tipos'
import { calcularBrutoDeLinea } from './precios/brutoDeLinea'

export const MODO_IMPOSITIVO_A = 'A'

export type CodigoErrorDeCalculoDeVenta =
  | 'MODO_IMPOSITIVO_NO_SOPORTADO'
  | 'VENTA_SIN_LINEAS'
  | 'ENTRADA_NO_ES_DINERO_EXACTO'

/** Error de dominio del cálculo de la venta, con el mismo código estable que el backend. */
export class ErrorDeCalculoDeVenta extends Error {
  readonly codigo: CodigoErrorDeCalculoDeVenta

  constructor(codigo: CodigoErrorDeCalculoDeVenta, mensaje: string) {
    super(mensaje)
    this.name = 'ErrorDeCalculoDeVenta'
    this.codigo = codigo
  }
}

/**
 * Una línea tal como entra al motor: precio y unidades de referencia (PRC-22), cantidad base,
 * alícuota del producto (fracción como cadena, `"0.210000"`) y los datos del motor de descuentos.
 */
export interface LineaCalculo {
  id: string
  precioReferencia: string
  unidadesReferencia: number
  cantidadBase: number
  alicuota: string
  productoId: string
  categoriaId: string
  marcaId: string
  descuentoManual: string | null
}

export interface ResultadoLineaVenta {
  id: string
  bruto: Importe
  descuentos: readonly DescuentoAplicado[]
  descuentoTotal: Importe
  neto: Importe
  alicuota: Importe
  importeIva: Importe
}

export interface ResultadoVenta {
  modoImpositivo: string
  lineas: readonly ResultadoLineaVenta[]
  totalNeto: Importe
  totalIva: Importe
  total: Importe
}

function exigirAlicuota(linea: LineaCalculo): Importe {
  const valor: unknown = linea.alicuota
  if (typeof valor !== 'string') {
    throw new ErrorDeCalculoDeVenta(
      'ENTRADA_NO_ES_DINERO_EXACTO',
      `La alícuota de la línea "${linea.id}" debe ser una cadena decimal exacta, no ` +
        `${typeof valor}: ${String(valor)} (INV-03: nunca punto flotante)`,
    )
  }
  return parsearImporteDesdeApi(valor)
}

/**
 * Calcula bruto, descuentos, neto, IVA y total de la venta (VTA-04, INV-14). Rechaza un modo
 * distinto de `A` (D13) y una venta sin líneas antes de calcular nada; cualquier otra entrada
 * inválida lanza el error de dominio de precios o descuentos que corresponde, sin devolver un
 * resultado parcial.
 */
export function calcularVenta(
  modoImpositivo: string,
  lineas: readonly LineaCalculo[],
  reglas: readonly ReglaDescuento[],
  descuentoManualGeneral: string | null,
): ResultadoVenta {
  if (modoImpositivo !== MODO_IMPOSITIVO_A) {
    throw new ErrorDeCalculoDeVenta(
      'MODO_IMPOSITIVO_NO_SOPORTADO',
      `El modo impositivo "${modoImpositivo}" no está soportado: solo se vende en modo ` +
        `"${MODO_IMPOSITIVO_A}" (los modos B y C son de la etapa 4).`,
    )
  }
  if (lineas.length === 0) {
    throw new ErrorDeCalculoDeVenta('VENTA_SIN_LINEAS', 'Una venta necesita al menos una línea.')
  }

  const alicuotas = lineas.map(exigirAlicuota)
  const paraDescuentos: LineaVenta[] = lineas.map((linea) => ({
    id: linea.id,
    bruto: calcularBrutoDeLinea(
      linea.precioReferencia,
      linea.unidadesReferencia,
      linea.cantidadBase,
    ).toFixed(2),
    cantidadBase: linea.cantidadBase,
    unidadesReferencia: linea.unidadesReferencia,
    productoId: linea.productoId,
    categoriaId: linea.categoriaId,
    marcaId: linea.marcaId,
    descuentoManual: linea.descuentoManual,
  }))
  const descuentos = calcularDescuentos(paraDescuentos, reglas, descuentoManualGeneral)

  const cero = redondearImporte('0')
  const resultado = descuentos.lineas.map((calculada, posicion): ResultadoLineaVenta => {
    const entrada = paraDescuentos[posicion] as LineaVenta
    return {
      id: entrada.id,
      bruto: parsearImporteDesdeApi(entrada.bruto),
      descuentos: calculada.descuentos,
      descuentoTotal: calculada.descuentoTotal,
      neto: calculada.neto,
      alicuota: alicuotas[posicion] as Importe,
      importeIva: cero,
    }
  })
  const totalNeto = resultado.reduce((suma, linea) => suma.plus(linea.neto), cero)
  const totalIva = resultado.reduce((suma, linea) => suma.plus(linea.importeIva), cero)
  return {
    modoImpositivo,
    lineas: resultado,
    totalNeto,
    totalIva,
    total: totalNeto.plus(totalIva),
  }
}
