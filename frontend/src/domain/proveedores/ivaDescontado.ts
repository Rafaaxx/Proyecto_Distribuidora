/**
 * ¿Se descontó IVA al calcular el costo base? (11b, CST-06, TR-06). Se decide con las dos
 * columnas congeladas en el costo o en la línea de compra (`computa_credito_fiscal` e
 * `incluye_iva`), nunca con la condición actual de la organización: un registro anterior a
 * un cambio de condición conserva su regla.
 */
export interface ReglaDeIvaCongelada {
  computa_credito_fiscal: boolean
  incluye_iva: boolean
}

export function ivaDescontado(registro: ReglaDeIvaCongelada): boolean {
  return registro.computa_credito_fiscal && registro.incluye_iva
}

export function etiquetaIvaDescontado(registro: ReglaDeIvaCongelada): string {
  return `IVA descontado: ${ivaDescontado(registro) ? 'Sí' : 'No'}`
}
