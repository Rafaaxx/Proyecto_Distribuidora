import { describe, expect, it } from 'vitest'

import { formatearFechaHora, formatearFechaHoraEnZona } from '../../../src/lib/fecha'

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

/**
 * Change 08, tarea 7.3 (TR-04): el estado de cuenta muestra cada movimiento en
 * la zona horaria de la ORGANIZACIÓN, no en la del navegador. A diferencia de
 * `formatearFechaHora`, el resultado no depende de dónde corra la prueba.
 */
describe('formatearFechaHoraEnZona', () => {
  it('muestra la hora de la zona de la organización (Mendoza, UTC-3)', () => {
    expect(formatearFechaHoraEnZona('2026-03-10T15:00:00Z', 'America/Argentina/Mendoza')).toBe('10/03/2026 12:00')
  })

  it('cruza el día cuando la zona lo exige', () => {
    expect(formatearFechaHoraEnZona('2026-03-10T15:00:00Z', 'Asia/Tokyo')).toBe('11/03/2026 00:00')
    expect(formatearFechaHoraEnZona('2026-03-10T02:30:00Z', 'America/Argentina/Mendoza')).toBe('09/03/2026 23:30')
  })
})
