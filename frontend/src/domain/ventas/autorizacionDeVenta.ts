/**
 * Autorizaciones de la pantalla de venta (change 18b, tarea 13.1; DSC-06, CRE-05, SEG-05;
 * `design.md` D2, D4, D20): qué autorizaciones hacen falta, quién puede darlas y con qué
 * credenciales. Una sola credencial por persona aunque autorice las dos cosas (D4). El PIN no se
 * guarda en ningún lado: estas funciones solo lo reciben y lo devuelven, y la pantalla lo borra de
 * la memoria al enviar o cancelar.
 */

import type { DecisionDeCredito } from './creditoDeVenta'
import type { NecesidadDeDescuento } from './descuentosDeVenta'

export type TipoDeAutorizacion = 'DESCUENTO' | 'CREDITO'

/** Un autorizador de `GET /ventas/contexto`: nunca trae la derivación del PIN. */
export interface AutorizadorDeContexto {
  id: string
  nombre: string
  puedeAutorizarDescuento: boolean
  puedeSuperarCredito: boolean
}

export type SeleccionDeAutorizadores = Partial<Record<TipoDeAutorizacion, string>>

/** Las autorizaciones que otra persona tiene que dar (con permiso propio no hace falta nada). */
export function autorizacionesNecesarias(
  descuento: NecesidadDeDescuento,
  credito: DecisionDeCredito,
): TipoDeAutorizacion[] {
  const necesarias: TipoDeAutorizacion[] = []
  if (descuento.estado === 'requiere-autorizador') necesarias.push('DESCUENTO')
  if (credito === 'pide-autorizador') necesarias.push('CREDITO')
  return necesarias
}

/** Quién puede dar cada autorización (el permiso que corresponde). */
export function autorizadoresPara(
  tipo: TipoDeAutorizacion,
  autorizadores: readonly AutorizadorDeContexto[],
): AutorizadorDeContexto[] {
  return autorizadores.filter((a) => (tipo === 'DESCUENTO' ? a.puedeAutorizarDescuento : a.puedeSuperarCredito))
}

/** Las personas que tienen que escribir su PIN, sin repetir (D4), en el orden de las autorizaciones. */
export function personasQueDebenPonerPin(
  necesarias: readonly TipoDeAutorizacion[],
  seleccion: SeleccionDeAutorizadores,
): string[] {
  const personas: string[] = []
  for (const tipo of necesarias) {
    const id = seleccion[tipo]
    if (id !== undefined && id !== '' && !personas.includes(id)) personas.push(id)
  }
  return personas
}

/** Ayuda local: al menos 6 caracteres, solo dígitos ASCII. El servidor valida igual (TR-10). */
export function formatoDePinValido(pin: string): boolean {
  return /^[0-9]{6,}$/.test(pin)
}

/** Falta el PIN (o no tiene el formato) de alguna de las personas que lo deben poner. */
export function faltaAlgunPin(personas: readonly string[], pins: Readonly<Record<string, string>>): boolean {
  return personas.some((id) => !formatoDePinValido(pins[id] ?? ''))
}

export interface CredencialDePin {
  autorizador_id: string
  pin: string
}

/** Una credencial por persona que debe poner el PIN; los demás PIN escritos no viajan. */
export function armarCredenciales(
  personas: readonly string[],
  pins: Readonly<Record<string, string>>,
): CredencialDePin[] {
  return personas.map((id) => ({ autorizador_id: id, pin: pins[id] ?? '' }))
}

/**
 * Quién autoriza cada cosa al abrir el diálogo: se conserva lo ya elegido si sigue siendo válido;
 * si no, la misma persona que ya autoriza la otra cosa (así el PIN se pide una sola vez, D4) y,
 * si no, la única que puede. Lo que quede ambiguo lo elige el usuario.
 */
export function completarSeleccion(
  necesarias: readonly TipoDeAutorizacion[],
  autorizadores: readonly AutorizadorDeContexto[],
  actual: SeleccionDeAutorizadores,
): SeleccionDeAutorizadores {
  const resultado: SeleccionDeAutorizadores = {}
  for (const tipo of necesarias) {
    const posibles = autorizadoresPara(tipo, autorizadores)
    const previo = actual[tipo]
    if (previo !== undefined && posibles.some((a) => a.id === previo)) {
      resultado[tipo] = previo
      continue
    }
    const yaElegido = Object.values(resultado).find((id) => posibles.some((a) => a.id === id))
    if (yaElegido !== undefined) {
      resultado[tipo] = yaElegido
      continue
    }
    const unico = posibles.length === 1 ? posibles[0] : undefined
    if (unico !== undefined) resultado[tipo] = unico.id
  }
  return resultado
}
