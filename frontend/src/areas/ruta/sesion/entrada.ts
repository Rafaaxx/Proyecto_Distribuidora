import { obtenerJornadaActual } from '../../../features/stock/api'
import { baseLocal } from '../../../lib/dispositivo/db'
import { aplicarBootstrap } from '../../../sync/aplicarBootstrap'
import { pedirBootstrap } from '../../../sync/clienteBootstrap'
import { marcarJornadaDeLaSesionNoAbierta, marcarJornadaNoAbierta } from '../../../sync/estadoDeJornada'

/**
 * Qué pasó con los datos al entrar con conexión (change 21, `design.md` D11; RUT-03).
 * - `al_dia`: la jornada abierta es la del bootstrap local; no se pidió nada.
 * - `bootstrap_aplicado`: había una jornada abierta propia nueva (o no había datos) y se bajó.
 * - `sin_jornada`: no hay jornada abierta propia; el inicio ofrece abrirla.
 * - `sin_red`: sin conexión o con un corte; se sigue con los datos locales.
 * - `sesion_vencida`: el servidor rechazó la sesión.
 * - `error`: el servidor falló; el inicio ofrece reintentar.
 */
export type ResultadoEntrada =
  | { tipo: 'al_dia' }
  | { tipo: 'bootstrap_aplicado' }
  | { tipo: 'sin_jornada' }
  | { tipo: 'sin_red' }
  | { tipo: 'sesion_vencida' }
  | { tipo: 'error' }

const ESTADO_JORNADA_ABIERTA = 'ABIERTA'

/**
 * Change 22d (D8): la consulta al entrar no encontró una jornada abierta propia. Si la jornada no
 * cerrada del servidor es la de la sesión local, se guarda su estado (por ejemplo `EN_RENDICION`);
 * si no hay ninguna, se guarda que la de la sesión ya no está abierta, sin estado conocido.
 */
async function marcarSinJornada(jornada: Awaited<ReturnType<typeof obtenerJornadaActual>>): Promise<void> {
  const ahora = new Date()
  if (jornada !== null && jornada.estado === 'EN_RENDICION') {
    await marcarJornadaNoAbierta(jornada.id, 'EN_RENDICION', ahora)
  }
  // Sin efecto si ya se conoce el estado; si la jornada del servidor es otra, la local ya no está abierta.
  await marcarJornadaDeLaSesionNoAbierta('DESCONOCIDO', ahora)
}

export async function sincronizarAlEntrar(): Promise<ResultadoEntrada> {
  if (!navigator.onLine) return { tipo: 'sin_red' }

  let jornada: Awaited<ReturnType<typeof obtenerJornadaActual>>
  try {
    jornada = await obtenerJornadaActual()
  } catch (e) {
    return e instanceof TypeError ? { tipo: 'sin_red' } : { tipo: 'error' }
  }

  if (jornada === null || jornada.estado !== ESTADO_JORNADA_ABIERTA) {
    await marcarSinJornada(jornada)
    return { tipo: 'sin_jornada' }
  }

  const [local, sesion] = await Promise.all([baseLocal.meta.get('jornada_id'), baseLocal.sesion.get('actual')])
  if (sesion !== undefined && local?.valor === jornada.id) return { tipo: 'al_dia' }

  const resultado = await pedirBootstrap()
  switch (resultado.tipo) {
    case 'ok':
      await aplicarBootstrap(resultado.bootstrap)
      return { tipo: 'bootstrap_aplicado' }
    case 'jornada_requerida':
      await marcarJornadaDeLaSesionNoAbierta('DESCONOCIDO', new Date())
      return { tipo: 'sin_jornada' }
    case 'sin_sesion':
      return { tipo: 'sesion_vencida' }
    case 'sin_red':
      return { tipo: 'sin_red' }
    case 'error':
      return { tipo: 'error' }
  }
}
