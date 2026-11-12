/**
 * Mapea el `codigo` de un error de la API de descuentos al campo del formulario donde se muestra
 * (TR-10), mismo criterio que `features/precios/mapaErrorACampo.ts`. `null` cuando el error no
 * corresponde a un campo puntual (se muestra como mensaje general).
 */

export type CampoReglaDescuento =
  | 'nombre'
  | 'umbral'
  | 'accion_valor'
  | 'prioridad'
  | 'alcances'
  | 'vigencia_hasta'

const MAPA_REGLA: Record<string, CampoReglaDescuento> = {
  NOMBRE_INVALIDO: 'nombre',
  UMBRAL_INVALIDO: 'umbral',
  ACCION_INVALIDA: 'accion_valor',
  PRIORIDAD_INVALIDA: 'prioridad',
  ALCANCE_INVALIDO: 'alcances',
  VIGENCIA_INVALIDA: 'vigencia_hasta',
}

export function campoDeReglaDeDescuentoParaCodigo(codigo: string): CampoReglaDescuento | null {
  return MAPA_REGLA[codigo] ?? null
}

export type CampoTope = 'tope_descuento'

export function campoDeTopeParaCodigo(codigo: string): CampoTope | null {
  return codigo === 'IDENTIDAD_TOPE_DESCUENTO_FUERA_DE_RANGO' ? 'tope_descuento' : null
}

const MENSAJE_ESTADO_CAMBIADO =
  'La regla cambió de estado mientras mirabas la pantalla. Se muestra el estado actual.'
const MENSAJE_YA_NO_ES_BORRADOR =
  'La regla ya no es un borrador, por eso no se puede editar. Pausala y creá otra, o poné fin a su vigencia.'

/** El mensaje que ve la persona: propio para los dos rechazos de estado, el del servidor en el resto. */
export function mensajeDeErrorDeDescuentos(codigo: string | null, mensajeDelServidor: string): string {
  if (codigo === 'REGLA_ESTADO_INVALIDO') return MENSAJE_ESTADO_CAMBIADO
  if (codigo === 'REGLA_NO_ES_BORRADOR') return MENSAJE_YA_NO_ES_BORRADOR
  return mensajeDelServidor
}
