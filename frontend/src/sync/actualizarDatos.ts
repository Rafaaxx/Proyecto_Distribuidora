import { aplicarBootstrap } from './aplicarBootstrap'
import { pedirBootstrap } from './clienteBootstrap'

/**
 * "Actualizar datos" del inicio de `/ruta` (change 21, `design.md` D2, D3; SYN-11): pide un
 * bootstrap nuevo y lo aplica reemplazando los datos maestros. No toca nada de lo pendiente.
 * Si falla, la base local queda como estaba.
 */
export type ResultadoActualizacion = 'actualizados' | 'sin_jornada' | 'sesion_vencida' | 'sin_red' | 'error'

export async function actualizarDatos(): Promise<ResultadoActualizacion> {
  const r = await pedirBootstrap()
  switch (r.tipo) {
    case 'ok':
      await aplicarBootstrap(r.bootstrap)
      return 'actualizados'
    case 'jornada_requerida':
      return 'sin_jornada'
    case 'sin_sesion':
      return 'sesion_vencida'
    case 'sin_red':
      return 'sin_red'
    case 'error':
      return 'error'
  }
}
