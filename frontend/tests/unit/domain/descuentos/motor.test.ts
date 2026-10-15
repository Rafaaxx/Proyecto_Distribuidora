/**
 * Change 16, tarea 3.2: motor de descuentos (DSC-05, DSC-06, DSC-07, DSC-08, INV-03; `design.md`
 * D7 a D11). Lo que comparte con el servidor corre en `tests/unit/calculo/dsc05.fixtures.test.ts`;
 * acá, el desempate por orden de entrega, el manual por línea y las guardas de entrada.
 */

import { describe, expect, it } from 'vitest'

import { ErrorDeDescuentos } from '../../../../src/domain/descuentos/errores'
import { calcularDescuentos } from '../../../../src/domain/descuentos/motor'
import type {
  AlcanceRegla,
  LineaVenta,
  ReglaDescuento,
  ResultadoDescuentos,
} from '../../../../src/domain/descuentos/tipos'

function linea(id: string, bruto: string, parcial: Partial<LineaVenta> = {}): LineaVenta {
  return {
    id,
    bruto,
    cantidadBase: 1,
    unidadesReferencia: 1,
    productoId: `prod-${id}`,
    categoriaId: 'cat',
    marcaId: 'marca',
    descuentoManual: null,
    ...parcial,
  }
}

function porcentaje(n: number, pct: string, parcial: Partial<ReglaDescuento> = {}): ReglaDescuento {
  return {
    id: String(n).padStart(8, '0'),
    tipo: 'VOLUMEN_OPERACION',
    medida: 'UNIDADES_BASE',
    operador: 'GTE',
    umbral: '1',
    accionTipo: 'PORCENTAJE',
    accionPorcentaje: pct,
    accionImporte: null,
    acumulable: false,
    prioridad: 1,
    alcances: [],
    ...parcial,
  }
}

function fijo(n: number, importe: string, parcial: Partial<ReglaDescuento> = {}): ReglaDescuento {
  return {
    ...porcentaje(n, '0.05', parcial),
    accionTipo: 'IMPORTE_FIJO',
    accionPorcentaje: null,
    accionImporte: importe,
    ...parcial,
  }
}

const importes = (r: ResultadoDescuentos): string[][] =>
  r.lineas.map((l) => l.descuentos.map((d) => d.importe.toFixed(2)))

function permutaciones<T>(items: readonly T[]): T[][] {
  if (items.length <= 1) {
    return [[...items]]
  }
  return items.flatMap((item, i) =>
    permutaciones([...items.slice(0, i), ...items.slice(i + 1)]).map((resto) => [item, ...resto]),
  )
}

const codigoDe = (f: () => unknown): string | undefined => {
  try {
    f()
  } catch (error) {
    return (error as { codigo?: string }).codigo
  }
  return undefined
}

