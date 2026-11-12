import { describe, expect, it } from 'vitest'

import {
  debeEsperar,
  ESPERA_INICIAL,
  esperaDeReintento,
  registrarFallo,
  reiniciarEspera,
} from '../../../src/sync/espera'

/**
 * Change 22b, tarea 2.2 (`design.md` D5; cita SYN-03, `02` §13.3): espera exponencial de
 * 5, 10, 20, 40, 80 y 120 s fijos después, con ±20 % de azar inyectable.
 */
const SIN_AZAR = () => 0.5 // factor exacto 1,0

describe('espera exponencial (tarea 2.2)', () => {
  it('base 5, 10, 20, 40, 80 y luego 120 s fijos', () => {
    const esperas = [1, 2, 3, 4, 5, 6, 7, 20].map((fallos) => esperaDeReintento(fallos, SIN_AZAR))

    expect(esperas).toEqual([5000, 10000, 20000, 40000, 80000, 120000, 120000, 120000])
  })

  it('el azar mueve el valor entre -20 % y +20 %', () => {
    expect(esperaDeReintento(1, () => 0)).toBe(4000)
    expect(esperaDeReintento(1, () => 1)).toBe(6000)
    expect(esperaDeReintento(6, () => 0)).toBe(96000)
    expect(esperaDeReintento(6, () => 1)).toBe(144000)
  })

  it('cada fallo consecutivo sube la espera y fija el momento hasta el que se espera', () => {
    const primero = registrarFallo(ESPERA_INICIAL, 1_000, SIN_AZAR)
    const segundo = registrarFallo(primero, 7_000, SIN_AZAR)

    expect(primero).toEqual({ fallos: 1, hasta: 6_000 })
    expect(segundo).toEqual({ fallos: 2, hasta: 17_000 })
  })

  it('debeEsperar es verdadero solo antes de que venza la espera', () => {
    const estado = registrarFallo(ESPERA_INICIAL, 0, SIN_AZAR)

    expect(debeEsperar(estado, 4_999)).toBe(true)
    expect(debeEsperar(estado, 5_000)).toBe(false)
    expect(debeEsperar(ESPERA_INICIAL, 0)).toBe(false)
  })

  it('reiniciarEspera (éxito, «Sincronizar», online, primer plano) vuelve a cero', () => {
    const estado = registrarFallo(registrarFallo(ESPERA_INICIAL, 0, SIN_AZAR), 10_000, SIN_AZAR)

    expect(reiniciarEspera()).toEqual(ESPERA_INICIAL)
    expect(debeEsperar(reiniciarEspera(), 10_001)).toBe(false)
    expect(registrarFallo(reiniciarEspera(), 0, SIN_AZAR).fallos).toBe(1)
    expect(estado.fallos).toBe(2)
  })
})
