import { describe, expect, it } from 'vitest'

import { formatearFechaHora } from '../../../src/lib/fecha'

/**
 * Change 06, tarea 14.5 (corrección de la verificación manual 13.5):
 * `CostosHistorialScreen.tsx` necesita mostrar el momento de registro
 * (`creado_en`) como fecha y hora local, `dd/mm/aaaa hh:mm`. Las fechas de
 * prueba se construyen a partir de sus componentes locales (no de una
 * cadena UTC fija) para que la prueba no dependa de la zona horaria de
 * quien la corre: `formatearFechaHora` vuelve a leer esos mismos
 * componentes locales al formatear.
 */
describe('formatearFechaHora', () => {
  it('formatea con día, mes y año con dos dígitos y ceros a la izquierda en hora y minutos', () => {
    const momento = new Date(2026, 8, 10, 8, 5) // 10/09/2026 08:05 (mes 0-based)
    expect(formatearFechaHora(momento.toISOString())).toBe('10/09/2026 08:05')
  })

  it('un mes y día de dos dígitos y una hora de la tarde se muestran igual', () => {
    const momento = new Date(2026, 11, 25, 23, 59)
    expect(formatearFechaHora(momento.toISOString())).toBe('25/12/2026 23:59')
  })
})
