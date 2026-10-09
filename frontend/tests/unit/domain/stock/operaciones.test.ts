import { describe, expect, it } from 'vitest'

import type { CodigoPermiso } from '../../../../src/domain/identidad/permisos'
import { formatearCantidad } from '../../../../src/domain/stock/cantidades'
import {
  armarAjuste,
  armarTransferencia,
  cantidadDeLinea,
  cantidadParaLlevarACero,
  esquemaAnulacion,
  enlaceDeOperacion,
  etiquetaDeEstado,
  previsualizarAjuste,
  previsualizarTransferencia,
  puedeAnularAjuste,
  puedeAnularTransferencia,
  rotuloDeMovimiento,
  type LineaDeEntrada,
} from '../../../../src/domain/stock/operaciones'

const ORIGEN = '11111111-1111-4111-8111-111111111111'
const DESTINO = '22222222-2222-4222-8222-222222222222'
const MOTIVO = '33333333-3333-4333-8333-333333333333'
const P1 = '44444444-4444-4444-8444-444444444444'
const P2 = '55555555-5555-4555-8555-555555555555'

function permisos(...codigos: CodigoPermiso[]) {
  return { tiene: (codigo: CodigoPermiso) => codigos.includes(codigo) }
}

function entrada(cambios: Partial<LineaDeEntrada> = {}): LineaDeEntrada {
  return {
    productoId: P1,
    cajas: '8',
    unidades: '0',
    negativa: false,
    unidadesPorCaja: 6,
    nombrePresentacion: 'Caja x6',
    ...cambios,
  }
}

describe('cantidadDeLinea (CAT-08, INV-04)', () => {
  it('convierte cajas + unidades a unidad base con enteros', () => {
    expect(cantidadDeLinea(entrada({ cajas: '8', unidades: '0' }))).toEqual({ ok: true, cantidadBase: 48 })
    expect(cantidadDeLinea(entrada({ cajas: '2', unidades: '3' }))).toEqual({ ok: true, cantidadBase: 15 })
  })

  it('una línea negativa (faltante) conserva el signo', () => {
    expect(cantidadDeLinea(entrada({ cajas: '1', unidades: '0', negativa: true }))).toEqual({
      ok: true,
      cantidadBase: -6,
    })
    expect(cantidadDeLinea(entrada({ cajas: '0', unidades: '2', negativa: true }))).toEqual({
      ok: true,
      cantidadBase: -2,
    })
  })

  it('sin presentación de referencia solo cuentan las unidades', () => {
    expect(
      cantidadDeLinea(entrada({ unidadesPorCaja: null, nombrePresentacion: null, cajas: '', unidades: '7' })),
    ).toEqual({ ok: true, cantidadBase: 7 })
  })

  it('rechaza partes que no son enteros no negativos', () => {
    expect(cantidadDeLinea(entrada({ cajas: '1.5' })).ok).toBe(false)
    expect(cantidadDeLinea(entrada({ unidades: '-2' })).ok).toBe(false)
    expect(cantidadDeLinea(entrada({ unidades: 'abc' })).ok).toBe(false)
  })

  it('rechaza una línea sin producto', () => {
    expect(cantidadDeLinea(entrada({ productoId: '' }))).toEqual({ ok: false, mensaje: 'Elegí un producto.' })
  })
})

describe('saldo resultante por línea (D7, D11)', () => {
  it('transferencia: resta en el origen, suma en el destino y marca el negativo', () => {
    expect(previsualizarTransferencia(120, 0, 48)).toEqual({
      origen: { actual: 120, resultante: 72, negativo: false },
      destino: { actual: 0, resultante: 48, negativo: false },
    })
    expect(previsualizarTransferencia(48, 10, 60)).toEqual({
      origen: { actual: 48, resultante: -12, negativo: true },
      destino: { actual: 10, resultante: 70, negativo: false },
    })
  })

  it('ajuste: suma con signo y marca el negativo', () => {
    expect(previsualizarAjuste(120, -6)).toEqual({ actual: 120, resultante: 114, negativo: false })
    expect(previsualizarAjuste(10, -11)).toEqual({ actual: 10, resultante: -1, negativo: true })
    expect(previsualizarAjuste(-12, 12)).toEqual({ actual: -12, resultante: 0, negativo: false })
  })

  it('el resultado se muestra en cajas + unidades con signo', () => {
    const referencia = { unidades: 6, nombre: 'Caja' }
    expect(formatearCantidad(previsualizarAjuste(120, -6).resultante, referencia)).toBe('114 unidades (19 Caja)')
    expect(formatearCantidad(previsualizarTransferencia(48, 0, 60).origen.resultante, referencia)).toBe(
      '-12 unidades (-2 Caja)',
    )
  })
})

