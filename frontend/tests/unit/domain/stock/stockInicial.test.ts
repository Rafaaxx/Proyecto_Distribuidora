import { describe, expect, it } from 'vitest'

import {
  armarEnvio,
  previsualizarPromedio,
  resolverOperationId,
  validarLinea,
  type LineaDeFormulario,
} from '../../../../src/domain/stock/stockInicial'

const P1 = '11111111-1111-4111-8111-111111111111'
const P2 = '22222222-2222-4222-8222-222222222222'
const UBICACION = '33333333-3333-4333-8333-333333333333'

function linea(cambios: Partial<LineaDeFormulario> = {}): LineaDeFormulario {
  return { productoId: P1, sentido: 'INGRESO', cajas: '5', unidades: '1', costo: '1000.50', ...cambios }
}

/** D5, D6, D4: una línea se escribe en cajas + unidades, se convierte a base
 * entera, y el costo viaja como string (solo en un ingreso). */
describe('validarLinea', () => {
  it('un ingreso convierte cajas + unidades a base y conserva el costo como string', () => {
    expect(validarLinea(linea(), 6)).toEqual({
      ok: true,
      payload: { producto_id: P1, cantidad_base: 31, costo_unitario: '1000.50' },
    })
  })

  it('una corrección lleva cantidad negativa y ningún costo', () => {
    expect(validarLinea(linea({ sentido: 'CORRECCION', cajas: '2', unidades: '0', costo: '' }), 6)).toEqual({
      ok: true,
      payload: { producto_id: P1, cantidad_base: -12 },
    })
  })

  it('los campos vacíos cuentan como cero y sin referencia solo valen las unidades', () => {
    expect(validarLinea(linea({ cajas: '', unidades: '7' }), null)).toEqual({
      ok: true,
      payload: { producto_id: P1, cantidad_base: 7, costo_unitario: '1000.50' },
    })
  })

  it.each([
    [{ productoId: '' }],
    [{ cajas: '0', unidades: '0' }],
    [{ cajas: '1.5' }],
    [{ unidades: '-2' }],
    [{ costo: '' }],
    [{ costo: '0' }],
    [{ costo: '1.1234567' }],
    [{ costo: '10,5' }],
  ])('rechaza %j', (cambios) => {
    const resultado = validarLinea(linea(cambios), 6)
    expect(resultado.ok).toBe(false)
    if (!resultado.ok) expect(resultado.mensaje.length).toBeGreaterThan(0)
  })
})

describe('validarLinea con el nombre de la presentación', () => {
  it('el mensaje de una parte inválida usa el nombre; sin nombre dice Cajas', () => {
    expect(validarLinea(linea({ cajas: '1.5' }), 6, 'Caja x6')).toEqual({
      ok: false,
      mensaje: 'Caja x6: ingresá un entero mayor o igual a cero.',
    })
    expect(validarLinea(linea({ cajas: 'x' }), 12, 'Pack x12')).toEqual({
      ok: false,
      mensaje: 'Pack x12: ingresá un entero mayor o igual a cero.',
    })
    expect(validarLinea(linea({ cajas: '1.5' }), null)).toEqual({
      ok: false,
      mensaje: 'Cajas: ingresá un entero mayor o igual a cero.',
    })
  })

  it('armarEnvio propaga el nombre al mensaje de la línea', () => {
    const envio = armarEnvio(UBICACION, [
      { linea: linea({ cajas: '1.5' }), unidadesPorCaja: 6, nombrePresentacion: 'Caja x6' },
    ])
    expect(envio).toEqual({
      ok: false,
      mensaje: 'Caja x6: ingresá un entero mayor o igual a cero.',
      indice: 0,
    })
  })
})

