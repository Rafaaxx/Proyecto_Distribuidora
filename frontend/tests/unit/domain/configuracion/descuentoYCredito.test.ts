/**
 * Change 18b, tarea 14.1: la tolerancia del crédito por defecto como la recibe el servidor
 * (CRE-06, ADR-032, INV-03; `design.md` D14).
 */

import { describe, expect, it } from 'vitest'

import {
  leerTolerancia,
  toleranciaParaElFormulario,
} from '../../../../src/domain/configuracion/descuentoYCredito'

describe('leerTolerancia', () => {
  it('sin tipo son los dos nulos (sin tolerancia: todo exceso sin señal pide permiso o PIN)', () => {
    expect(leerTolerancia({ tipo: '', valor: '' })).toEqual({ valida: true, tipo: null, valor: null })
    expect(leerTolerancia({ tipo: '', valor: '999' })).toEqual({ valida: true, tipo: null, valor: null })
  })

  it.each([
    ['IMPORTE', '20000', '20000.00'],
    ['IMPORTE', '20000,5', '20000.50'],
    ['IMPORTE', '0', '0.00'],
    ['PORCENTAJE', '2,5', '2.50'],
    ['PORCENTAJE', '100', '100.00'],
  ] as const)('%s "%s" se envía como "%s"', (tipo, valor, esperado) => {
    expect(leerTolerancia({ tipo, valor })).toEqual({ valida: true, tipo, valor: esperado })
  })

  it.each(['', 'abc', '-5', '1,234', '1e3', '5%'])('el valor "%s" no es válido', (valor) => {
    const r = leerTolerancia({ tipo: 'IMPORTE', valor })
    expect(r.valida).toBe(false)
  })

  it('un porcentaje del límite no puede pasar de 100', () => {
    expect(leerTolerancia({ tipo: 'PORCENTAJE', valor: '100,01' })).toEqual({
      valida: false,
      mensaje: 'El porcentaje del límite no puede pasar de 100.',
    })
  })

  it('un importe grande conserva sus centavos exactos (INV-03)', () => {
    expect(leerTolerancia({ tipo: 'IMPORTE', valor: '12345678901234,56' })).toEqual({
      valida: true,
      tipo: 'IMPORTE',
      valor: '12345678901234.56',
    })
  })
})

describe('toleranciaParaElFormulario', () => {
  it('muestra el valor del servidor con coma decimal', () => {
    expect(toleranciaParaElFormulario('PORCENTAJE', '2.50')).toEqual({ tipo: 'PORCENTAJE', valor: '2,50' })
    expect(toleranciaParaElFormulario('IMPORTE', '20000.00')).toEqual({ tipo: 'IMPORTE', valor: '20000,00' })
  })

  it('sin tolerancia (o a medias) deja el formulario vacío', () => {
    expect(toleranciaParaElFormulario(null, null)).toEqual({ tipo: '', valor: '' })
    expect(toleranciaParaElFormulario('IMPORTE', null)).toEqual({ tipo: '', valor: '' })
  })
})
