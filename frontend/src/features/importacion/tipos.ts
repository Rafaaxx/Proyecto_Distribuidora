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
  {
    valor: 'COSTOS',
    etiqueta: 'Costos',
    // Change 11b (CST-06): el valor es lo que se pagó; el IVA solo se descuenta si la
    // organización es responsable inscripta.
    ayuda:
      'En "valor" cargá el valor pagado por la presentación completa. La columna incluye_iva (S o N) es ' +
      'obligatoria para un responsable inscripto, que descuenta el IVA; si tu organización es monotributista ' +
      'o exenta, dejala vacía o con N: una S se rechaza.',
  },
  {
    valor: 'STOCK_INICIAL',
    etiqueta: 'Stock inicial',
    ayuda:
      'El costo unitario es por unidad base, tal como lo pagaste: si tu organización no descuenta el IVA ' +
      '(monotributista o exenta), con el IVA incluido.',
  },
  { valor: 'SALDOS_INICIALES', etiqueta: 'Saldos iniciales' },
] as const

interface TipoOfrecido {
  valor: string
  etiqueta: string
  ayuda?: string
}

export type TipoDeImportacion = (typeof TIPOS_DE_IMPORTACION)[number]['valor']

/** Ayuda del tipo para mostrar bajo el selector, o `null` si no tiene. */
export function ayudaDeTipo(tipo: string): string | null {
  const encontrado = (TIPOS_DE_IMPORTACION as readonly TipoOfrecido[]).find((t) => t.valor === tipo)
  return encontrado?.ayuda ?? null
}

/** Etiqueta para mostrar; un tipo desconocido (de un servidor más nuevo) se muestra tal cual. */
export function etiquetaDeTipo(tipo: string): string {
  return TIPOS_DE_IMPORTACION.find((t) => t.valor === tipo)?.etiqueta ?? tipo
}