describe('cantidadParaLlevarACero (D2)', () => {
  it('un saldo negativo precarga la cantidad positiva que lo lleva a cero', () => {
    expect(cantidadParaLlevarACero(-12)).toBe(12)
    expect(cantidadParaLlevarACero(-1)).toBe(1)
  })

  it('un saldo cero o positivo no precarga nada', () => {
    expect(cantidadParaLlevarACero(0)).toBeNull()
    expect(cantidadParaLlevarACero(5)).toBeNull()
  })
})

describe('armarTransferencia', () => {
  const base = { origenId: ORIGEN, destinoId: DESTINO, observacion: '' }

  it('arma el cuerpo con cantidades en unidad base y sin observación vacía', () => {
    expect(
      armarTransferencia({ ...base, lineas: [entrada(), entrada({ productoId: P2, cajas: '0', unidades: '5' })] }),
    ).toEqual({
      ok: true,
      cuerpo: {
        ubicacion_origen_id: ORIGEN,
        ubicacion_destino_id: DESTINO,
        lineas: [
          { producto_id: P1, cantidad_base: 48 },
          { producto_id: P2, cantidad_base: 5 },
        ],
      },
    })
  })

  it('recorta la observación y la manda si tiene texto', () => {
    const resultado = armarTransferencia({ ...base, observacion: '  carga del lunes ', lineas: [entrada()] })
    expect(resultado).toMatchObject({ ok: true, cuerpo: { observacion: 'carga del lunes' } })
  })

  it('exige origen distinto de destino', () => {
    expect(armarTransferencia({ ...base, destinoId: ORIGEN, lineas: [entrada()] })).toEqual({
      ok: false,
      mensaje: 'El origen y el destino tienen que ser distintos.',
    })
  })

  it('exige origen y destino elegidos', () => {
    expect(armarTransferencia({ ...base, origenId: '', lineas: [entrada()] })).toMatchObject({
      ok: false,
      mensaje: 'Elegí el origen.',
    })
    expect(armarTransferencia({ ...base, destinoId: '', lineas: [entrada()] })).toMatchObject({
      ok: false,
      mensaje: 'Elegí el destino.',
    })
  })

  it('exige de 1 a 200 líneas', () => {
    expect(armarTransferencia({ ...base, lineas: [] })).toMatchObject({
      ok: false,
      mensaje: 'Agregá al menos una línea.',
    })
    const demasiadas = Array.from({ length: 201 }, (_, i) => entrada({ productoId: `p-${String(i)}` }))
    expect(armarTransferencia({ ...base, lineas: demasiadas })).toMatchObject({
      ok: false,
      mensaje: 'Una operación admite hasta 200 líneas.',
    })
    const justas = Array.from({ length: 200 }, (_, i) => entrada({ productoId: `p-${String(i)}` }))
    expect(armarTransferencia({ ...base, lineas: justas }).ok).toBe(true)
  })

  it('rechaza un producto repetido señalando la línea', () => {
    expect(armarTransferencia({ ...base, lineas: [entrada(), entrada({ cajas: '1' })] })).toEqual({
      ok: false,
      mensaje: 'Un producto no puede repetirse en la misma operación.',
      indice: 1,
    })
  })

  it('la cantidad tiene que ser mayor que cero y entera', () => {
    expect(armarTransferencia({ ...base, lineas: [entrada({ cajas: '0', unidades: '0' })] })).toEqual({
      ok: false,
      mensaje: 'La cantidad tiene que ser mayor que cero.',
      indice: 0,
    })
    const decimal = armarTransferencia({ ...base, lineas: [entrada(), entrada({ productoId: P2, unidades: '1,5' })] })
    expect(decimal).toMatchObject({ ok: false, indice: 1 })
  })

  it('una transferencia no admite línea negativa: la cantidad siempre sale positiva', () => {
    const resultado = armarTransferencia({ ...base, lineas: [entrada({ negativa: true })] })
    expect(resultado).toMatchObject({ ok: true, cuerpo: { lineas: [{ cantidad_base: 48 }] } })
  })

  it('la observación admite hasta 500 caracteres', () => {
    expect(armarTransferencia({ ...base, observacion: 'x'.repeat(500), lineas: [entrada()] }).ok).toBe(true)
    expect(armarTransferencia({ ...base, observacion: 'x'.repeat(501), lineas: [entrada()] })).toMatchObject({
      ok: false,
      mensaje: 'La observación admite hasta 500 caracteres.',
    })
  })
})

