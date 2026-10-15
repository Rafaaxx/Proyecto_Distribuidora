/**
 * Change 16, tarea 15.4 (gobernanza crítica, D13): tope de descuento manual de un rol. El tope se
 * escribe como porcentaje (`5`, `12,5`) y viaja como fracción de seis decimales (`"0.050000"`);
 * 100 % es "Sin tope" (DSC-06; `01` §19; TR-02, INV-03). Solo UX: el servidor valida igual
 * (`IDENTIDAD_TOPE_DESCUENTO_FUERA_DE_RANGO`).
 */

import { describe, expect, it } from 'vitest'

import {
  avisaTopeCero,
  describirTope,
  esquemaTope,
  esTopeCero,
  topeEscritoDesdeFraccion,
} from '../../../../src/domain/identidad/topes'

describe('esquemaTope (TR-02)', () => {
  it.each([
    ['5', '0.050000'],
    ['12,5', '0.125000'],
    ['12.5', '0.125000'],
    ['0', '0.000000'],
    ['100', '1.000000'],
    ['0,0001', '0.000001'],
    [' 7 ', '0.070000'],
  ])('el tope escrito %s viaja como %s', (escrito, fraccion) => {
    expect(esquemaTope.parse({ tope_descuento: escrito })).toEqual({ tope_descuento: fraccion })
  })

  it.each(['120', '100,01', '-1', '-0,5', '', 'cinco', '1e2', '5,12345', '5%'])(
    'rechaza %s junto al tope y no produce nada para enviar',
    (escrito) => {
      const resultado = esquemaTope.safeParse({ tope_descuento: escrito })

      expect(resultado.success).toBe(false)
      expect(resultado.error?.issues[0]?.path).toEqual(['tope_descuento'])
    },
  )
})

describe('describirTope', () => {
  it.each([
    ['1.000000', 'Sin tope'],
    ['0.050000', '5 %'],
    ['0.125000', '12,5 %'],
    ['0.000000', '0 %'],
    ['0.100000', '10 %'],
  ])('%s se muestra como %s', (fraccion, texto) => {
    expect(describirTope(fraccion)).toBe(texto)
  })
})

describe('esTopeCero (DSC-06: un rol con tope 0 % necesita autorización)', () => {
  it('solo el cero exacto', () => {
    expect(esTopeCero('0.000000')).toBe(true)
    expect(esTopeCero('0.000001')).toBe(false)
    expect(esTopeCero('1.000000')).toBe(false)
  })
})

describe('topeEscritoDesdeFraccion', () => {
  it('es lo que la persona escribiría: 0.050000 -> 5, 0.125000 -> 12.5, 1.000000 -> 100', () => {
    expect(topeEscritoDesdeFraccion('0.050000')).toBe('5')
    expect(topeEscritoDesdeFraccion('0.125000')).toBe('12.5')
    expect(topeEscritoDesdeFraccion('1.000000')).toBe('100')
    expect(topeEscritoDesdeFraccion('0.000000')).toBe('0')
  })
})

describe('avisaTopeCero (DSC-06: el aviso solo vale donde el rol puede dar descuento manual)', () => {
  const con = (permisos: string[], tope: string) => ({ permisos, tope_descuento: tope })

  it('con DESCUENTO_MANUAL y tope 0 avisa', () => {
    expect(avisaTopeCero(con(['VER_COSTOS', 'DESCUENTO_MANUAL'], '0.000000'))).toBe(true)
  })
  it('sin DESCUENTO_MANUAL y tope 0 no avisa', () => {
    expect(avisaTopeCero(con(['VER_COSTOS'], '0.000000'))).toBe(false)
    expect(avisaTopeCero(con([], '0.000000'))).toBe(false)
  })
  it('con DESCUENTO_MANUAL y tope mayor que 0 no avisa', () => {
    expect(avisaTopeCero(con(['DESCUENTO_MANUAL'], '0.000001'))).toBe(false)
    expect(avisaTopeCero(con(['DESCUENTO_MANUAL'], '1.000000'))).toBe(false)
  })
})
