import { describe, expect, it } from 'vitest'

import {
  AMBITOS_DE_MOTIVO,
  NOMBRE_DE_AMBITO,
  esquemaAlicuota,
  esquemaMotivo,
  esquemaRedondeoPorDefecto,
  fraccionAPorcentaje,
  mensajeDeErrorDeAlicuota,
  mensajeDeErrorDeMotivo,
  porcentajeAFraccion,
} from '../../../../src/domain/configuracion/catalogos'

/**
 * Dominio de las pantallas de motivos, alícuotas y redondeo por defecto (change 20c, tarea 7.1;
 * D7, D12; TR-02, TR-09, INV-03). Solo UX: el servidor valida igual.
 */

describe('ámbitos de motivo', () => {
  it('los diez ámbitos tienen nombre en castellano, distinto del código', () => {
    expect(AMBITOS_DE_MOTIVO).toHaveLength(10)
    for (const ambito of AMBITOS_DE_MOTIVO) {
      expect(NOMBRE_DE_AMBITO[ambito]).toBeTruthy()
      expect(NOMBRE_DE_AMBITO[ambito]).not.toBe(ambito)
    }
    expect(new Set(AMBITOS_DE_MOTIVO.map((a) => NOMBRE_DE_AMBITO[a])).size).toBe(10)
  })

  it('nombra los ámbitos que usa la prueba manual', () => {
    expect(NOMBRE_DE_AMBITO.AJUSTE_STOCK).toBe('Ajuste de stock')
    expect(NOMBRE_DE_AMBITO.LIBERACION_JORNADA).toBe('Liberación de jornada')
  })
})

describe('porcentajeAFraccion (D7, INV-03)', () => {
  it.each([
    ['10,5', '0.105000'],
    ['21', '0.210000'],
    ['0', '0.000000'],
    ['10.5', '0.105000'],
    ['0,0001', '0.000001'],
    ['  27 ', '0.270000'],
  ])('%j -> %j', (entrada, esperado) => {
    expect(porcentajeAFraccion(entrada)).toBe(esperado)
  })

  it.each(['', 'abc', '-1', '100', '100,5', '10,12345', '1,2,3', '99,99999'])('%j es inválido', (entrada) => {
    expect(porcentajeAFraccion(entrada)).toBeNull()
  })

  it('99,9999 es válido (el mayor con cuatro decimales)', () => {
    expect(porcentajeAFraccion('99,9999')).toBe('0.999999')
  })
})

describe('fraccionAPorcentaje', () => {
  it.each([
    ['0.105000', '10,5'],
    ['0.210000', '21'],
    ['0.000000', '0'],
    ['0.000001', '0,0001'],
  ])('%j -> %j', (fraccion, esperado) => {
    expect(fraccionAPorcentaje(fraccion)).toBe(esperado)
  })

  it('ida y vuelta conserva el valor', () => {
    expect(fraccionAPorcentaje(porcentajeAFraccion('12,3456') as string)).toBe('12,3456')
  })
})

describe('esquemaMotivo', () => {
  it('recorta el nombre', () => {
    const r = esquemaMotivo.safeParse({ nombre: '  Robo ' })
    expect(r.success && r.data).toEqual({ nombre: 'Robo' })
  })
  it.each(['', '   '])('rechaza el nombre vacío %j', (nombre) => {
    expect(esquemaMotivo.safeParse({ nombre }).success).toBe(false)
  })
})

describe('esquemaAlicuota', () => {
  it('convierte el porcentaje a fracción string', () => {
    const r = esquemaAlicuota.safeParse({ nombre: ' 27% ', porcentaje: '27' })
    expect(r.success && r.data).toEqual({ nombre: '27%', valor: '0.270000' })
  })
  it('acepta coma decimal', () => {
    const r = esquemaAlicuota.safeParse({ nombre: '10,5%', porcentaje: '10,5' })
    expect(r.success && r.data).toEqual({ nombre: '10,5%', valor: '0.105000' })
  })
  it.each([
    { nombre: '', porcentaje: '27' },
    { nombre: 'X', porcentaje: '100' },
    { nombre: 'X', porcentaje: '' },
    { nombre: 'X', porcentaje: '1,23456' },
  ])('rechaza %j', (datos) => {
    expect(esquemaAlicuota.safeParse(datos).success).toBe(false)
  })
})

describe('esquemaRedondeoPorDefecto', () => {
  it('acepta múltiplo y dirección', () => {
    const r = esquemaRedondeoPorDefecto.safeParse({ redondeo_multiplo: '500', redondeo_direccion: 'ABAJO' })
    expect(r.success && r.data).toEqual({ redondeo_multiplo: '500', redondeo_direccion: 'ABAJO' })
  })
  it.each([
    { redondeo_multiplo: '0', redondeo_direccion: 'ABAJO' },
    { redondeo_multiplo: '10,005', redondeo_direccion: 'ABAJO' },
    { redondeo_multiplo: '', redondeo_direccion: 'ABAJO' },
    { redondeo_multiplo: '100', redondeo_direccion: '' },
  ])('rechaza %j', (datos) => {
    expect(esquemaRedondeoPorDefecto.safeParse(datos).success).toBe(false)
  })
})

describe('mensajes de error del servidor', () => {
  it('motivos', () => {
    expect(mensajeDeErrorDeMotivo('ULTIMO_MOTIVO_ACTIVO', 'x')).toMatch(/al menos un motivo activo/i)
    expect(mensajeDeErrorDeMotivo('NOMBRE_DUPLICADO', 'x')).toMatch(/ya hay un motivo con ese nombre/i)
    expect(mensajeDeErrorDeMotivo('NOMBRE_INVALIDO', 'x')).toMatch(/escribí un nombre/i)
    expect(mensajeDeErrorDeMotivo('OTRO', 'del servidor')).toBe('del servidor')
  })
  it('alícuotas, con la cantidad de productos', () => {
    expect(mensajeDeErrorDeAlicuota('VALOR_DUPLICADO', 'x')).toMatch(/ya hay una alícuota con ese porcentaje/i)
    expect(mensajeDeErrorDeAlicuota('ULTIMA_ALICUOTA_ACTIVA', 'x')).toMatch(/al menos una alícuota activa/i)
    expect(mensajeDeErrorDeAlicuota('ALICUOTA_EN_USO', 'x', 3)).toMatch(/3 productos activos/)
    expect(mensajeDeErrorDeAlicuota('ALICUOTA_EN_USO', 'x', 1)).toMatch(/1 producto activo\b/)
    expect(mensajeDeErrorDeAlicuota('OTRO', 'del servidor')).toBe('del servidor')
  })
})
