/**
 * Visualización de cantidades: cajas + unidades (CAT-08, `01` §5,
 * `design.md` D8). Función pura sobre enteros seguros -- no es cálculo de
 * dinero, así que no se usa `decimal.js` acá, pero SÍ se valida
 * `Number.isSafeInteger` en cada entrada (`design.md` D8): un `number` que
 * perdió precisión nunca produce un resultado silenciosamente incorrecto.
 * Idéntica en espíritu a `backend/app/modules/catalogo/domain/cantidades.py`
 * -- ambas se ejercitan contra los mismos casos de
 * `shared/fixtures/calculo/cat-08-visualizacion.json`.
 */

export class UnidadesDeReferenciaInvalidasError extends Error {
  constructor(mensaje: string) {
    super(mensaje)
    this.name = 'UnidadesDeReferenciaInvalidasError'
  }
}

export interface CantidadVisualizada {
  cajas: number
  unidades: number
  negativo: boolean
}

/**
 * `floor(|q| / u)` cajas y `|q| mod u` unidades, signo aplicado al
 * conjunto si `cantidadBase < 0` (CAT-08). `Math.trunc`/`%` sobre enteros
 * seguros son exactos (INV-04): sin acumulación de error de punto
 * flotante porque nunca hay parte fraccionaria de por medio.
 */
export function visualizarCantidad(
  cantidadBase: number,
  unidadesReferencia: number,
): CantidadVisualizada {
  if (!Number.isSafeInteger(unidadesReferencia)) {
    throw new UnidadesDeReferenciaInvalidasError(
      `Las unidades de referencia deben ser un entero seguro, no ${String(unidadesReferencia)}.`,
    )
  }
  if (unidadesReferencia < 1) {
    throw new UnidadesDeReferenciaInvalidasError(
      `Las unidades de referencia deben ser un entero >= 1 (recibido ${unidadesReferencia}).`,
    )
  }
  if (!Number.isSafeInteger(cantidadBase)) {
    throw new UnidadesDeReferenciaInvalidasError(
      `La cantidad base debe ser un entero seguro, no ${String(cantidadBase)}.`,
    )
  }

  const absoluto = Math.abs(cantidadBase)
  const cajas = Math.trunc(absoluto / unidadesReferencia)
  const unidades = absoluto % unidadesReferencia
  return { cajas, unidades, negativo: cantidadBase < 0 }
}
