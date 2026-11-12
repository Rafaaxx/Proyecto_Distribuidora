/**
 * Motor de descuentos de una venta (DSC-05, DSC-06, DSC-07, DSC-08; `design.md` D7 a D11 del
 * change 16). Espejo de `backend/app/modules/descuentos/domain/motor.py`: mismos casos de
 * `shared/fixtures/calculo/dsc-05-descuentos.json` (`"motor": "dsc05"`, ADR-016).
 *
 * Función pura: de las líneas con su bruto ya calculado (PRC-22), las reglas aplicables y el
 * descuento manual, devuelve por línea los descuentos en el orden en que se aplicaron, su total y
 * su neto. No calcula IVA ni el total de la venta (VTA-04, change 18a).
 *
 * Orden de resolución (DSC-05):
 *  1. El bruto de cada línea viene dado.
 *  2. Se evalúan las condiciones de todas las reglas sobre cantidades y brutos (D6).
 *  3. Entre las no acumulables que aplican gana UNA para toda la venta: la de mayor beneficio
 *     total sobre el bruto; empate por prioridad (número más bajo) y, si persiste, la creada
 *     primero (D7, D8).
 *  4. Las acumulables, por prioridad y antigüedad, cada una sobre el resultado anterior (D9).
 *  5. El descuento manual: el porcentaje propio de la línea si lo trae, el general si no; uno solo
 *     por línea, siempre el último (D11).
 *
 * El resultado no depende del orden en que se entregan las reglas ni sus alcances. Nada se
 * convierte a `number` para calcular (INV-03); el redondeo sale de `lib/money.ts`.
 */

import type { Importe } from '../../lib/money'
import { parsearImporteDesdeApi, redondearCosto, redondearImporte } from '../../lib/money'
import { descuentoPorcentual, repartirImporteFijo } from './acciones'
import { cumpleCondicion, indicesElegibles } from './condicion'
import { ErrorDeDescuentos } from './errores'
import type {
  DescuentoAplicado,
  LineaResultado,
  LineaVenta,
  ReglaDescuento,
  ResultadoDescuentos,
} from './tipos'
import { ACCIONES, MEDIDAS, OPERADORES, TIPOS_ALCANCE, TIPOS_REGLA } from './tipos'

const DECIMAL_EXACTO = /^-?\d+(\.\d+)?$/

function esEnteroPositivo(valor: unknown): boolean {
  return typeof valor === 'number' && Number.isInteger(valor) && valor >= 1
}

/** Cadena decimal exacta; un `number` u otro tipo es punto flotante o basura (INV-03). */
function exigirDecimal(valor: unknown, nombre: string): Importe {
  if (typeof valor !== 'string' || !DECIMAL_EXACTO.test(valor.trim())) {
    throw new ErrorDeDescuentos(
      'ENTRADA_NO_ES_DINERO_EXACTO',
      `${nombre} debe ser una cadena decimal exacta, no ${typeof valor}: ${String(valor)} ` +
        '(INV-03: nunca punto flotante)',
    )
  }
  return parsearImporteDesdeApi(valor)
}

function validarLinea(linea: LineaVenta): void {
  const bruto = exigirDecimal(linea.bruto, 'El bruto de la línea')
  if (bruto.isNegative() || bruto.decimalPlaces() > 2) {
    throw new ErrorDeDescuentos(
      'LINEA_DESCUENTO_INVALIDA',
      `El bruto de la línea "${linea.id}" debe ser un importe no negativo de hasta 2 decimales ` +
        `(recibido ${linea.bruto}).`,
    )
  }
  if (!esEnteroPositivo(linea.cantidadBase)) {
    throw new ErrorDeDescuentos(
      'LINEA_DESCUENTO_INVALIDA',
      `La cantidad base de la línea "${linea.id}" debe ser un entero positivo.`,
    )
  }
  if (!esEnteroPositivo(linea.unidadesReferencia)) {
    throw new ErrorDeDescuentos(
      'LINEA_DESCUENTO_INVALIDA',
      `Las unidades de referencia de la línea "${linea.id}" deben ser un entero >= 1.`,
    )
  }
}