describe('una sola no acumulable por venta (D7, D8)', () => {
  const a = linea('a', '150000.00', { cantidadBase: 72, unidadesReferencia: 6, productoId: 'pa' })
  const b = linea('b', '86000.00', { cantidadBase: 60, unidadesReferencia: 6, productoId: 'pb' })
  const r1 = porcentaje(1, '0.05', { medida: 'CAJAS_EQUIVALENTES', umbral: '20' })
  const alcancePa: AlcanceRegla[] = [{ tipo: 'PRODUCTO', entidadId: 'pa' }]
  const r2 = porcentaje(2, '0.08', {
    prioridad: 2,
    medida: 'CAJAS_EQUIVALENTES',
    umbral: '10',
    tipo: 'VOLUMEN_ALCANCE',
    alcances: alcancePa,
  })

  it('gana la de mayor beneficio total y la otra no se aplica a ninguna línea', () => {
    const r = calcularDescuentos([a, b], [r1, r2], null)
    expect(importes(r)).toEqual([['12000.00'], []])
    expect(r.lineas[0]?.descuentos[0]?.reglaId).toBe(r2.id)
    expect(r.lineas[1]?.neto.toFixed(2)).toBe('86000.00')
  })

  it('gana la otra cuando el beneficio se invierte', () => {
    const a2 = linea('a', '100000.00', { cantidadBase: 72, unidadesReferencia: 6, productoId: 'pa' })
    expect(importes(calcularDescuentos([a2, b], [r2, r1], null))).toEqual([['5000.00'], ['4300.00']])
  })

  it('empate de beneficio: gana la prioridad más baja aunque sea la más nueva', () => {
    const l = linea('a', '10000.00')
    const vieja = porcentaje(1, '0.05', { prioridad: 2 })
    const nueva = porcentaje(2, '0.05', { prioridad: 1 })
    const r = calcularDescuentos([l], [vieja, nueva], null)
    expect(r.lineas[0]?.descuentos[0]?.reglaId).toBe(nueva.id)
  })

  it('empate de beneficio y prioridad: gana la creada primero en cualquier orden', () => {
    const l = linea('a', '10000.00')
    const primera = porcentaje(1, '0.05')
    const segunda = porcentaje(2, '0.05')
    for (const orden of permutaciones([primera, segunda])) {
      expect(calcularDescuentos([l], orden, null).lineas[0]?.descuentos[0]?.reglaId).toBe(primera.id)
    }
  })

  it('una regla cuya condición no se cumple no participa', () => {
    const l = linea('a', '10000.00', { cantidadBase: 10 })
    const r = calcularDescuentos([l], [porcentaje(1, '0.2', { umbral: '1000' }), porcentaje(2, '0.05')], null)
    expect(importes(r)).toEqual([['500.00']])
  })
})

