/**
 * Mapea el `codigo` de un `ErrorDeCatalogo` (tarea 10.2) al campo del
 * formulario de producto donde se muestra, para que la tarea 10.5 pueda
 * usar `setError(campo, { message })` de React Hook Form en vez de un
 * cartel genérico (`tasks.md` 10.5: "errores de dominio mostrados junto al
 * campo"). `null` cuando el error no corresponde a un campo puntual del
 * formulario de producto (se muestra entonces como mensaje general).
 */
export type CampoProducto =
  | 'codigo'
  | 'nombre'
  | 'categoriaId'
  | 'marcaId'
  | 'proveedorId'
  | 'alicuotaId'
  | 'presentaciones'

const MAPA_CODIGO_A_CAMPO: Record<string, CampoProducto> = {
  CODIGO_INVALIDO: 'codigo',
  CODIGO_DUPLICADO: 'codigo',
  NOMBRE_INVALIDO: 'nombre',
  CATEGORIA_INACTIVA: 'categoriaId',
  MARCA_INACTIVA: 'marcaId',
  // Change 06 (D9, ADR-025, tarea 11.6): proveedor inexistente, inactivo o
  // ajeno -- mismo código que usa `proveedores` (`PROVEEDOR_INACTIVO`).
  PROVEEDOR_INACTIVO: 'proveedorId',
  ALICUOTA_INACTIVA: 'alicuotaId',
  PRODUCTO_SIN_PRESENTACIONES: 'presentaciones',
  REFERENCIA_INVALIDA: 'presentaciones',
  UNIDADES_INVALIDAS: 'presentaciones',
}

export function campoDeProductoParaCodigo(codigo: string): CampoProducto | null {
  return MAPA_CODIGO_A_CAMPO[codigo] ?? null
}