/**
 * Fracción de hasta 6 decimales, mayor que 0 y hasta 1; un `number` no es válido (DSC-06, TR-02,
 * INV-03; D11, D11.1).
 */
export function validarPorcentajeManual(valor: unknown, nombre: string): void {
  const invalido = (): never => {
    throw new ErrorDeDescuentos(
      'DESCUENTO_MANUAL_INVALIDO',
      `${nombre} debe ser una fracción mayor que 0 y hasta 1 con hasta 6 decimales ` +
        `(recibido ${String(valor)}).`,
    )
  }
  if (typeof valor !== 'string' || !DECIMAL_EXACTO.test(valor.trim())) {
    return invalido()
  }
  const decimal = parsearImporteDesdeApi(valor)
  if (decimal.lessThanOrEqualTo(0) || decimal.greaterThan(1) || decimal.decimalPlaces() > 6) {
    invalido()
  }
}

function validarRegla(regla: ReglaDescuento): void {
  if (
    !TIPOS_REGLA.includes(regla.tipo) ||
    !MEDIDAS.includes(regla.medida) ||
    !OPERADORES.includes(regla.operador) ||
    !ACCIONES.includes(regla.accionTipo) ||
    regla.alcances.some((alcance) => !TIPOS_ALCANCE.includes(alcance.tipo))
  ) {
    throw new ErrorDeDescuentos(
      'REGLA_DESCUENTO_INVALIDA',
      `La regla "${regla.id}" trae un tipo, medida, operador, acción o alcance desconocido.`,
    )
  }
  exigirDecimal(regla.umbral, 'El umbral de la regla')
  if (regla.accionTipo === 'PORCENTAJE') {
    const porcentaje = exigirDecimal(regla.accionPorcentaje, 'El porcentaje de la regla')
    if (porcentaje.lessThanOrEqualTo(0) || porcentaje.greaterThan(1)) {
      throw new ErrorDeDescuentos(
        'REGLA_DESCUENTO_INVALIDA',
        `El porcentaje de la regla "${regla.id}" debe ser mayor que 0 y hasta 1.`,
      )
    }
  } else if (exigirDecimal(regla.accionImporte, 'El importe de la regla').lessThanOrEqualTo(0)) {
    throw new ErrorDeDescuentos(
      'REGLA_DESCUENTO_INVALIDA',
      `El importe de la regla "${regla.id}" debe ser mayor que 0.`,
    )
  }
}

function descuentosDeRegla(regla: ReglaDescuento, importes: readonly Importe[]): Importe[] {
  return regla.accionTipo === 'PORCENTAJE'
    ? descuentoPorcentual(importes, regla.accionPorcentaje as string)
    : repartirImporteFijo(importes, regla.accionImporte as string)
}

function compararTexto(a: string, b: string): number {
  return a < b ? -1 : a > b ? 1 : 0
}

/** Prioridad (número más bajo primero) y, si empatan, la creada primero (UUIDv7). */
function compararPorOrden(a: ReglaDescuento, b: ReglaDescuento): number {
  return a.prioridad - b.prioridad || compararTexto(a.id, b.id)
}

/**
 * Calcula los descuentos de la venta. Lanza `ErrorDeDescuentos` si alguna entrada no es válida
 * y, en ese caso, no devuelve nada (tampoco para las demás líneas).
 */