describe('armarAjuste', () => {
  const base = { ubicacionId: ORIGEN, motivoId: MOTIVO, observacion: '' }

  it('arma el cuerpo con líneas con signo', () => {
    expect(
      armarAjuste({
        ...base,
        lineas: [entrada({ cajas: '1', negativa: true }), entrada({ productoId: P2, cajas: '0', unidades: '4' })],
      }),
    ).toEqual({
      ok: true,
      cuerpo: {
        ubicacion_id: ORIGEN,
        motivo_id: MOTIVO,
        lineas: [
          { producto_id: P1, cantidad_base: -6 },
          { producto_id: P2, cantidad_base: 4 },
        ],
      },
    })
  })

  it('el motivo es obligatorio', () => {
    expect(armarAjuste({ ...base, motivoId: '', lineas: [entrada()] })).toMatchObject({
      ok: false,
      mensaje: 'Elegí un motivo.',
    })
  })

  it('la ubicación es obligatoria', () => {
    expect(armarAjuste({ ...base, ubicacionId: '', lineas: [entrada()] })).toMatchObject({
      ok: false,
      mensaje: 'Elegí la ubicación.',
    })
  })

  it('la cantidad no puede ser cero', () => {
    expect(armarAjuste({ ...base, lineas: [entrada({ cajas: '0', unidades: '0' })] })).toEqual({
      ok: false,
      mensaje: 'La cantidad no puede ser cero.',
      indice: 0,
    })
  })

  it('1 a 200 líneas, sin producto repetido y observación hasta 500', () => {
    expect(armarAjuste({ ...base, lineas: [] })).toMatchObject({ ok: false, mensaje: 'Agregá al menos una línea.' })
    expect(armarAjuste({ ...base, lineas: [entrada(), entrada({ negativa: true })] })).toMatchObject({
      ok: false,
      indice: 1,
    })
    expect(armarAjuste({ ...base, observacion: 'x'.repeat(501), lineas: [entrada()] })).toMatchObject({ ok: false })
    expect(armarAjuste({ ...base, observacion: 'rotura en traslado', lineas: [entrada()] })).toMatchObject({
      ok: true,
      cuerpo: { observacion: 'rotura en traslado' },
    })
  })
})

describe('esquemaAnulacion', () => {
  it('exige un motivo', () => {
    const vacio = esquemaAnulacion.safeParse({ motivoId: '' })
    expect(vacio.success).toBe(false)
    expect(vacio.error?.issues[0]?.message).toBe('Elegí un motivo.')
    expect(esquemaAnulacion.safeParse({ motivoId: MOTIVO }).success).toBe(true)
  })
})

describe('quién puede anular (D5, D5.4; mismas reglas que el dominio del backend)', () => {
  const CREADOR = 'usuario-creador'
  const OTRO = 'usuario-otro'

  it('una transferencia propia se anula con TRANSFERIR_STOCK', () => {
    expect(puedeAnularTransferencia(CREADOR, CREADOR, permisos('TRANSFERIR_STOCK'))).toBe(true)
  })

  it('una transferencia ajena exige además ANULAR_TRANSFERENCIA', () => {
    expect(puedeAnularTransferencia(CREADOR, OTRO, permisos('TRANSFERIR_STOCK'))).toBe(false)
    expect(puedeAnularTransferencia(CREADOR, OTRO, permisos('TRANSFERIR_STOCK', 'ANULAR_TRANSFERENCIA'))).toBe(true)
  })

  it('TRANSFERIR_STOCK es siempre necesario: ANULAR_TRANSFERENCIA sola no alcanza (D5.4)', () => {
    expect(puedeAnularTransferencia(CREADOR, OTRO, permisos('ANULAR_TRANSFERENCIA'))).toBe(false)
    expect(puedeAnularTransferencia(CREADOR, CREADOR, permisos())).toBe(false)
  })

  it('un ajuste, propio o ajeno, se anula con AJUSTAR_STOCK', () => {
    expect(puedeAnularAjuste(permisos('AJUSTAR_STOCK'))).toBe(true)
    expect(puedeAnularAjuste(permisos('TRANSFERIR_STOCK', 'ANULAR_TRANSFERENCIA'))).toBe(false)
  })
})

