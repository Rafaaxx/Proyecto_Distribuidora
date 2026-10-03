/**
 * Mapea el `codigo` de un `ErrorDeProveedores` (tarea 11.2) al campo del
 * formulario donde se muestra, mismo criterio que
 * `features/catalogo/mapaErrorACampo.ts`. `null` cuando el error no
 * corresponde a un campo puntual (se muestra como mensaje general).
 */

/** Campos de la ficha de proveedor (`ProveedorFormScreen.tsx`, tarea 11.3). */
export type CampoProveedor = 'nombre' | 'cuit'

const MAPA_CODIGO_A_CAMPO_PROVEEDOR: Record<string, CampoProveedor> = {
  NOMBRE_INVALIDO: 'nombre',
  NOMBRE_DUPLICADO: 'nombre',
  CUIT_INVALIDO: 'cuit',
  CUIT_DUPLICADO: 'cuit',
}

export function campoDeProveedorParaCodigo(codigo: string): CampoProveedor | null {
  return MAPA_CODIGO_A_CAMPO_PROVEEDOR[codigo] ?? null
}

/** Campos de una fila de la carga de costos (`CostosCargaScreen.tsx`,
 * tarea 11.4). */
export type CampoCosto = 'productoId' | 'presentacionId' | 'valor' | 'bonificacion' | 'vigenciaDesde'

const MAPA_CODIGO_A_CAMPO_COSTO: Record<string, CampoCosto> = {
  VALOR_INVALIDO: 'valor',
  // 11b (CST-06): sin crédito fiscal no hay casilla de IVA; el error va en el valor pagado.
  INCLUYE_IVA_NO_APLICA: 'valor',
  BONIFICACION_INVALIDA: 'bonificacion',
  PRESENTACION_INVALIDA: 'presentacionId',
  PRODUCTO_INACTIVO: 'productoId',
  PROVEEDOR_NO_CORRESPONDE: 'productoId',
  RECURSO_NO_ENCONTRADO: 'productoId',
}

export function campoDeCostoParaCodigo(codigo: string): CampoCosto | null {
  return MAPA_CODIGO_A_CAMPO_COSTO[codigo] ?? null
}
