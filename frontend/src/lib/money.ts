/**
 * Redondeo de dinero (`docs/02-arquitectura.md` §10.3, INV-03).
 *
 * Único módulo del frontend que cuantiza importes, costos y porcentajes.
 * Usa decimal.js configurado con `ROUND_HALF_UP`, con el mismo contrato de
 * `backend/app/core/money.py`: `redondearImporte` (2 decimales) y
 * `redondearCosto` (6 decimales). Ningún importe se convierte a `number`
 * nativo para calcular -- solo `formatearImporte` lo hace, y solo para
 * mostrar.
 */

import Decimal from 'decimal.js'

/**
 * Instancia de decimal.js dedicada a dinero: `ROUND_HALF_UP` explícito y
 * `precision: 50` (change 06, tarea 11.1) para que los cocientes
 * intermedios de CST-02 (`domain/proveedores/costoBase.ts`) tengan la misma
 * precisión ampliada que `_PRECISION_INTERMEDIA` en
 * `backend/app/modules/proveedores/domain/costo_base.py` -- la única
 * cuantización real sigue siendo la de `redondearCosto` al final.
 */
const DecimalDinero = Decimal.clone({ rounding: Decimal.ROUND_HALF_UP, precision: 50 })

export type Importe = InstanceType<typeof DecimalDinero>

/** La entrada no es un valor decimal exacto (INV-03). */
export class EntradaNoEsDineroExactoError extends Error {
  constructor(mensaje: string) {
    super(mensaje)
    this.name = 'EntradaNoEsDineroExactoError'
  }
}

function aDecimalExacto(valor: string | Importe): Importe {
  // `typeof valor === 'number'` cubre el flotante binario nativo de
  // JavaScript, incluido el caso en que llega desde código sin tipar; en
  // TypeScript estricto la firma ya lo excluye, pero la guardia en runtime
  // es la que realmente cierra INV-03.
  if (typeof valor === 'number') {
    throw new EntradaNoEsDineroExactoError(
      `No se puede redondear un number nativo: ${String(valor)} ` +
        '(INV-03: usar una cadena numérica exacta o un Importe ya construido)',
    )
  }

  if (valor instanceof DecimalDinero) {
    return valor
  }

  if (typeof valor === 'string') {
    if (!/^-?\d+(\.\d+)?$/.test(valor.trim())) {
      throw new EntradaNoEsDineroExactoError(
        `La cadena "${valor}" no representa un valor decimal exacto`,
      )
    }
    return new DecimalDinero(valor)
  }

  throw new EntradaNoEsDineroExactoError(
    `Tipo de entrada no soportado para redondeo de dinero: ${typeof valor}`,
  )
}

/**
 * Cuantiza un importe a 2 decimales con `ROUND_HALF_UP` (`NUMERIC(14,2)`).
 *
 * El medio se desempata siempre alejándose de cero: `0.125 -> 0.13`,
 * `-0.125 -> -0.13`.
 */
export function redondearImporte(valor: string | Importe): Importe {
  return aDecimalExacto(valor).toDecimalPlaces(2)
}

/**
 * Cuantiza un costo por unidad base o un porcentaje a 6 decimales con
 * `ROUND_HALF_UP` (`NUMERIC(18,6)` / `NUMERIC(9,6)`, `design.md` D4).
 */
export function redondearCosto(valor: string | Importe): Importe {
  return aDecimalExacto(valor).toDecimalPlaces(6)
}

/**
 * Convierte la cadena de un importe recibida de la API (`"31250.00"`) en un
 * valor decimal exacto, sin pasar en ningún punto por `number` (`02` §10.3).
 */
export function parsearImporteDesdeApi(valorApi: string): Importe {
  return aDecimalExacto(valorApi)
}

/**
 * Formatea un `Importe` con miles agrupados con `.` y `,` como separador
 * decimal (es-AR), a la cantidad fija de `decimales` pedida. Manipulación
 * de cadenas sobre `toFixed(decimales)` -- nunca pasa por `number`
 * (INV-03). Helper privado compartido por `formatearImporte` y
 * `formatearCosto`; ninguna de las dos duplica la lógica de agrupación.
 */
function formatearConMilesEsAr(importe: Importe, decimales: number): string {
  const partes = importe.toFixed(decimales).split('.')
  const entero = partes[0] ?? '0'
  const parteDecimal = partes[1] ?? '0'.repeat(decimales)
  const negativo = entero.startsWith('-')
  const digitos = negativo ? entero.slice(1) : entero
  const enteroAgrupado = digitos.replace(/\B(?=(\d{3})+(?!\d))/g, '.')
  return `${negativo ? '-' : ''}${enteroAgrupado},${parteDecimal}`
}

/**
 * Formatea un importe ya redondeado para mostrarlo en pantalla: dos
 * decimales fijos, miles agrupados con `.` y `,` como separador decimal
 * (es-AR), igual criterio que `formatearCosto` -- "31250" -> "31.250,00".
 * Es el único punto donde el valor se convierte a texto para el usuario;
 * nunca se usa el resultado para volver a calcular ni para serializar a
 * la API (esa serialización usa siempre la cadena sin formatear, `02` §10.3).
 */
export function formatearImporte(importe: Importe): string {
  return formatearConMilesEsAr(importe, 2)
}

/**
 * Formatea un costo ya redondeado para mostrarlo en pantalla (tarea 11.4,
 * `CostosCargaScreen.tsx` y `CostosHistorialScreen.tsx`): seis decimales
 * fijos, miles agrupados con `.` y `,` como separador decimal (es-AR;
 * spec `administracion-de-proveedores`, "1.239,669421"). Nunca pasa por
 * `number` (INV-03), igual criterio que `formatearImporte`.
 */
export function formatearCosto(importe: Importe): string {
  return formatearConMilesEsAr(importe, 6)
}

/**
 * Formatea una fracción (`alicuota_aplicada`, `bonificacion` -- TR-02) como
 * porcentaje para mostrar (tarea 14.5, corrección de la verificación
 * manual 13.5): multiplica por 100 con decimal.js (nunca `number`) y
 * muestra hasta cuatro decimales, sin ceros de relleno -- `0.21` ->
 * `"21 %"`, `0.105` -> `"10,5 %"`, `0` -> `"0 %"`. Separador decimal `,`
 * (es-AR), igual criterio que `formatearCosto`.
 */
export function formatearPorcentaje(fraccion: Importe): string {
  const porcentaje = fraccion.mul(100)
  const [entero = '0', decimales = ''] = porcentaje.toFixed(4).split('.')
  const decimalesSinCeros = decimales.replace(/0+$/, '')
  return decimalesSinCeros ? `${entero},${decimalesSinCeros} %` : `${entero} %`
}
