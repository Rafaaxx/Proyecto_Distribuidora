/**
 * Tipos de importación que ofrece la pantalla (change 10, `design.md` D9). Son los que
 * tienen importador en el servidor; `PRECIOS` (listas de precios) no se ofrece hasta el
 * change 13. El orden es el recomendado para la puesta en marcha: primero los maestros de
 * los que dependen los demás (los costos y el stock inicial referencian productos; los
 * saldos, clientes y proveedores).
 */
export const TIPOS_DE_IMPORTACION = [
  { valor: 'PROVEEDORES', etiqueta: 'Proveedores' },
  { valor: 'PRODUCTOS', etiqueta: 'Productos' },
  { valor: 'CLIENTES', etiqueta: 'Clientes' },
  { valor: 'COSTOS', etiqueta: 'Costos' },
  { valor: 'STOCK_INICIAL', etiqueta: 'Stock inicial' },
  { valor: 'SALDOS_INICIALES', etiqueta: 'Saldos iniciales' },
] as const

export type TipoDeImportacion = (typeof TIPOS_DE_IMPORTACION)[number]['valor']

/** Etiqueta para mostrar; un tipo desconocido (de un servidor más nuevo) se muestra tal cual. */
export function etiquetaDeTipo(tipo: string): string {
  return TIPOS_DE_IMPORTACION.find((t) => t.valor === tipo)?.etiqueta ?? tipo
}
