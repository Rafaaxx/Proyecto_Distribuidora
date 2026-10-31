import { describe, expect, it } from 'vitest'

import { siguienteNumeroLocal, siguienteSecuencia } from '../../../../src/domain/ruta/numeracionLocal'

/**
 * Change 22a, tarea 2.1 (spec `sync/cola-local`, "El número de la venta lo asigna el teléfono
 * al confirmar"; `design.md` D4; VTA-06, `02` §7.7).
 */
describe('número de la venta local (VTA-06)', () => {
  it('primera venta tras el bootstrap: V03-000142', () => {
    expect(
      siguienteNumeroLocal({ prefijo: 'V03', ultimoCorrelativoBootstrap: 141, ultimoCorrelativoLocal: null }),
    ).toEqual({ numero: 'V03-000142', correlativo: 142 })
  })

  it('el teléfono va adelante del servidor: V03-000146', () => {
    expect(
      siguienteNumeroLocal({ prefijo: 'V03', ultimoCorrelativoBootstrap: 141, ultimoCorrelativoLocal: 145 }),
    ).toEqual({ numero: 'V03-000146', correlativo: 146 })
  })

  it('carrito descartado: no consume número; tras V03-000142 sigue V03-000143', () => {
    // Descartar un carrito no toca el contador: el siguiente cálculo parte del mismo último usado.
    const dato = { prefijo: 'V03', ultimoCorrelativoBootstrap: 141, ultimoCorrelativoLocal: 142 }
    expect(siguienteNumeroLocal(dato).numero).toBe('V03-000143')
    expect(siguienteNumeroLocal(dato).numero).toBe('V03-000143')
  })

  it('el servidor va adelante del teléfono (bootstrap nuevo): usa el mayor', () => {
    expect(
      siguienteNumeroLocal({ prefijo: '0001', ultimoCorrelativoBootstrap: 200, ultimoCorrelativoLocal: 150 }).numero,
    ).toBe('0001-000201')
  })

  it('el correlativo pasa los seis dígitos sin truncarse', () => {
    expect(
      siguienteNumeroLocal({ prefijo: 'V03', ultimoCorrelativoBootstrap: 999_999, ultimoCorrelativoLocal: null }).numero,
    ).toBe('V03-1000000')
  })
})

describe('secuencia de la cola (SYN-03)', () => {
  it('sin ninguna usada empieza en 1', () => {
    expect(siguienteSecuencia(null)).toBe(1)
  })

  it('es estrictamente creciente: 7 da 8 y 8 da 9', () => {
    const primera = siguienteSecuencia(7)
    const segunda = siguienteSecuencia(primera)
    expect([primera, segunda]).toEqual([8, 9])
  })
})
