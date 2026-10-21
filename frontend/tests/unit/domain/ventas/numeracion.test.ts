import { describe, expect, it } from 'vitest'

import {
  correlativoDeNumero,
  formatearNumero,
  guardarCorrelativo,
  leerCorrelativoGuardado,
  proponerNumero,
  type AlmacenDeCorrelativo,
} from '../../../../src/domain/ventas/numeracion'

function almacenEnMemoria(inicial: Record<string, string> = {}): AlmacenDeCorrelativo {
  const datos = { ...inicial }
  return {
    getItem: (clave) => datos[clave] ?? null,
    setItem: (clave, valor) => {
      datos[clave] = valor
    },
  }
}

const ALMACEN_ROTO: AlmacenDeCorrelativo = {
  getItem: () => {
    throw new Error('almacenamiento bloqueado')
  },
  setItem: () => {
    throw new Error('almacenamiento bloqueado')
  },
}

/** VTA-06, D4: número propuesto = mayor entre el servidor y el navegador, más uno. */
describe('número propuesto (VTA-06, design D4)', () => {
  it('formatea PPP-NNNNNN con seis dígitos', () => {
    expect(formatearNumero('V01', 42)).toBe('V01-000042')
    expect(formatearNumero('PC2', 1234567)).toBe('PC2-1234567')
  })

  it('extrae el correlativo solo si el prefijo es el del dispositivo', () => {
    expect(correlativoDeNumero('V01-000042', 'V01')).toBe(42)
    expect(correlativoDeNumero('V02-000042', 'V01')).toBeNull()
    expect(correlativoDeNumero('V01-abc', 'V01')).toBeNull()
  })

  it('sin valor guardado propone el siguiente del servidor (41 -> V01-000042)', () => {
    expect(proponerNumero({ prefijo: 'V01', ultimoCorrelativo: 41 }, null)).toBe('V01-000042')
  })

  it('si el navegador guardó uno mayor, manda el guardado (otra pestaña vendió sin que el servidor lo refleje)', () => {
    expect(proponerNumero({ prefijo: 'V01', ultimoCorrelativo: 41 }, 44)).toBe('V01-000045')
  })

  it('si el guardado es menor que el del servidor, manda el servidor', () => {
    expect(proponerNumero({ prefijo: 'V01', ultimoCorrelativo: 41 }, 10)).toBe('V01-000042')
  })
})

describe('correlativo guardado en el navegador (try/catch)', () => {
  it('guarda y lee por prefijo', () => {
    const almacen = almacenEnMemoria()
    guardarCorrelativo('V01', 42, almacen)
    expect(leerCorrelativoGuardado('V01', almacen)).toBe(42)
    expect(leerCorrelativoGuardado('V02', almacen)).toBeNull()
  })

  it('nunca retrocede: guardar uno menor conserva el mayor', () => {
    const almacen = almacenEnMemoria()
    guardarCorrelativo('V01', 50, almacen)
    guardarCorrelativo('V01', 43, almacen)
    expect(leerCorrelativoGuardado('V01', almacen)).toBe(50)
  })

  it('un valor guardado corrupto se ignora', () => {
    expect(leerCorrelativoGuardado('V01', almacenEnMemoria({ 'ventas.correlativo.V01': 'xx' }))).toBeNull()
  })

  it('si el almacenamiento falla o no existe, lee nulo y guarda sin romper', () => {
    expect(leerCorrelativoGuardado('V01', ALMACEN_ROTO)).toBeNull()
    expect(() => guardarCorrelativo('V01', 5, ALMACEN_ROTO)).not.toThrow()
    expect(leerCorrelativoGuardado('V01', undefined)).toBeNull()
    expect(() => guardarCorrelativo('V01', 5, undefined)).not.toThrow()
  })
})
