/**
 * Change 13, tarea 12.1: textos y cálculo de presentación de las pantallas de precios.
 * La fórmula es PRC-12; el precio por presentación, PRC-22 con `brutoDeLinea`.
 */

import { describe, expect, it } from 'vitest'

import {
  ETIQUETA_DE_CAUSA_SIN_PRECIO,
  avisosDeGeneracion,
  descripcionDeRedondeo,
  etiquetaDeAlcance,
  etiquetaDeCausaSinPrecio,
  etiquetaDeEstadoDeVersion,
  etiquetaDeRelacion,
  etiquetaDeTipoDeMargen,
  formulaDesdePorcentaje,
  etiquetasDeSenales,
  precioPorPresentacion,
  resumenDePublicacion,
  textoDeFormula,
  puedeAnularse,
} from '../../../../src/domain/precios/presentacion'

describe('textoDeFormula (PRC-12)', () => {
  it('markup: el costo por 1,30', () => {
    expect(textoDeFormula('MARKUP', '0.300000')).toBe('Precio = costo × 1,30')
  })

  it('margen bruto: el costo dividido por 0,70', () => {
    expect(textoDeFormula('MARGEN_BRUTO', '0.300000')).toBe('Precio = costo ÷ 0,70')
  })

  it('un markup mayor que 100% y valores con más decimales', () => {
    expect(textoDeFormula('MARKUP', '1.500000')).toBe('Precio = costo × 2,50')
    expect(textoDeFormula('MARGEN_BRUTO', '0.125000')).toBe('Precio = costo ÷ 0,875')
  })

  it('no inventa una fórmula para un tipo desconocido', () => {
    expect(textoDeFormula('OTRO', '0.1')).toBe('')
  })
})

describe('precioPorPresentacion (PRC-22)', () => {
  it('caja x6 a 9.500,00: la botella sale a 1.583,33', () => {
    expect(precioPorPresentacion('9500.00', 6, 1)).toBe('1583.33')
  })

  it('la caja x6 vale lo mismo que el precio de referencia y la x12 el doble', () => {
    expect(precioPorPresentacion('9500.00', 6, 6)).toBe('9500.00')
    expect(precioPorPresentacion('9500.00', 6, 12)).toBe('19000.00')
  })

  it('un solo redondeo, medio hacia arriba', () => {
    expect(precioPorPresentacion('8600.00', 6, 1)).toBe('1433.33')
    expect(precioPorPresentacion('1.00', 8, 1)).toBe('0.13')
  })
})

describe('rótulos', () => {
  it('estado de una versión: el derivado manda sobre el almacenado', () => {
    expect(etiquetaDeEstadoDeVersion('PUBLICADA', 'VIGENTE')).toBe('Vigente')
    expect(etiquetaDeEstadoDeVersion('PUBLICADA', 'PROGRAMADA')).toBe('Programada')
    expect(etiquetaDeEstadoDeVersion('PUBLICADA', 'HISTORICA')).toBe('Histórica')
    expect(etiquetaDeEstadoDeVersion('BORRADOR', null)).toBe('Borrador')
    expect(etiquetaDeEstadoDeVersion('ANULADA', null)).toBe('Anulada')
  })

  it('solo una versión programada se anula (PRC-05)', () => {
    expect(puedeAnularse('PUBLICADA', 'PROGRAMADA')).toBe(true)
    expect(puedeAnularse('PUBLICADA', 'VIGENTE')).toBe(false)
    expect(puedeAnularse('PUBLICADA', 'HISTORICA')).toBe(false)
    expect(puedeAnularse('BORRADOR', null)).toBe(false)
    expect(puedeAnularse('ANULADA', null)).toBe(false)
  })

  it('relación con la versión base', () => {
    expect(etiquetaDeRelacion('NUEVO')).toBe('Nuevo')
    expect(etiquetaDeRelacion('CAMBIA')).toBe('Cambia')
    expect(etiquetaDeRelacion('IGUAL')).toBe('Igual')
    expect(etiquetaDeRelacion(null)).toBe('')
  })

  it('tipo de margen', () => {
    expect(etiquetaDeTipoDeMargen('MARKUP')).toBe('Markup')
    expect(etiquetaDeTipoDeMargen('MARGEN_BRUTO')).toBe('Margen bruto')
  })

  it('cada causa de producto sin precio tiene su rótulo', () => {
    for (const causa of [
      'SIN_COSTO',
      'SIN_REGLA',
      'PRECIO_NO_POSITIVO',
      'SIN_PRESENTACION_DE_REFERENCIA',
      'SIN_CALCULAR',
    ]) {
      expect(ETIQUETA_DE_CAUSA_SIN_PRECIO[causa]).toBeTruthy()
    }
    expect(etiquetaDeCausaSinPrecio('SIN_PRESENTACION_DE_REFERENCIA')).toMatch(/presentaci[oó]n de referencia/i)
    expect(etiquetaDeCausaSinPrecio('SIN_CALCULAR')).toMatch(/regener/i)
    expect(etiquetaDeCausaSinPrecio('CAUSA_NUEVA')).toBe('CAUSA_NUEVA')
  })

  it('señales de un precio: solo las que valen', () => {
    const ninguna = {
      sin_costo: false,
      margen_menor: false,
      costo_otra_regla_iva: false,
      costos_distintos_por_presentacion: false,
    }

    expect(etiquetasDeSenales(ninguna)).toEqual([])
    expect(etiquetasDeSenales(null)).toEqual([])
    expect(etiquetasDeSenales({ ...ninguna, margen_menor: true })).toEqual(['Margen menor que el de la regla'])
    expect(etiquetasDeSenales({ ...ninguna, sin_costo: true, costo_otra_regla_iva: true })).toEqual([
      'Sin costo',
      'Costo calculado con otra regla de IVA',
    ])
    expect(etiquetasDeSenales({ ...ninguna, costos_distintos_por_presentacion: true })).toEqual([
      'Los costos por presentación difieren',
    ])
  })
})

