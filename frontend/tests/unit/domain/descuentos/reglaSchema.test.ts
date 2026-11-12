/**
 * Change 16, tarea 14.1: esquema Zod del formulario de regla de descuento y conversión del
 * porcentaje escrito a fracción (DSC-01 a DSC-04, TR-02, INV-03, INV-04; `design.md` D5, D8,
 * D16). Solo UX: el servidor valida igual (`UMBRAL_INVALIDO`, `ACCION_INVALIDA`,
 * `PRIORIDAD_INVALIDA`, `ALCANCE_INVALIDO`, `VIGENCIA_INVALIDA`). Nada pasa por `number`.
 */

import { describe, expect, it } from 'vitest'

import {
  esquemaReglaDescuento,
  fraccionDesdePorcentaje,
  porcentajeDesdeFraccion,
  type DatosReglaDescuentoEntrada,
} from '../../../../src/domain/descuentos/reglaSchema'

const MARCA = '11111111-1111-4111-8111-111111111111'
const CATEGORIA = '22222222-2222-4222-8222-222222222222'

function formulario(campos: Partial<DatosReglaDescuentoEntrada> = {}): DatosReglaDescuentoEntrada {
  return {
    nombre: 'Mayorista 20 cajas',
    tipo: 'VOLUMEN_OPERACION',
    medida: 'CAJAS_EQUIVALENTES',
    operador: 'GTE',
    umbral: '20',
    accion_tipo: 'PORCENTAJE',
    accion_valor: '5',
    prioridad: '10',
    acumulable: false,
    alcances: [],
    vigencia_desde: '',
    vigencia_hasta: '',
    ...campos,
  }
}

function camposConError(campos: Partial<DatosReglaDescuentoEntrada>): string[] {
  const resultado = esquemaReglaDescuento.safeParse(formulario(campos))
  return resultado.success ? [] : resultado.error.issues.map((i) => String(i.path[0]))
}

describe('fraccionDesdePorcentaje (TR-02, INV-03)', () => {
  it.each([
    ['12,5', '0.125000'],
    ['12.5', '0.125000'],
    ['5', '0.050000'],
    ['100', '1.000000'],
    ['0,0001', '0.000001'],
  ])('el porcentaje escrito %s viaja como %s', (escrito, fraccion) => {
    expect(fraccionDesdePorcentaje(escrito)).toBe(fraccion)
  })

  it('porcentajeDesdeFraccion es la vuelta: 0.125000 -> 12.5', () => {
    expect(porcentajeDesdeFraccion('0.125000')).toBe('12.5')
    expect(porcentajeDesdeFraccion('0.050000')).toBe('5')
  })
})

describe('esquemaReglaDescuento: salida lista para el comando', () => {
  it('"Cajas >= 20 -> 5 %" sobre toda la venta lleva la fracción y los tipos del comando', () => {
    const datos = esquemaReglaDescuento.parse(formulario())

    expect(datos).toEqual({
      nombre: 'Mayorista 20 cajas',
      tipo: 'VOLUMEN_OPERACION',
      medida: 'CAJAS_EQUIVALENTES',
      operador: 'GTE',
      umbral: '20',
      accion_tipo: 'PORCENTAJE',
      accion_valor: '0.050000',
      prioridad: 10,
      acumulable: false,
      alcances: [],
      vigencia_desde: null,
      vigencia_hasta: null,
    })
  })

  it('el 12,5 escrito llega como "0.125000" y el importe fijo con coma queda con punto', () => {
    expect(esquemaReglaDescuento.parse(formulario({ accion_valor: '12,5' })).accion_valor).toBe('0.125000')
    const fijo = esquemaReglaDescuento.parse(formulario({ accion_tipo: 'IMPORTE_FIJO', accion_valor: '1000,50' }))
    expect(fijo.accion_valor).toBe('1000.50')
  })

  it('una regla de alcance conserva sus alcances y las vigencias salen como instantes', () => {
    const datos = esquemaReglaDescuento.parse(
      formulario({
        tipo: 'VOLUMEN_ALCANCE',
        alcances: [{ tipo: 'MARCA', entidad_id: MARCA }],
        vigencia_desde: '2026-10-10T09:00',
        vigencia_hasta: '2026-12-31T18:00',
      }),
    )

    expect(datos.alcances).toEqual([{ tipo: 'MARCA', entidad_id: MARCA }])
    expect(datos.vigencia_desde).toBe(new Date('2026-10-10T09:00').toISOString())
    expect(datos.vigencia_hasta).toBe(new Date('2026-12-31T18:00').toISOString())
  })

  it('recorta el nombre', () => {
    expect(esquemaReglaDescuento.parse(formulario({ nombre: '  Mayorista  ' })).nombre).toBe('Mayorista')
  })
})

