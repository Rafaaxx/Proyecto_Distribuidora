import { describe, expect, it } from 'vitest'

import { aFiltros, esquemaPeriodo } from '../../../../src/domain/cuentas-corrientes/periodoSchema'

describe('esquemaPeriodo (tarea 7.3, D9)', () => {
  it.each([
    { desde: '', hasta: '' },
    { desde: '2026-04-01', hasta: '' },
    { desde: '', hasta: '2026-04-30' },
    { desde: '2026-04-01', hasta: '2026-04-01' },
    { desde: '2026-04-01', hasta: '2026-04-30' },
  ])('acepta el período %j', (periodo) => {
    expect(esquemaPeriodo.safeParse(periodo).success).toBe(true)
  })

  it('rechaza un desde posterior al hasta, con el mensaje en el campo hasta', () => {
    const resultado = esquemaPeriodo.safeParse({ desde: '2026-04-02', hasta: '2026-04-01' })
    expect(resultado.success).toBe(false)
    if (!resultado.success) {
      expect(resultado.error.issues[0]?.path).toEqual(['hasta'])
      expect(resultado.error.issues[0]?.message).toBe('"Desde" no puede ser posterior a "Hasta".')
    }
  })
})

describe('aFiltros', () => {
  it('descarta los campos vacíos y conserva los llenos', () => {
    expect(aFiltros({ desde: '', hasta: '' })).toEqual({})
    expect(aFiltros({ desde: '2026-04-01', hasta: '' })).toEqual({ desde: '2026-04-01' })
    expect(aFiltros({ desde: '', hasta: '2026-04-30' })).toEqual({ hasta: '2026-04-30' })
    expect(aFiltros({ desde: '2026-04-01', hasta: '2026-04-30' })).toEqual({
      desde: '2026-04-01',
      hasta: '2026-04-30',
    })
  })
})