describe('armarEnvio', () => {
  it('arma el cuerpo con la ubicación y las líneas convertidas', () => {
    const envio = armarEnvio(UBICACION, [
      { linea: linea(), unidadesPorCaja: 6 },
      { linea: linea({ productoId: P2, cajas: '0', unidades: '10', costo: '3' }), unidadesPorCaja: null },
    ])
    expect(envio).toEqual({
      ok: true,
      cuerpo: {
        ubicacion_id: UBICACION,
        lineas: [
          { producto_id: P1, cantidad_base: 31, costo_unitario: '1000.50' },
          { producto_id: P2, cantidad_base: 10, costo_unitario: '3' },
        ],
      },
    })
  })

  it('rechaza un producto repetido y una lista vacía', () => {
    const repetido = armarEnvio(UBICACION, [
      { linea: linea(), unidadesPorCaja: 6 },
      { linea: linea(), unidadesPorCaja: 6 },
    ])
    expect(repetido.ok).toBe(false)
    expect(armarEnvio(UBICACION, []).ok).toBe(false)
  })

  it('rechaza más de doscientas líneas', () => {
    const muchas = Array.from({ length: 201 }, (_, i) => ({
      linea: linea({ productoId: `p-${String(i)}` }),
      unidadesPorCaja: 6,
    }))
    expect(armarEnvio(UBICACION, muchas).ok).toBe(false)
  })

  it('informa la línea inválida por su posición', () => {
    const envio = armarEnvio(UBICACION, [
      { linea: linea(), unidadesPorCaja: 6 },
      { linea: linea({ productoId: P2, costo: '' }), unidadesPorCaja: 6 },
    ])
    expect(envio.ok).toBe(false)
    if (!envio.ok) expect(envio.indice).toBe(1)
  })
})

/** CST-11 (`01` §6.2): la previsualización usa la misma función que los fixtures. */
describe('previsualizarPromedio', () => {
  it('60 a 1000 más 60 a 1100 dan 1050', () => {
    expect(previsualizarPromedio({ stockTotal: 60, promedio: '1000.000000', cantidadBase: 60, costo: '1100' })).toBe(
      '1050.000000',
    )
  })

  it('con stock previo 0 el promedio es el costo del ingreso', () => {
    expect(previsualizarPromedio({ stockTotal: 0, promedio: null, cantidadBase: 10, costo: '7.5' })).toBe('7.500000')
  })

  it('una corrección no cambia el promedio', () => {
    expect(
      previsualizarPromedio({ stockTotal: 120, promedio: '1050.000000', cantidadBase: -12, costo: null }),
    ).toBe('1050.000000')
  })

  it('devuelve null si no se puede calcular (costo inválido o faltante)', () => {
    expect(previsualizarPromedio({ stockTotal: 60, promedio: '1000.000000', cantidadBase: 5, costo: 'abc' })).toBeNull()
    expect(previsualizarPromedio({ stockTotal: 60, promedio: '1000.000000', cantidadBase: 5, costo: null })).toBeNull()
  })
})

/** INV-06, TR-07: el reintento de lo mismo que se cortó por la red reenvía el
 * mismo `operation_id`; cambiar cualquier dato es otra operación. */
describe('resolverOperationId', () => {
  const cuerpo = armarEnvio(UBICACION, [{ linea: linea(), unidadesPorCaja: 6 }])
  if (!cuerpo.ok) throw new Error('el cuerpo de prueba tiene que ser válido')

  it('reutiliza el del envío pendiente si el cuerpo es el mismo', () => {
    const pendiente = { cuerpo: cuerpo.cuerpo, operationId: 'op-1' }
    expect(resolverOperationId(pendiente, { ...cuerpo.cuerpo }, () => 'op-2')).toBe('op-1')
  })

  it('genera uno nuevo si no hay pendiente o si cambió algún dato', () => {
    expect(resolverOperationId(null, cuerpo.cuerpo, () => 'op-2')).toBe('op-2')
    const otro = armarEnvio(UBICACION, [{ linea: linea({ unidades: '2' }), unidadesPorCaja: 6 }])
    if (!otro.ok) throw new Error('inválido')
    expect(resolverOperationId({ cuerpo: cuerpo.cuerpo, operationId: 'op-1' }, otro.cuerpo, () => 'op-3')).toBe('op-3')
  })
})
