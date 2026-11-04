import type { EstadoDeJornadaNoAbierta } from '../../sync/estadoDeJornada'

/**
 * Avisos de la jornada que ya no está abierta (change 22d, `design.md` D9, aprobados en 0.2;
 * RUT-05, RUT-09). El aviso dice el estado, y siempre sigue que lo ya vendido se envía.
 */
const TEXTOS: Readonly<Record<EstadoDeJornadaNoAbierta, string>> = {
  LIBERADA: 'Tu jornada fue liberada.',
  EN_RENDICION: 'Tu jornada está en rendición.',
  CERRADA: 'Tu jornada fue cerrada.',
  DESCONOCIDO: 'Tu jornada ya no está abierta.',
}

export const AVISO_LO_YA_VENDIDO = 'Lo que ya vendiste y cobraste se sigue enviando.'

export function textoDeJornadaNoAbierta(estado: EstadoDeJornadaNoAbierta): string {
  return TEXTOS[estado]
}
