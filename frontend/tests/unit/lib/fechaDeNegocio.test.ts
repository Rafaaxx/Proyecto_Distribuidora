import { describe, expect, it } from 'vitest'

import { formatearFechaDeNegocio } from '../../../src/lib/fecha'

describe('formatearFechaDeNegocio (TR-04: fecha sin hora ni zona)', () => {
  it.each([
    ['2026-05-10', '10/05/2026'],
    ['2026-12-01', '01/12/2026'],
  ])('%s -> %s sin pasar por Date (no hay corrimiento de zona)', (entrada, esperado) => {
    expect(formatearFechaDeNegocio(entrada)).toBe(esperado)
  })

  it('devuelve el texto tal cual si no es aaaa-mm-dd', () => {
    expect(formatearFechaDeNegocio('mañana')).toBe('mañana')
  })
})