describe('acumulables en orden sobre el resultado anterior (D9)', () => {
  it('se aplican después de la ganadora y suman el detalle por línea', () => {
    const a = linea('a', '150000.00', { cantidadBase: 72, unidadesReferencia: 6, productoId: 'pa' })
    const b = linea('b', '86000.00', { cantidadBase: 60, unidadesReferencia: 6, productoId: 'pb' })
    const ganadora = porcentaje(2, '0.08', {
      tipo: 'VOLUMEN_ALCANCE',
      medida: 'CAJAS_EQUIVALENTES',
      umbral: '10',
      alcances: [{ tipo: 'PRODUCTO', entidadId: 'pa' }],
    })
    const acumulable = porcentaje(3, '0.02', {
      prioridad: 3,
      acumulable: true,
      medida: 'IMPORTE_BRUTO',
      umbral: '200000',
    })
    const r = calcularDescuentos([a, b], [acumulable, ganadora], null)
    expect(importes(r)).toEqual([['12000.00', '2760.00'], ['1720.00']])
    expect(r.lineas.map((l) => l.neto.toFixed(2))).toEqual(['135240.00', '84280.00'])
    expect(r.lineas[0]?.descuentoTotal.toFixed(2)).toBe('14760.00')
  })

  it('dos acumulables se encadenan por prioridad y no suman porcentajes', () => {
    const l = linea('a', '10000.00')
    const segunda = porcentaje(1, '0.02', { prioridad: 2, acumulable: true })
    const primera = porcentaje(2, '0.08', { prioridad: 1, acumulable: true })
    const r = calcularDescuentos([l], [segunda, primera], null)
    expect(r.lineas[0]?.descuentos.map((d) => d.reglaId)).toEqual([primera.id, segunda.id])
    expect(importes(r)).toEqual([['800.00', '184.00']])
    expect(r.lineas[0]?.neto.toFixed(2)).toBe('9016.00')
  })

  it('igual prioridad se ordena por antigüedad', () => {
    const l = linea('a', '10000.00')
    const vieja = porcentaje(1, '0.08', { acumulable: true })
    const nueva = porcentaje(2, '0.02', { acumulable: true })
    const r = calcularDescuentos([l], [nueva, vieja], null)
    expect(r.lineas[0]?.descuentos.map((d) => d.reglaId)).toEqual([vieja.id, nueva.id])
  })

  it('la condición de una acumulable mira el bruto, no lo ya descontado', () => {
    const a = linea('a', '150000.00')
    const b = linea('b', '86000.00')
    const acumulable = porcentaje(2, '0.02', {
      prioridad: 2,
      acumulable: true,
      medida: 'IMPORTE_BRUTO',
      umbral: '200000',
    })
    const r = calcularDescuentos([a, b], [fijo(1, '38000.00'), acumulable], null)
    expect(importes(r)).toEqual([['24152.54', '2516.95'], ['13847.46', '1443.05']])
  })

  it('un importe fijo acumulable se reparte sobre el resultado anterior', () => {
    const r = calcularDescuentos(
      [linea('a', '135240.00'), linea('b', '84280.00')],
      [fijo(1, '1000.00', { acumulable: true })],
      null,
    )
    expect(importes(r)).toEqual([['616.07'], ['383.93']])
  })

  it('un descuento que redondea a cero no se informa', () => {
    const r = calcularDescuentos([linea('chica', '0.05'), linea('grande', '100.00')], [porcentaje(1, '0.05')], null)
    expect(r.lineas[0]?.descuentos).toEqual([])
    expect(r.lineas[0]?.neto.toFixed(2)).toBe('0.05')
    expect(importes(r)[1]).toEqual(['5.00'])
  })

  it('el neto nunca es negativo con un importe fijo mayor y una acumulable posterior', () => {
    const r = calcularDescuentos(
      [linea('a', '100.00')],
      [fijo(1, '500.00', { acumulable: true }), porcentaje(2, '0.5', { prioridad: 2, acumulable: true })],
      null,
    )
    expect(r.lineas[0]?.neto.toFixed(2)).toBe('0.00')
    expect(importes(r)).toEqual([['100.00']])
  })

  it('sin reglas ni manual cada línea queda en su bruto y el máximo es nulo', () => {
    const r = calcularDescuentos([linea('a', '100.00'), linea('b', '250.50')], [], null)
    expect(r.lineas.map((l) => l.neto.toFixed(2))).toEqual(['100.00', '250.50'])
    expect(r.lineas.map((l) => l.descuentoTotal.toFixed(2))).toEqual(['0.00', '0.00'])
    expect(r.porcentajeManualMaximo).toBeNull()
  })

  it('el detalle lleva origen, regla, porcentaje (nulo en el importe fijo) e importe', () => {
    const r = calcularDescuentos(
      [linea('a', '10000.00')],
      [porcentaje(1, '0.05'), fijo(2, '100.00', { prioridad: 2, acumulable: true })],
      null,
    )
    const [porcentual, fijoAplicado] = r.lineas[0]?.descuentos ?? []
    expect([porcentual?.origen, porcentual?.reglaId, porcentual?.porcentaje?.toFixed(6), porcentual?.importe.toFixed(2)]).toEqual(
      ['AUTOMATICO', '00000001', '0.050000', '500.00'],
    )
    expect([fijoAplicado?.reglaId, fijoAplicado?.porcentaje, fijoAplicado?.importe.toFixed(2)]).toEqual([
      '00000002',
      null,
      '100.00',
    ])
  })
})