export function calcularDescuentos(
  lineas: readonly LineaVenta[],
  reglas: readonly ReglaDescuento[],
  descuentoManualGeneral: string | null,
): ResultadoDescuentos {
  lineas.forEach(validarLinea)
  reglas.forEach(validarRegla)
  if (descuentoManualGeneral !== null) {
    validarPorcentajeManual(descuentoManualGeneral, 'El descuento manual general')
  }
  for (const linea of lineas) {
    if (linea.descuentoManual !== null) {
      validarPorcentajeManual(linea.descuentoManual, `El descuento manual propio de la línea "${linea.id}"`)
    }
  }

  const cero = redondearImporte('0')
  const importes: Importe[] = lineas.map((linea) => parsearImporteDesdeApi(linea.bruto))
  const detalle: DescuentoAplicado[][] = lineas.map(() => [])

  const aplicar = (regla: ReglaDescuento): void => {
    const elegibles = indicesElegibles(regla, lineas)
    const partes = descuentosDeRegla(
      regla,
      elegibles.map((posicion) => importes[posicion] as Importe),
    )
    const porcentaje =
      regla.accionTipo === 'PORCENTAJE' ? redondearCosto(regla.accionPorcentaje as string) : null
    elegibles.forEach((posicion, i) => {
      const parte = partes[i] as Importe
      if (parte.greaterThan(0)) {
        // un descuento que redondea a cero no se informa (D9)
        detalle[posicion]?.push({ origen: 'AUTOMATICO', reglaId: regla.id, porcentaje, importe: parte })
        importes[posicion] = (importes[posicion] as Importe).minus(parte)
      }
    })
  }

  // Paso 2: las condiciones se evalúan una sola vez, sobre cantidades y brutos (D6).
  const aplicables = reglas.filter((regla) => cumpleCondicion(regla, lineas))

  // Paso 3: una sola no acumulable por venta (D7, D8).
  const noAcumulables = aplicables.filter((regla) => !regla.acumulable)
  if (noAcumulables.length > 0) {
    const beneficios = new Map<ReglaDescuento, Importe>()
    for (const regla of noAcumulables) {
      const brutos = indicesElegibles(regla, lineas).map((posicion) =>
        parsearImporteDesdeApi((lineas[posicion] as LineaVenta).bruto),
      )
      beneficios.set(
        regla,
        descuentosDeRegla(regla, brutos).reduce((suma, parte) => suma.plus(parte), cero),
      )
    }
    const ganadora = [...noAcumulables].sort(
      (a, b) =>
        (beneficios.get(b) as Importe).cmp(beneficios.get(a) as Importe) || compararPorOrden(a, b),
    )[0] as ReglaDescuento
    aplicar(ganadora)
  }

  // Paso 4: las acumulables, en orden, cada una sobre el resultado anterior (D9).
  for (const regla of aplicables.filter((r) => r.acumulable).sort(compararPorOrden)) {
    aplicar(regla)
  }

  // Paso 5: descuento manual; el propio de la línea reemplaza al general (D11).
  let manualMaximo: Importe | null = null
  for (const [posicion, linea] of lineas.entries()) {
    const porcentajeManual = linea.descuentoManual ?? descuentoManualGeneral
    if (porcentajeManual === null) {
      continue
    }
    const actual = importes[posicion] as Importe
    const importe = redondearImporte(actual.times(parsearImporteDesdeApi(porcentajeManual)))
    if (importe.greaterThan(0)) {
      const porcentaje = redondearCosto(porcentajeManual)
      detalle[posicion]?.push({ origen: 'MANUAL', reglaId: null, porcentaje, importe })
      importes[posicion] = actual.minus(importe)
      if (manualMaximo === null || porcentaje.greaterThan(manualMaximo)) {
        manualMaximo = porcentaje
      }
    }
  }

  const resultado: LineaResultado[] = lineas.map((linea, posicion) => {
    const descuentos = detalle[posicion] as DescuentoAplicado[]
    return {
      id: linea.id,
      descuentos,
      descuentoTotal: descuentos.reduce((suma, d) => suma.plus(d.importe), cero),
      neto: redondearImporte(importes[posicion] as Importe),
    }
  })
  return { lineas: resultado, porcentajeManualMaximo: manualMaximo }
}
