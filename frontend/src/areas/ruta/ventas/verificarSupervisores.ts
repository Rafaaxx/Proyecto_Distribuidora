import { verificarPinDeSupervisor, type ResultadoPinSupervisor } from '../../../lib/sesionLocal/pinSupervisor'

/**
 * Verifica en el teléfono el PIN de cada supervisor que autoriza la venta (change 22a,
 * `design.md` D10; SEG-05, ADR-055). Una credencial por persona. El PIN pasa por acá solo hasta
 * la verificación: no se guarda ni se devuelve. Se detiene en el primer fallo.
 */
export interface PersonaQueAutoriza {
  id: string
  nombre: string
  /** Permiso que debe tener para lo que autoriza (`AUTORIZAR_DESCUENTO`, `SUPERAR_CREDITO`). */
  permiso: string
}

export type ResultadoDeVerificacion = { tipo: 'ok'; verificados: string[] } | { tipo: 'error'; mensaje: string }

export function mensajeDeFallo(resultado: Exclude<ResultadoPinSupervisor, { tipo: 'ok' }>, nombre: string): string {
  switch (resultado.tipo) {
    case 'incorrecto':
      return resultado.restantes === 1
        ? 'PIN incorrecto. Te queda 1 intento.'
        : `PIN incorrecto. Te quedan ${resultado.restantes} intentos.`
    case 'bloqueado':
      return `El PIN de ${nombre} está bloqueado en este teléfono hasta que actualices los datos.`
    case 'sin_permiso':
      return `${nombre} no tiene el permiso para autorizar esto.`
  }
}

export async function verificarSupervisores(
  usuarioId: string,
  personas: readonly PersonaQueAutoriza[],
  pins: Readonly<Record<string, string>>,
): Promise<ResultadoDeVerificacion> {
  const verificados: string[] = []
  for (const persona of personas) {
    const resultado = await verificarPinDeSupervisor({
      usuarioId,
      autorizadorId: persona.id,
      permisoRequerido: persona.permiso,
      pin: pins[persona.id] ?? '',
    })
    if (resultado.tipo !== 'ok') return { tipo: 'error', mensaje: mensajeDeFallo(resultado, persona.nombre) }
    verificados.push(resultado.autorizadorId)
  }
  return { tipo: 'ok', verificados }
}
