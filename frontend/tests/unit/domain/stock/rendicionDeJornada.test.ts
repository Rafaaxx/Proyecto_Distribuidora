import { describe, expect, it } from 'vitest'

import {
  armarConteo,
  armarDevolucion,
  contadoEnBase,
  precargarDevolucion,
  totalDeDevolucion,
  textoDeConfirmacionDeRendicion,
  textoDeConteoIncompleto,
  textoDeDevolucion,
  type FilaDeConteo,
} from '../../../../src/domain/stock/rendicion'

/**
 * Change 24, tareas 12.1 y 13.1 (D2, D6, D9; cita RUT-06, RUT-08, CAT-08, INV-04): lo que la pantalla
 * de conteo y el diálogo de cierre arman antes de enviar. Lógica pura; el servidor valida siempre.
 */
const A = 'prod-a'
const B = 'prod-b'
const C = 'prod-c'

function fila(productoId: string, esperado: number, cajas: string, unidades: string, cambios: Partial<FilaDeConteo> = {}): FilaDeConteo {
  return { productoId, esperado, cajas, unidades, unidadesPorCaja: null, nombrePresentacion: null, ...cambios }
}

describe('armarConteo (D2; RUT-06, CAT-08, INV-04)', () => {
  it('convierte cajas y unidades a unidad base y lleva el esperado que vio quien contó', () => {
    const r = armarConteo([fila(A, 40, '6', '1', { unidadesPorCaja: 6, nombrePresentacion: 'Caja x6' })])

    expect(r).toEqual({
      ok: true,
      lineas: [{ producto_id: A, cantidad_contada: 37, cantidad_esperada: 40 }],
      conDiferencias: 1,
    })
  })

  it('un producto sin referencia se cuenta en unidades base y una diferencia cero no cuenta como diferencia', () => {
    const r = armarConteo([fila(A, 12, '', '12'), fila(B, 5, '', '3')])

    expect(r).toMatchObject({ ok: true, conDiferencias: 1 })
    expect(r.ok && r.lineas.map((l) => l.cantidad_contada)).toEqual([12, 3])
  })

  it('un cero escrito es un conteo válido (faltante total); un campo vacío no es contar', () => {
    const conCero = armarConteo([fila(A, 8, '', '0')])
    const sinContar = armarConteo([fila(A, 8, '', ''), fila(B, 3, '', '3')])

    expect(conCero).toEqual({ ok: true, lineas: [{ producto_id: A, cantidad_contada: 0, cantidad_esperada: 8 }], conDiferencias: 1 })
    expect(sinContar).toEqual({ ok: false, sinContar: [A], invalidas: [] })
  })

  it('un valor que no es un entero no negativo se marca como inválido con su mensaje', () => {
    const r = armarConteo([fila(A, 8, '', '2,5'), fila(B, 3, '', '-1'), fila(C, 1, '', '1')])

    expect(r.ok).toBe(false)
    expect(!r.ok && r.invalidas.map((i) => i.productoId)).toEqual([A, B])
    expect(!r.ok && r.invalidas[0]?.mensaje).toMatch(/entero mayor o igual a cero/)
    expect(!r.ok && r.sinContar).toEqual([])
  })

  it('sin filas el conteo vacío es válido (conjunto vacío)', () => {
    expect(armarConteo([])).toEqual({ ok: true, lineas: [], conDiferencias: 0 })
  })
})

describe('textoDeConfirmacionDeRendicion (D9, aprobados en 0.2)', () => {
  it.each([
    [0, '¿Registrar la rendición sin diferencias?'],
    [3, '¿Registrar la rendición con 3 diferencias?'],
    [1, '¿Registrar la rendición con 1 diferencia?'],
  ])('%i diferencias dicen «%s»', (n, esperado) => {
    expect(textoDeConfirmacionDeRendicion(n)).toBe(esperado)
  })
})

