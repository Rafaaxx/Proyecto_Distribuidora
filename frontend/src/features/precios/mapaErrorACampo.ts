/**
 * Mapea el `codigo` de un `ErrorDePrecios` al campo del formulario donde se muestra
 * (TR-10), mismo criterio que `features/clientes/mapaErrorACampo.ts`. `null` cuando el
 * error no corresponde a un campo puntual (se muestra como mensaje general).
 */

export type CampoLista = 'nombre' | 'redondeo_multiplo' | 'activo'

const MAPA_LISTA: Record<string, CampoLista> = {
  NOMBRE_INVALIDO: 'nombre',
  NOMBRE_DUPLICADO: 'nombre',
  REDONDEO_INVALIDO: 'redondeo_multiplo',
  LISTA_EN_USO: 'activo',
}

export function campoDeListaParaCodigo(codigo: string): CampoLista | null {
  return MAPA_LISTA[codigo] ?? null
}

/** `alcance` junta el tipo y la entidad: el error se muestra junto al selector de alcance. */
export type CampoRegla = 'porcentaje' | 'alcance'

const MAPA_REGLA: Record<string, CampoRegla> = {
  MARGEN_INVALIDO: 'porcentaje',
  ALCANCE_INVALIDO: 'alcance',
  REGLA_DUPLICADA: 'alcance',
}

export function campoDeReglaParaCodigo(codigo: string): CampoRegla | null {
  return MAPA_REGLA[codigo] ?? null
}

export type CampoPublicacion = 'vigencia_desde' | 'vigencia_hasta'

const MAPA_PUBLICACION: Record<string, CampoPublicacion> = {
  VIGENCIA_INVALIDA: 'vigencia_desde',
  VIGENCIA_DUPLICADA: 'vigencia_desde',
}

export function campoDePublicacionParaCodigo(codigo: string): CampoPublicacion | null {
  return MAPA_PUBLICACION[codigo] ?? null
}

export type CampoPrecio = 'precio_final'

const MAPA_PRECIO: Record<string, CampoPrecio> = {
  IMPORTE_INVALIDO: 'precio_final',
  PRECIO_NO_POSITIVO: 'precio_final',
}

export function campoDePrecioParaCodigo(codigo: string): CampoPrecio | null {
  return MAPA_PRECIO[codigo] ?? null
}