describe('descripcionDeRedondeo (PRC-14)', () => {
  it.each([
    ['100.00', 'ARRIBA', '100,00 · Hacia arriba'],
    ['0.50', 'CERCANO', '0,50 · Al más cercano'],
    ['1000.00', 'ABAJO', '1.000,00 · Hacia abajo'],
  ])('%s %s -> %s', (multiplo, direccion, texto) => {
    expect(descripcionDeRedondeo(multiplo, direccion)).toBe(texto)
  })
})

describe('etiquetaDeAlcance (PRC-13)', () => {
  it('cada alcance tiene su rótulo y uno desconocido se muestra tal cual', () => {
    expect(etiquetaDeAlcance('LISTA')).toBe('Toda la lista')
    expect(etiquetaDeAlcance('CATEGORIA')).toBe('Categoría')
    expect(etiquetaDeAlcance('MARCA')).toBe('Marca')
    expect(etiquetaDeAlcance('PRODUCTO')).toBe('Producto')
    expect(etiquetaDeAlcance('PROVEEDOR')).toBe('Proveedor')
    expect(etiquetaDeAlcance('ZONA')).toBe('ZONA')
  })
})

describe('formulaDesdePorcentaje (vista previa del formulario de regla)', () => {
  it('con el porcentaje que la persona escribe, muestra la fórmula', () => {
    expect(formulaDesdePorcentaje('MARKUP', '12,5')).toBe('Precio = costo × 1,125')
    expect(formulaDesdePorcentaje('MARGEN_BRUTO', '30')).toBe('Precio = costo ÷ 0,70')
  })

  it.each([
    ['MARKUP', ''],
    ['MARKUP', 'abc'],
    ['MARKUP', '-5'],
    ['MARGEN_BRUTO', '100'],
    ['MARGEN_BRUTO', '120'],
    ['COMISION', '10'],
  ])('%s con "%s" no inventa una fórmula', (tipo, porcentaje) => {
    expect(formulaDesdePorcentaje(tipo, porcentaje)).toBe('')
  })
})

describe('resumenDePublicacion (confirmación de "Publicar")', () => {
  it.each([
    [98, 2, '98 precios, 2 productos sin precio'],
    [1, 1, '1 precio, 1 producto sin precio'],
    [5, 0, '5 precios, ningún producto sin precio'],
    [0, 3, 'ningún precio, 3 productos sin precio'],
  ])('%i precios y %i sin precio -> %s', (precios, sinPrecio, texto) => {
    expect(resumenDePublicacion(precios, sinPrecio)).toBe(texto)
  })
})

describe('avisosDeGeneracion (D2, D3)', () => {
  it.each([
    [0, 0, []],
    [1, 0, ['1 precio calculado con otra regla de IVA']],
    [3, 2, ['3 precios calculados con otra regla de IVA', '2 precios con costos distintos por presentación']],
    [0, 1, ['1 precio con costos distintos por presentación']],
  ])('%i con otra regla de IVA y %i con costos distintos', (iva, distintos, esperado) => {
    expect(avisosDeGeneracion({ precios_con_otra_regla_iva: iva, precios_con_costos_distintos: distintos })).toEqual(esperado)
  })
})
