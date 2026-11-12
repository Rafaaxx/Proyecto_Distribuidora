import { describe, expect, it } from 'vitest'

import {
  aCuerpoDeUbicacion,
  esquemaUbicacion,
  etiquetaDeTipoDeUbicacion,
  etiquetaDeTipoDeMovimiento,
} from '../../../../src/domain/stock/ubicacionSchema'

/** STK-02, D7: nombre obligatorio, tipo del catálogo y un vehículo siempre
 * requiere toma (la base y el servidor lo repiten). */
describe('esquemaUbicacion', () => {
  it('acepta un depósito sin toma', () => {
    const r = esquemaUbicacion.safeParse({ nombre: 'Depósito central', tipo: 'DEPOSITO', requiere_toma: false, activo: true })
    expect(r.success).toBe(true)
  })

  it('rechaza un nombre vacío o de espacios', () => {
    expect(esquemaUbicacion.safeParse({ nombre: '   ', tipo: 'DEPOSITO', requiere_toma: false, activo: true }).success).toBe(false)
    expect(esquemaUbicacion.safeParse({ nombre: '', tipo: 'OTRO', requiere_toma: false, activo: true }).success).toBe(false)
  })

  it('rechaza un tipo fuera del catálogo', () => {
    expect(esquemaUbicacion.safeParse({ nombre: 'X', tipo: 'CAMION', requiere_toma: false, activo: true }).success).toBe(false)
  })

  it('rechaza un vehículo sin toma y acepta uno con toma', () => {
    const sin = esquemaUbicacion.safeParse({ nombre: 'Camión 1', tipo: 'VEHICULO', requiere_toma: false, activo: true })
    expect(sin.success).toBe(false)
    const con = esquemaUbicacion.safeParse({ nombre: 'Camión 1', tipo: 'VEHICULO', requiere_toma: true, activo: true })
    expect(con.success).toBe(true)
  })
})

describe('aCuerpoDeUbicacion', () => {
  it('recorta el nombre y conserva el resto', () => {
    expect(aCuerpoDeUbicacion({ nombre: '  Camión 1 ', tipo: 'VEHICULO', requiere_toma: true, activo: false })).toEqual({
      nombre: 'Camión 1',
      tipo: 'VEHICULO',
      requiere_toma: true,
      activo: false,
    })
  })
})

describe('etiquetas', () => {
  it('nombra los tipos de ubicación y de movimiento', () => {
    expect(etiquetaDeTipoDeUbicacion('DEPOSITO')).toBe('Depósito')
    expect(etiquetaDeTipoDeUbicacion('VEHICULO')).toBe('Vehículo')
    expect(etiquetaDeTipoDeUbicacion('OTRO')).toBe('Otro')
    expect(etiquetaDeTipoDeMovimiento('STOCK_INICIAL')).toBe('Stock inicial')
    expect(etiquetaDeTipoDeMovimiento('ALGO_NUEVO')).toBe('ALGO_NUEVO')
  })
})
