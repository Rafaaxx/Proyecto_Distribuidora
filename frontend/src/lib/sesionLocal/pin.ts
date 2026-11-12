import { baseLocal } from '../dispositivo/db'
import { derivarPin, verificarPin } from './derivacion'

/**
 * PIN de desbloqueo de la sesión local (change 21, `design.md` D13, D15; SEG-03, SEG-04, ADR-011,
 * ADR-055). El PIN NUNCA se guarda en claro ni se envía al servidor: solo se guarda su derivación
 * PBKDF2-SHA256 con sal aleatoria de 32 bytes, junto con la sal y las iteraciones, en `meta`.
 * Los fallos se cuentan en la base local (sobreviven a una recarga). Al llegar a
 * `INTENTOS_DESBLOQUEO_MAX` (10, constante en código, como el tope de ADR-055) se borra la
 * derivación y se exige iniciar sesión con conexión; los datos maestros y las operaciones
 * pendientes no se tocan. El parámetro `intentos_pin_max` de la organización ya no aplica acá:
 * rige solo para los fallos contra el PIN de un supervisor (en línea; aprobado 2026-10-30).
 */
export const ITERACIONES_PIN = 600_000
export const LARGO_SAL_BYTES = 32
/** Fallos del PIN de desbloqueo antes de exigir el login (constante fija; ADR-062 punto 15). */
export const INTENTOS_DESBLOQUEO_MAX = 10

const CLAVE_HASH = 'pin_hash'
const CLAVE_SAL = 'pin_sal'
const CLAVE_ITERACIONES = 'pin_iteraciones'
const CLAVE_INTENTOS = 'pin_intentos'

/** Claves de `meta` que componen la derivación del PIN y su cuenta de fallos. */
export const CLAVES_DE_PIN = [CLAVE_HASH, CLAVE_SAL, CLAVE_ITERACIONES, CLAVE_INTENTOS] as const

export type ResultadoValidacion = { ok: true } | { ok: false; motivo: string }

export type ResultadoDesbloqueo =
  | { tipo: 'ok' }
  | { tipo: 'incorrecto'; restantes: number }
  | { tipo: 'bloqueado' }
  | { tipo: 'sin_pin' }

export type ResultadoCambio =
  | { tipo: 'ok' }
  | { tipo: 'invalido'; motivo: string }
  | { tipo: 'incorrecto'; restantes: number }
  | { tipo: 'bloqueado' }
  | { tipo: 'sin_pin' }

const SEIS_DIGITOS = /^\d{6}$/

function esEscalera(pin: string): boolean {
  const pasos = new Set<number>()
  for (let i = 1; i < pin.length; i += 1) {
    pasos.add(Number(pin[i]) - Number(pin[i - 1]))
  }
  return pasos.size === 1 && (pasos.has(1) || pasos.has(-1))
}

/** Reglas del PIN nuevo (D13): 6 dígitos exactos, dos veces iguales, no trivial (ADR-055). */
export function validarPinNuevo(pin: string, confirmacion: string): ResultadoValidacion {
  if (!SEIS_DIGITOS.test(pin)) {
    return { ok: false, motivo: 'El PIN debe tener exactamente 6 dígitos.' }
  }
  if (pin !== confirmacion) {
    return { ok: false, motivo: 'Los dos PIN no coinciden.' }
  }
  if (new Set(pin).size === 1) {
    return { ok: false, motivo: 'El PIN no puede tener todos los dígitos iguales.' }
  }
  if (esEscalera(pin)) {
    return { ok: false, motivo: 'El PIN no puede tener dígitos seguidos (123456 o 654321).' }
  }
  return { ok: true }
}

function sal32Bytes(): string {
  const bytes = globalThis.crypto.getRandomValues(new Uint8Array(LARGO_SAL_BYTES))
  return Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('')
}

async function leer(clave: string): Promise<string | undefined> {
  return (await baseLocal.meta.get(clave))?.valor
}

async function guardarDerivacion(pin: string): Promise<void> {
  const sal = sal32Bytes()
  const hash = await derivarPin(pin, sal, ITERACIONES_PIN)
  await baseLocal.meta.bulkPut([
    { clave: CLAVE_HASH, valor: hash },
    { clave: CLAVE_SAL, valor: sal },
    { clave: CLAVE_ITERACIONES, valor: String(ITERACIONES_PIN) },
    { clave: CLAVE_INTENTOS, valor: '0' },
  ])
}

/** Borra la derivación y la cuenta de fallos (no toca datos maestros ni operaciones). */
export async function borrarDerivacionDePin(): Promise<void> {
  await baseLocal.meta.bulkDelete([...CLAVES_DE_PIN])
}

export async function hayPinDefinido(): Promise<boolean> {
  return (await leer(CLAVE_HASH)) !== undefined
}

export async function intentosFallidos(): Promise<number> {
  return Number((await leer(CLAVE_INTENTOS)) ?? '0')
}

/** Define el PIN (con conexión, tras el login). Si no es válido no guarda nada. */
export async function definirPin(pin: string, confirmacion: string): Promise<ResultadoValidacion> {
  const validacion = validarPinNuevo(pin, confirmacion)
  if (!validacion.ok) return validacion
  await guardarDerivacion(pin)
  return { ok: true }
}

type ResultadoComprobacion = { tipo: 'correcto' } | Exclude<ResultadoDesbloqueo, { tipo: 'ok' }>

/** Compara el PIN con la derivación guardada y lleva la cuenta de fallos (D15). */
async function comprobarPin(pin: string): Promise<ResultadoComprobacion> {
  const [hash, sal, iteraciones] = await Promise.all([leer(CLAVE_HASH), leer(CLAVE_SAL), leer(CLAVE_ITERACIONES)])
  if (hash === undefined || sal === undefined || iteraciones === undefined) {
    return { tipo: 'sin_pin' }
  }

  if (await verificarPin(pin, sal, Number(iteraciones), hash)) {
    await baseLocal.meta.put({ clave: CLAVE_INTENTOS, valor: '0' })
    return { tipo: 'correcto' }
  }

  const fallos = (await intentosFallidos()) + 1
  const maximo = INTENTOS_DESBLOQUEO_MAX
  if (fallos >= maximo) {
    await borrarDerivacionDePin()
    return { tipo: 'bloqueado' }
  }
  await baseLocal.meta.put({ clave: CLAVE_INTENTOS, valor: String(fallos) })
  return { tipo: 'incorrecto', restantes: maximo - fallos }
}

/** Desbloquea la sesión local con el PIN (con o sin conexión). */
export async function desbloquearConPin(pin: string): Promise<ResultadoDesbloqueo> {
  const r = await comprobarPin(pin)
  return r.tipo === 'correcto' ? { tipo: 'ok' } : r
}

/** Cambia el PIN con el actual y el nuevo dos veces; un actual incorrecto cuenta como fallo. */
export async function cambiarPin(actual: string, nuevo: string, confirmacion: string): Promise<ResultadoCambio> {
  const validacion = validarPinNuevo(nuevo, confirmacion)
  if (!validacion.ok) return { tipo: 'invalido', motivo: validacion.motivo }

  const r = await comprobarPin(actual)
  if (r.tipo !== 'correcto') return r

  await guardarDerivacion(nuevo)
  return { tipo: 'ok' }
}