describe('devolución del remanente (D6, D9; RUT-08, STK-07)', () => {
  it('se precarga con todo lo contado: cada producto con contado mayor que cero, en cajas y unidades', () => {
    const filas = precargarDevolucion(
      [
        { productoId: A, contado: 37 },
        { productoId: B, contado: 0 },
        { productoId: C, contado: 5 },
      ],
      new Map([[A, { unidades: 6, nombre: 'Caja x6' }]]),
    )

    expect(filas).toEqual([
      { productoId: A, cajas: '6', unidades: '1', unidadesPorCaja: 6, nombrePresentacion: 'Caja x6' },
      { productoId: C, cajas: '', unidades: '5', unidadesPorCaja: null, nombrePresentacion: null },
    ])
  })

  it('con una referencia de 1 unidad (Botella) precarga todo en unidades y deja las cajas vacías, sin duplicar la cantidad', () => {
    const filas = precargarDevolucion([{ productoId: A, contado: 97 }], new Map([[A, { unidades: 1, nombre: 'Botella' }]]))

    expect(filas).toEqual([{ productoId: A, cajas: '', unidades: '97', unidadesPorCaja: null, nombrePresentacion: null }])
    const r = armarDevolucion('dep-1', filas)
    expect(r).toEqual({ ok: true, devolucion: { ubicacion_destino_id: 'dep-1', lineas: [{ producto_id: A, cantidad_base: 97 }] } })
  })

  it('con una referencia de 6 unidades y resto separa cajas y unidades; sin referencia solo unidades', () => {
    const filas = precargarDevolucion(
      [
        { productoId: A, contado: 13 },
        { productoId: B, contado: 6 },
      ],
      new Map([
        [A, { unidades: 6, nombre: 'Caja x6' }],
        [B, { unidades: 6, nombre: 'Caja x6' }],
      ]),
    )

    expect(filas.map((f) => [f.cajas, f.unidades])).toEqual([
      ['2', '1'],
      ['1', '0'],
    ])
  })

  it('arma las líneas con la cantidad en unidad base y omite las que quedaron en cero', () => {
    const r = armarDevolucion('dep-1', [
      { productoId: A, cajas: '2', unidades: '3', unidadesPorCaja: 6, nombrePresentacion: 'Caja x6' },
      { productoId: B, cajas: '', unidades: '0', unidadesPorCaja: null, nombrePresentacion: null },
      { productoId: C, cajas: '', unidades: '5', unidadesPorCaja: null, nombrePresentacion: null },
    ])

    expect(r).toEqual({
      ok: true,
      devolucion: {
        ubicacion_destino_id: 'dep-1',
        lineas: [
          { producto_id: A, cantidad_base: 15 },
          { producto_id: C, cantidad_base: 5 },
        ],
      },
    })
  })

  it('sin destino no hay devolución; con destino y todo en cero se pide una cantidad', () => {
    expect(armarDevolucion('', [{ productoId: A, cajas: '', unidades: '4', unidadesPorCaja: null, nombrePresentacion: null }])).toEqual({
      ok: true,
      devolucion: null,
    })
    expect(armarDevolucion('dep-1', [{ productoId: A, cajas: '', unidades: '0', unidadesPorCaja: null, nombrePresentacion: null }])).toEqual({
      ok: false,
      mensaje: 'Indicá la cantidad que se devuelve de al menos un producto.',
    })
  })

  it('una cantidad inválida detiene el armado con su mensaje', () => {
    const r = armarDevolucion('dep-1', [{ productoId: A, cajas: '', unidades: 'x', unidadesPorCaja: null, nombrePresentacion: null }])

    expect(r.ok).toBe(false)
    expect(!r.ok && r.mensaje).toMatch(/entero mayor o igual a cero/)
  })

  it.each([
    [3, 'Depósito central', 'Se transfieren 3 productos a Depósito central.'],
    [1, 'Depósito central', 'Se transfiere 1 producto a Depósito central.'],
  ])('el texto de %i productos dice «%s»', (n, destino, esperado) => {
    expect(textoDeDevolucion(n, destino)).toBe(esperado)
  })
})

describe('textoDeConteoIncompleto (D11, aprobado en 0.2; RUT-06)', () => {
  it.each([
    [['Vino A'], 'Falta contar: Vino A.'],
    [['Vino A', 'Gaseosa Cola'], 'Falta contar: Vino A, Gaseosa Cola.'],
  ])('%j dice «%s»', (nombres, esperado) => {
    expect(textoDeConteoIncompleto(nombres)).toBe(esperado)
  })

  it('sin nombres conocidos cae en el texto de reserva', () => {
    expect(textoDeConteoIncompleto([])).toBe('Falta contar algún producto.')
  })
})

describe('contadoEnBase (D2; INV-04)', () => {
  it.each([
    [fila(A, 40, '6', '1', { unidadesPorCaja: 6 }), 37],
    [fila(A, 40, '', '0'), 0],
    [fila(A, 40, '', ''), null],
    [fila(A, 40, '', 'abc'), null],
  ])('%j da %s', (entrada, esperado) => {
    expect(contadoEnBase(entrada)).toBe(esperado)
  })
})

describe('totalDeDevolucion (D6; CAT-08, INV-04)', () => {
  const base = { productoId: A, unidadesPorCaja: null, nombrePresentacion: null }

  it('devuelve el total en unidad base de lo escrito', () => {
    expect(totalDeDevolucion({ ...base, cajas: '', unidades: '97' })).toBe(97)
    expect(totalDeDevolucion({ ...base, cajas: '2', unidades: '3', unidadesPorCaja: 6, nombrePresentacion: 'Caja x6' })).toBe(15)
  })

  it('es null si lo escrito no es una cantidad válida', () => {
    expect(totalDeDevolucion({ ...base, cajas: '', unidades: 'x' })).toBeNull()
    expect(totalDeDevolucion({ ...base, cajas: '', unidades: '' })).toBe(0)
  })
})