describe('descuento manual, paso 5 (D11)', () => {
  it('el general se aplica sobre el resultado de los automáticos y es el último de la línea', () => {
    const r = calcularDescuentos([linea('a', '10000.00')], [porcentaje(1, '0.05')], '0.10')
    expect(r.lineas[0]?.descuentos.map((d) => d.origen)).toEqual(['AUTOMATICO', 'MANUAL'])
    const manual = r.lineas[0]?.descuentos[1]
    expect([manual?.reglaId, manual?.porcentaje?.toFixed(6), manual?.importe.toFixed(2)]).toEqual([
      null,
      '0.100000',
      '950.00',
    ])
  })

  it('el propio mayor reemplaza al general y no se suman', () => {
    const r = calcularDescuentos(
      [linea('a', '135240.00', { descuentoManual: '0.10' }), linea('b', '84280.00')],
      [],
      '0.05',
    )
    expect(importes(r)).toEqual([['13524.00'], ['4214.00']])
    expect(r.porcentajeManualMaximo?.toFixed(6)).toBe('0.100000')
    expect(r.lineas[0]?.descuentos).toHaveLength(1)
  })

  it('el propio menor que el general también lo reemplaza', () => {
    const r = calcularDescuentos(
      [linea('a', '135240.00'), linea('b', '84280.00', { descuentoManual: '0.03' })],
      [],
      '0.10',
    )
    expect(importes(r)).toEqual([['13524.00'], ['2528.40']])
    expect(r.lineas[1]?.neto.toFixed(2)).toBe('81751.60')
    expect(r.porcentajeManualMaximo?.toFixed(6)).toBe('0.100000')
  })

  it('solo propio, sin general: las demás líneas no llevan manual', () => {
    const r = calcularDescuentos(
      [linea('a', '135240.00', { descuentoManual: '0.10' }), linea('b', '84280.00')],
      [],
      null,
    )
    expect(importes(r)).toEqual([['13524.00'], []])
    expect(r.porcentajeManualMaximo?.toFixed(6)).toBe('0.100000')
  })

  it('el general reemplazado en todas las líneas no cuenta para el máximo', () => {
    const r = calcularDescuentos(
      [
        linea('a', '135240.00', { descuentoManual: '0.03' }),
        linea('b', '84280.00', { descuentoManual: '0.02' }),
      ],
      [],
      '0.10',
    )
    expect(importes(r)).toEqual([['4057.20'], ['1685.60']])
    expect(r.porcentajeManualMaximo?.toFixed(6)).toBe('0.030000')
  })

  it('sin general ni propios el máximo es nulo', () => {
    const r = calcularDescuentos([linea('a', '100.00')], [porcentaje(1, '0.05')], null)
    expect(r.porcentajeManualMaximo).toBeNull()
    expect(r.lineas[0]?.descuentos.map((d) => d.origen)).toEqual(['AUTOMATICO'])
  })

  it('un manual de importe cero no se informa ni cuenta para el máximo', () => {
    const r = calcularDescuentos([linea('cero', '0.00'), linea('cien', '100.00')], [], '0.05')
    expect(r.lineas[0]?.descuentos).toEqual([])
    expect(importes(r)).toEqual([[], ['5.00']])
    expect(r.porcentajeManualMaximo?.toFixed(6)).toBe('0.050000')
  })

  it.each(['0', '-0.05', '1.000001', '0.0500001', 0.05, 1, false, true])(
    'el general %s se rechaza con DESCUENTO_MANUAL_INVALIDO',
    (invalido) => {
      expect(
        codigoDe(() => calcularDescuentos([linea('a', '100.00')], [], invalido as unknown as string)),
      ).toBe('DESCUENTO_MANUAL_INVALIDO')
    },
  )

  it.each(['0', '-0.05', '1.000001', '0.0500001', 0.05])(
    'el propio %s se rechaza para toda la venta',
    (invalido) => {
      const lineas = [
        linea('a', '100.00', { descuentoManual: invalido as unknown as string }),
        linea('b', '100.00'),
      ]
      expect(codigoDe(() => calcularDescuentos(lineas, [], '0.05'))).toBe('DESCUENTO_MANUAL_INVALIDO')
    },
  )

  it.each(['1', '1.000000', '0.000001', '0.123456'])('el extremo %s del dominio se acepta', (valido) => {
    const r = calcularDescuentos([linea('a', '1000000.00')], [], valido)
    expect(r.porcentajeManualMaximo?.toFixed(6)).toBe(Number(valido).toFixed(6))
  })
})

