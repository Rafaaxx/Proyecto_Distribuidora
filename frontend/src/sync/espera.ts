/**
 * Espera exponencial entre reintentos tras un corte transitorio (change 22b, `design.md` D5;
 * SYN-03, `02` §13.3). Funciones puras: el reloj y el azar los inyecta quien llama. El estado
 * (`fallos`, `hasta`) lo guarda el ciclo en memoria de la pestaña.
 *
 * Se vuelve a cero (`reiniciarEspera`) tras un éxito y con los disparadores que prueban en el
 * momento: «Sincronizar», `online` y la vuelta a primer plano (D6 = B, decisión del usuario).
 */
const ESPERAS_BASE_MS = [5_000, 10_000, 20_000, 40_000, 80_000, 120_000]
const VARIACION = 0.2

export interface EstadoDeEspera {
  fallos: number
  /** Momento (ms) hasta el que no se reintenta solo; `null` sin espera. */
  hasta: number | null
}

export const ESPERA_INICIAL: EstadoDeEspera = { fallos: 0, hasta: null }

/** Espera en ms tras `fallosConsecutivos` (1 = primer fallo); `azar` devuelve [0, 1]. */
export function esperaDeReintento(fallosConsecutivos: number, azar: () => number): number {
  const indice = Math.min(Math.max(fallosConsecutivos, 1), ESPERAS_BASE_MS.length) - 1
  const base = ESPERAS_BASE_MS[indice] ?? 120_000
  return Math.round(base * (1 + (azar() * 2 - 1) * VARIACION))
}

export function registrarFallo(estado: EstadoDeEspera, ahoraMs: number, azar: () => number): EstadoDeEspera {
  const fallos = estado.fallos + 1
  return { fallos, hasta: ahoraMs + esperaDeReintento(fallos, azar) }
}

export function reiniciarEspera(): EstadoDeEspera {
  return ESPERA_INICIAL
}

export function debeEsperar(estado: EstadoDeEspera, ahoraMs: number): boolean {
  return estado.hasta !== null && ahoraMs < estado.hasta
}
