import { describe, expect, it } from 'vitest'

import {
  TEXTO_SIN_PERMISO_DE_REVISION,
  hayRechazosPendientes,
  textoDeRechazosPendientes,
} from '../../../../src/domain/stock/rendicion'

/**
 * Change 25, tarea 15.3 (D9 = B, D12; RUT-05): el aviso de las operaciones rechazadas sin resolver que
 * impiden rendir una jornada.
 */
describe('rechazos pendientes de la jornada (RUT-05, D9 = B)', () => {
  it('«Esta jornada tiene {N} operaciones rechazadas sin resolver. Hay que resolverlas antes de rendir.»', () => {
    expect(textoDeRechazosPendientes(3)).toBe(
      'Esta jornada tiene 3 operaciones rechazadas sin resolver. Hay que resolverlas antes de rendir.',
    )
    expect(textoDeRechazosPendientes(12)).toBe(
      'Esta jornada tiene 12 operaciones rechazadas sin resolver. Hay que resolverlas antes de rendir.',
    )
  })

  it('con una sola dice «1 operación rechazada»', () => {
    expect(textoDeRechazosPendientes(1)).toBe(
      'Esta jornada tiene 1 operación rechazada sin resolver. Hay que resolverlas antes de rendir.',
    )
  })

  it('sin permiso de revisión: «Las resuelve quien revisa las observaciones.»', () => {
    expect(TEXTO_SIN_PERMISO_DE_REVISION).toBe('Las resuelve quien revisa las observaciones.')
  })

  it('hay rechazos pendientes solo con una cantidad positiva; un dato ausente cuenta como ninguno', () => {
    expect(hayRechazosPendientes(2)).toBe(true)
    expect(hayRechazosPendientes(0)).toBe(false)
    expect(hayRechazosPendientes(undefined)).toBe(false)
  })
})