describe('esquemaReglaDescuento: umbral según la medida (DSC-03, INV-04)', () => {
  it.each([
    [{ medida: 'UNIDADES_BASE', umbral: '60' }],
    [{ medida: 'CAJAS_EQUIVALENTES', umbral: '0,5' }],
    [{ medida: 'CAJAS_EQUIVALENTES', umbral: '1.2345' }],
    [{ medida: 'IMPORTE_BRUTO', umbral: '31250,50' }],
  ] as const)('acepta %j', (campos) => {
    expect(camposConError(campos as Partial<DatosReglaDescuentoEntrada>)).toEqual([])
  })

  it.each([
    [{ medida: 'UNIDADES_BASE', umbral: '60,5' }],
    [{ medida: 'UNIDADES_BASE', umbral: '1.5' }],
    [{ medida: 'CAJAS_EQUIVALENTES', umbral: '1.23456' }],
    [{ medida: 'IMPORTE_BRUTO', umbral: '100.005' }],
    [{ umbral: '0' }],
    [{ umbral: '-3' }],
    [{ umbral: '' }],
    [{ umbral: 'abc' }],
    [{ umbral: '1e3' }],
  ] as const)('rechaza %j junto al umbral', (campos) => {
    expect(camposConError(campos as Partial<DatosReglaDescuentoEntrada>)).toContain('umbral')
  })
})

describe('esquemaReglaDescuento: valor según la acción (DSC-04, TR-02)', () => {
  it.each(['0,0001', '5', '100', '12.5'])('acepta el porcentaje %s', (valor) => {
    expect(camposConError({ accion_valor: valor })).toEqual([])
  })

  it.each(['0', '-1', '100,01', '12,34567', '', 'cinco'])('rechaza el porcentaje %s', (valor) => {
    expect(camposConError({ accion_valor: valor })).toContain('accion_valor')
  })

  it.each(['1000', '1000,5', '0.01'])('acepta el importe fijo %s', (valor) => {
    expect(camposConError({ accion_tipo: 'IMPORTE_FIJO', accion_valor: valor })).toEqual([])
  })

  it.each(['0', '1000.005', '-5', ''])('rechaza el importe fijo %s', (valor) => {
    expect(camposConError({ accion_tipo: 'IMPORTE_FIJO', accion_valor: valor })).toContain('accion_valor')
  })
})

describe('esquemaReglaDescuento: prioridad, nombre y listas cerradas (DSC-01, D8)', () => {
  it.each(['1', '10', '2147483647'])('acepta la prioridad %s', (valor) => {
    expect(camposConError({ prioridad: valor })).toEqual([])
  })

  it.each(['0', '-1', '1.5', '1,5', '', 'alta', '2147483648'])('rechaza la prioridad %s', (valor) => {
    expect(camposConError({ prioridad: valor })).toContain('prioridad')
  })

  it('rechaza un nombre vacío o de espacios', () => {
    expect(camposConError({ nombre: '   ' })).toContain('nombre')
  })

  it('rechaza una medida, un operador o una acción fuera de la etapa 1', () => {
    expect(camposConError({ medida: 'PESO' as never })).toContain('medida')
    expect(camposConError({ operador: 'LT' as never })).toContain('operador')
    expect(camposConError({ accion_tipo: 'PRODUCTO_GRATIS' as never })).toContain('accion_tipo')
  })
})

describe('esquemaReglaDescuento: alcances según el tipo (DSC-02, 03 §11)', () => {
  it('una regla de operación completa no lleva alcances', () => {
    expect(camposConError({ alcances: [{ tipo: 'MARCA', entidad_id: MARCA }] })).toContain('alcances')
  })

  it('una regla de alcance necesita al menos uno', () => {
    expect(camposConError({ tipo: 'VOLUMEN_ALCANCE', alcances: [] })).toContain('alcances')
  })

  it('una regla de alcance rechaza un alcance repetido, y acepta mezclar tipos', () => {
    const repetido = [
      { tipo: 'MARCA', entidad_id: MARCA },
      { tipo: 'MARCA', entidad_id: MARCA },
    ] as const
    expect(camposConError({ tipo: 'VOLUMEN_ALCANCE', alcances: [...repetido] })).toContain('alcances')
    expect(
      camposConError({
        tipo: 'VOLUMEN_ALCANCE',
        alcances: [
          { tipo: 'MARCA', entidad_id: MARCA },
          { tipo: 'CATEGORIA', entidad_id: CATEGORIA },
        ],
      }),
    ).toEqual([])
  })

  it('un alcance sin entidad elegida se señala', () => {
    expect(camposConError({ tipo: 'VOLUMEN_ALCANCE', alcances: [{ tipo: 'MARCA', entidad_id: '' }] })).toContain(
      'alcances',
    )
  })
})

describe('esquemaReglaDescuento: vigencia (D16)', () => {
  it('rechaza una vigencia hasta anterior o igual a la desde, junto a la hasta', () => {
    expect(camposConError({ vigencia_desde: '2026-12-01T10:00', vigencia_hasta: '2026-11-01T10:00' })).toContain(
      'vigencia_hasta',
    )
    expect(camposConError({ vigencia_desde: '2026-12-01T10:00', vigencia_hasta: '2026-12-01T10:00' })).toContain(
      'vigencia_hasta',
    )
  })

  it('acepta solo una de las dos, o las dos en orden', () => {
    expect(camposConError({ vigencia_desde: '2026-12-01T10:00' })).toEqual([])
    expect(camposConError({ vigencia_hasta: '2026-12-01T10:00' })).toEqual([])
    expect(camposConError({ vigencia_desde: '2026-11-01T10:00', vigencia_hasta: '2026-12-01T10:00' })).toEqual([])
  })

  it('una fecha ilegible se señala', () => {
    expect(camposConError({ vigencia_desde: 'mañana' })).toContain('vigencia_desde')
  })
})