describe('entradas inválidas y determinismo', () => {
  it('un bruto number se rechaza (INV-03)', () => {
    const mala = linea('a', 31250.5 as unknown as string)
    expect(codigoDe(() => calcularDescuentos([mala], [], null))).toBe('ENTRADA_NO_ES_DINERO_EXACTO')
  })

  it.each([
    ['cantidadBase', 0],
    ['cantidadBase', -1],
    ['cantidadBase', 1.5],
    ['unidadesReferencia', 0],
    ['unidadesReferencia', -1],
    ['unidadesReferencia', 1.5],
  ] as const)('%s = %s se rechaza con LINEA_DESCUENTO_INVALIDA', (campo, valor) => {
    const mala = linea('a', '100.00', { [campo]: valor })
    expect(codigoDe(() => calcularDescuentos([mala], [], null))).toBe('LINEA_DESCUENTO_INVALIDA')
  })

  it.each(['-1.00', '10.001'])('un bruto %s se rechaza con LINEA_DESCUENTO_INVALIDA', (bruto) => {
    expect(codigoDe(() => calcularDescuentos([linea('a', bruto)], [], null))).toBe(
      'LINEA_DESCUENTO_INVALIDA',
    )
  })

  it('el porcentaje de una regla como number se rechaza (INV-03)', () => {
    const regla = porcentaje(1, 0.05 as unknown as string)
    expect(codigoDe(() => calcularDescuentos([linea('a', '100.00')], [regla], null))).toBe(
      'ENTRADA_NO_ES_DINERO_EXACTO',
    )
  })

  it('una regla con medida desconocida se rechaza con REGLA_DESCUENTO_INVALIDA', () => {
    const rara = { ...porcentaje(1, '0.05'), medida: 'HISTORIAL_DE_COMPRAS' } as unknown as ReglaDescuento
    expect(codigoDe(() => calcularDescuentos([linea('a', '100.00')], [rara], null))).toBe(
      'REGLA_DESCUENTO_INVALIDA',
    )
    expect(new ErrorDeDescuentos('REGLA_DESCUENTO_INVALIDA', 'x').codigo).toBe('REGLA_DESCUENTO_INVALIDA')
  })

  it('el resultado no depende del orden de las reglas ni de sus alcances', () => {
    const a = linea('a', '150000.00', { cantidadBase: 72, unidadesReferencia: 6, productoId: 'pa' })
    const b = linea('b', '86000.00', { cantidadBase: 60, unidadesReferencia: 6, productoId: 'pb' })
    const alcances: AlcanceRegla[] = [
      { tipo: 'PRODUCTO', entidadId: 'pa' },
      { tipo: 'MARCA', entidadId: 'marca-x' },
    ]
    const reglas = [
      porcentaje(1, '0.05', { medida: 'CAJAS_EQUIVALENTES', umbral: '20' }),
      porcentaje(2, '0.08', {
        prioridad: 2,
        tipo: 'VOLUMEN_ALCANCE',
        medida: 'CAJAS_EQUIVALENTES',
        umbral: '10',
        alcances,
      }),
      porcentaje(3, '0.02', { prioridad: 3, acumulable: true, medida: 'IMPORTE_BRUTO', umbral: '200000' }),
      fijo(5, '1000.00', { prioridad: 4, acumulable: true }),
    ]
    const resumen = (r: ResultadoDescuentos) =>
      JSON.stringify({
        l: r.lineas.map((l) => [l.id, l.neto.toFixed(2), l.descuentos.map((d) => [d.reglaId, d.importe.toFixed(2)])]),
        m: r.porcentajeManualMaximo?.toFixed(6) ?? null,
      })
    const referencia = resumen(calcularDescuentos([a, b], reglas, '0.05'))

    for (const orden of permutaciones(reglas)) {
      expect(resumen(calcularDescuentos([a, b], orden, '0.05'))).toBe(referencia)
    }
    const invertidos = reglas.map((r) => ({ ...r, alcances: [...r.alcances].reverse() }))
    expect(resumen(calcularDescuentos([a, b], invertidos, '0.05'))).toBe(referencia)
  })
})
