import { describe, expect, it } from 'vitest'

import {
  CODIGO_DE_EXCESO_AL_SINCRONIZAR,
  contadorDelMenu,
  lineasDeAviso,
} from '../../../../src/domain/revision/aviso'

const resumen = (campos: Partial<Record<string, unknown>> = {}) => ({
  observaciones_por_codigo: {} as Record<string, number>,
  observaciones_pendientes: 0,
  rechazos_pendientes: 0,
  cuarentenas_pendientes: 0,
  total_pendiente: 0,
  ...campos,
})

/** Change 25, tarea 15.1 (D5, D12; CRE-09): lo que dice el aviso de lo pendiente. */
describe('aviso de lo pendiente (CRE-09)', () => {
  it('no hay contador sin pendientes', () => {
    expect(contadorDelMenu(resumen())).toBeNull()
    expect(contadorDelMenu(undefined)).toBeNull()
    expect(contadorDelMenu(resumen({ total_pendiente: 7 }))).toBe(7)
  })

  it('las líneas separan los avisos, las rechazadas y los excesos', () => {
    const lineas = lineasDeAviso(
      resumen({
        observaciones_por_codigo: { [CODIGO_DE_EXCESO_AL_SINCRONIZAR]: 2 },
        observaciones_pendientes: 5,
        rechazos_pendientes: 1,
        cuarentenas_pendientes: 2,
        total_pendiente: 8,
      }),
    )

    expect(lineas).toEqual({
      avisos: { texto: '5 avisos pendientes', cantidad: 5 },
      rechazadas: { texto: '3 operaciones rechazadas sin resolver', cantidad: 3 },
      excesos: { texto: '2 excesos de crédito detectados al sincronizar', cantidad: 2 },
    })
  })

  it('usa el singular de uno y omite lo que está en cero', () => {
    const lineas = lineasDeAviso(
      resumen({
        observaciones_por_codigo: { [CODIGO_DE_EXCESO_AL_SINCRONIZAR]: 1 },
        observaciones_pendientes: 1,
        rechazos_pendientes: 1,
        total_pendiente: 2,
      }),
    )

    expect(lineas.avisos?.texto).toBe('1 aviso pendiente')
    expect(lineas.rechazadas?.texto).toBe('1 operación rechazada sin resolver')
    expect(lineas.excesos?.texto).toBe('1 exceso de crédito detectado al sincronizar')
    expect(lineasDeAviso(resumen())).toEqual({ avisos: null, rechazadas: null, excesos: null })
  })
})
