import { baseLocal, type AutorizadorLocal, type IntentoPinLocal } from '../dispositivo/db'
import { compararEnTiempoConstante, derivarPin } from './derivacion'

/**
 * Verificación local del PIN de un supervisor (change 22a, `design.md` D10 = B; spec
 * `identidad/pin-de-autorizacion`; SEG-05, ADR-055, `02` §12.4; gobernanza ALTA).
 *
 * - El PIN se deriva con PBKDF2-SHA256 (la misma función que el desbloqueo, change 21) con la sal
 *   y las iteraciones del autorizador del bootstrap y se compara en tiempo constante con la
 *   derivación del bootstrap. El PIN no se guarda ni se envía: la venta lleva solo `autorizador_id`.
 * - El permiso del autorizador se revisa ANTES del PIN: sin el permiso no se ofrece, no se
 *   verifica y no cuenta fallos.
 * - Los fallos se cuentan en `intentos_pin` por par (usuario local, autorizador). Con
 *   `intentos_pin_max` fallos (5 por defecto) el PIN queda bloqueado en este teléfono hasta el
 *   próximo bootstrap, NO por tiempo: el estado no guarda ni compara horas (el reloj del teléfono
 *   se puede adelantar). Un intento durante el bloqueo no verifica ni cuenta; un acierto no
 *   reinicia la cuenta. `aplicarBootstrap` vacía `intentos_pin` (cualquier bootstrap nuevo).
 */
export const INTENTOS_PIN_MAX_POR_DEFECTO = 5

export type ResultadoPinSupervisor =
  | { tipo: 'ok'; autorizadorId: string }
  | { tipo: 'incorrecto'; restantes: number }
  | { tipo: 'bloqueado' }
  /** Autorizador ausente del bootstrap o sin el permiso: no se ofrece y no cuenta. */
  | { tipo: 'sin_permiso' }

export interface SolicitudDePinSupervisor {
  usuarioId: string
  autorizadorId: string
  /** Permiso que el autorizador debe tener para lo que autoriza (`AUTORIZAR_DESCUENTO`, `SUPERAR_CREDITO`). */
  permisoRequerido: string
  pin: string
}

/** Autorizadores del bootstrap que tienen el permiso (los únicos que se ofrecen). */
export async function autorizadoresConPermiso(permiso: string): Promise<AutorizadorLocal[]> {
  const todos = await baseLocal.autorizadores.toArray()
  return todos.filter((a) => a.permisos.includes(permiso))
}

async function maximoDeIntentos(): Promise<number> {
  const maximo = (await baseLocal.configuracion.get('organizacion'))?.intentos_pin_max
  return typeof maximo === 'number' && maximo > 0 ? maximo : INTENTOS_PIN_MAX_POR_DEFECTO
}

/** Estado del par; una fila contada contra otra derivación se considera nueva (nunca bloquea). */
function estadoVigente(fila: IntentoPinLocal | undefined, derivacion: string): { fallos: number; bloqueado: boolean } {
  if (fila === undefined || fila.derivacion !== derivacion) return { fallos: 0, bloqueado: false }
  return { fallos: fila.fallos, bloqueado: fila.bloqueado }
}

/** Serializa los intentos para que dos toques simultáneos no esquiven el límite. */
let cola: Promise<unknown> = Promise.resolve()

function enSerie<T>(tarea: () => Promise<T>): Promise<T> {
  const siguiente = cola.then(tarea, tarea)
  cola = siguiente.catch(() => undefined)
  return siguiente
}

async function verificar(solicitud: SolicitudDePinSupervisor): Promise<ResultadoPinSupervisor> {
  const { usuarioId, autorizadorId, permisoRequerido, pin } = solicitud
  const autorizador = await baseLocal.autorizadores.get(autorizadorId)
  if (autorizador === undefined || !autorizador.permisos.includes(permisoRequerido)) {
    return { tipo: 'sin_permiso' }
  }

  const clave: [string, string] = [usuarioId, autorizadorId]
  const previo = estadoVigente(await baseLocal.intentos_pin.get(clave), autorizador.pin_hash)
  if (previo.bloqueado) return { tipo: 'bloqueado' }

  const derivado = await derivarPin(pin, autorizador.pin_sal, autorizador.iteraciones)
  if (compararEnTiempoConstante(derivado, autorizador.pin_hash)) {
    return { tipo: 'ok', autorizadorId }
  }

  const maximo = await maximoDeIntentos()
  const fallos = previo.fallos + 1
  const bloqueado = fallos >= maximo
  await baseLocal.intentos_pin.put({
    usuario_id: usuarioId,
    autorizador_id: autorizadorId,
    fallos,
    derivacion: autorizador.pin_hash,
    bloqueado,
  })
  return bloqueado ? { tipo: 'bloqueado' } : { tipo: 'incorrecto', restantes: maximo - fallos }
}

/** Verifica el PIN de un supervisor en el teléfono (sin señal, sin enviarlo). */
export function verificarPinDeSupervisor(solicitud: SolicitudDePinSupervisor): Promise<ResultadoPinSupervisor> {
  return enSerie(() => verificar(solicitud))
}