describe('etiquetaDeEstado', () => {
  it('rotula los dos estados de una operación', () => {
    expect(etiquetaDeEstado('CONFIRMADA')).toBe('Confirmada')
    expect(etiquetaDeEstado('ANULADA')).toBe('Anulada')
  })

  it('un estado desconocido se muestra tal cual', () => {
    expect(etiquetaDeEstado('PENDIENTE')).toBe('PENDIENTE')
  })
})

describe('rotuloDeMovimiento (kardex, D5.1)', () => {
  it('los movimientos inversos de una anulación se rotulan como tales', () => {
    expect(rotuloDeMovimiento('TRANSFERENCIA_SALIDA', 'ANULACION_TRANSFERENCIA')).toBe('Anulación de transferencia')
    expect(rotuloDeMovimiento('TRANSFERENCIA_ENTRADA', 'ANULACION_TRANSFERENCIA')).toBe('Anulación de transferencia')
    expect(rotuloDeMovimiento('AJUSTE', 'ANULACION_AJUSTE_STOCK')).toBe('Anulación de ajuste')
  })

  it('el resto usa la etiqueta de su tipo', () => {
    expect(rotuloDeMovimiento('TRANSFERENCIA_SALIDA', 'TRANSFERENCIA')).toBe('Transferencia (salida)')
    expect(rotuloDeMovimiento('AJUSTE', 'AJUSTE_STOCK')).toBe('Ajuste')
    expect(rotuloDeMovimiento('STOCK_INICIAL', 'STOCK_INICIAL')).toBe('Stock inicial')
  })
})

describe('enlaceDeOperacion (kardex, ADR-027, D7)', () => {
  const ID = '66666666-6666-4666-8666-666666666666'

  it('una transferencia (o su anulación) enlaza al detalle solo con TRANSFERIR_STOCK', () => {
    expect(enlaceDeOperacion('TRANSFERENCIA', ID, permisos('TRANSFERIR_STOCK'))).toBe(`/admin/stock/transferencias/${ID}`)
    expect(enlaceDeOperacion('ANULACION_TRANSFERENCIA', ID, permisos('TRANSFERIR_STOCK'))).toBe(
      `/admin/stock/transferencias/${ID}`,
    )
    expect(enlaceDeOperacion('TRANSFERENCIA', ID, permisos('AJUSTAR_STOCK'))).toBeNull()
  })

  it('un ajuste (o su anulación) enlaza al detalle solo con AJUSTAR_STOCK', () => {
    expect(enlaceDeOperacion('AJUSTE_STOCK', ID, permisos('AJUSTAR_STOCK'))).toBe(`/admin/stock/ajustes/${ID}`)
    expect(enlaceDeOperacion('ANULACION_AJUSTE_STOCK', ID, permisos('AJUSTAR_STOCK'))).toBe(`/admin/stock/ajustes/${ID}`)
    expect(enlaceDeOperacion('AJUSTE_STOCK', ID, permisos('TRANSFERIR_STOCK'))).toBeNull()
  })

  it('un movimiento de otro origen no enlaza a nada', () => {
    expect(enlaceDeOperacion('COMPRA', ID, permisos('TRANSFERIR_STOCK', 'AJUSTAR_STOCK'))).toBeNull()
    expect(enlaceDeOperacion('STOCK_INICIAL', ID, permisos('TRANSFERIR_STOCK', 'AJUSTAR_STOCK'))).toBeNull()
  })
})
