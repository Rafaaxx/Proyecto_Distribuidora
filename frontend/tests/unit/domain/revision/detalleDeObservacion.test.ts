import { describe, expect, it } from 'vitest'

import {
  detalleDeObservacion,
  etiquetaDeObservacion,
  nombresDeAviso,
} from '../../../../src/domain/revision/detalleDeObservacion'

/**
 * Change 25, tarea 13.1 (D3, D12; SYN-07, DSC-09, CRE-09): cada código de la bandeja se muestra con su etiqueta y
 * su detalle legible; los importes salen de `decimal.js` con el formato de `lib/money.ts`; un código desconocido
 * muestra el código.
 */
describe('etiquetaDeObservacion (SYN-07)', () => {
  it('traduce los códigos que faltaban (D12)', () => {
    expect(etiquetaDeObservacion('UBICACION_TOMADA_AL_SINCRONIZAR')).toBe('Ubicación tomada al sincronizar')
    expect(etiquetaDeObservacion('JORNADA_RENDIDA')).toBe('Llegó después de la rendición')
    expect(etiquetaDeObservacion('PRODUCTO_DESACTIVADO')).toBe('Producto desactivado')
  })

  it('conserva las etiquetas que ya existían', () => {
    expect(etiquetaDeObservacion('STOCK_NEGATIVO')).toBe('Stock negativo')
    expect(etiquetaDeObservacion('EXCESO_CREDITO_DETECTADO_SYNC')).toBe('Exceso de crédito detectado al sincronizar')
  })

  it('un código desconocido muestra el código', () => {
    expect(etiquetaDeObservacion('CODIGO_NUEVO')).toBe('CODIGO_NUEVO')
  })
})

describe('detalleDeObservacion: descuentos (DSC-09)', () => {
  it('cada causa de DESCUENTO_DIFIERE tiene su texto', () => {
    const detalle = {
      causas: [
        { causa: 'CALCULO', linea_id: 'l1', esperado: [], calculado: [] },
        { causa: 'TOPE', porcentaje_maximo: '0.150000', tope: '0.100000' },
        { causa: 'AUTORIZADOR_SIN_PERMISO', porcentaje_maximo: '0.125000', tope: '0.100000' },
        { causa: 'PERMISO' },
        { causa: 'DESHABILITADO' },
        { causa: 'MOTIVO' },
      ],
    }

    expect(detalleDeObservacion('DESCUENTO_DIFIERE', detalle)).toEqual([
      'Causa: el cálculo del teléfono no coincide con el del sistema',
      'Causa: supera el tope (15 % con tope 10 %)',
      'Causa: el autorizador no tenía el permiso (12,5 % con tope 10 %)',
      'Causa: el vendedor no tenía permiso de descuento',
      'Causa: el descuento manual estaba deshabilitado',
      'Causa: faltó el motivo',
    ])
  })

  it('AUTORIZACION_OFFLINE dice quién autorizó y si conserva el permiso', () => {
    const base = { tipo: 'DESCUENTO', resolucion: 'PIN_SUPERVISOR', autorizador_id: 'u1' }
    const nombres = { usuarios: new Map([['u1', 'Marta']]) }

    expect(detalleDeObservacion('AUTORIZACION_OFFLINE', { ...base, autorizador_con_permiso: true }, nombres)).toEqual([
      'Autorizó Marta (descuento, con el PIN de un supervisor); conserva el permiso',
    ])
    expect(
      detalleDeObservacion('AUTORIZACION_OFFLINE', { ...base, tipo: 'CREDITO', resolucion: 'PERMISO_PROPIO', autorizador_con_permiso: false }, nombres),
    ).toEqual(['Autorizó Marta (crédito, con su propio permiso); ya no tiene el permiso'])
  })
})

describe('detalleDeObservacion: crédito, cobranza y jornada (CRE-09, SYN-07)', () => {
  it('EXCESO_CREDITO_DETECTADO_SYNC compara el teléfono con el sistema, con importes exactos', () => {
    const detalle = {
      dispositivo: { limite: '100000.00', saldo_considerado: '40000.00', disponible: '60000.00', exceso: '0.00' },
      servidor: { limite: '100000.00', saldo_considerado: '130000.10', disponible: '0.00', exceso: '45000.55' },
    }

    expect(detalleDeObservacion('EXCESO_CREDITO_DETECTADO_SYNC', detalle)).toEqual([
      'Teléfono: disponible $ 60.000,00, exceso $ 0,00 · Sistema: disponible $ 0,00, exceso $ 45.000,55',
    ])
  })

  it('CONSUMIDOR_FINAL_CON_DEUDA muestra el total y lo cobrado', () => {
    expect(detalleDeObservacion('CONSUMIDOR_FINAL_CON_DEUDA', { total: '1500.50', cobranza: '500.00' })).toEqual([
      'Total $ 1.500,50 · cobrado $ 500,00',
    ])
  })

  it('MEDIO_INACTIVO y REFERENCIA_FALTANTE muestran el medio y el importe', () => {
    const detalle = { medio: 0, medio_pago_id: 'm1', nombre: 'Transferencia', importe: '2500.00' }

    expect(detalleDeObservacion('MEDIO_INACTIVO', detalle)).toEqual(['Medio Transferencia: $ 2.500,00'])
    expect(detalleDeObservacion('REFERENCIA_FALTANTE', { ...detalle, nombre: 'Cheque', importe: '10.00' })).toEqual([
      'Medio Cheque: $ 10,00',
    ])
  })

  it('JORNADA_RENDIDA dice cuándo se rindió', () => {
    expect(detalleDeObservacion('JORNADA_RENDIDA', { jornada_id: 'j1', rendida_en: '2026-11-05T15:30:00+00:00' })).toEqual([
      expect.stringMatching(/^Rendida el 05\/11\/2026/),
    ])
  })

  it('STOCK_NEGATIVO muestra el saldo resultante de la venta y de la transferencia', () => {
    expect(detalleDeObservacion('STOCK_NEGATIVO', { saldo_resultante: -3 })).toEqual(['Saldo resultante: -3 unidades'])
    expect(detalleDeObservacion('STOCK_NEGATIVO', { saldo: -8 })).toEqual(['Saldo resultante: -8 unidades'])
  })

  it('PRODUCTO_DESACTIVADO y VENTA_SIN_COSTO nombran la línea y el producto cuando se conocen', () => {
    const detalle = { linea_id: 'l2', producto_id: 'p1' }
    const nombres = { productos: new Map([['p1', 'Gaseosa 2 L']]), lineas: new Map([['l2', 2]]) }

    expect(detalleDeObservacion('PRODUCTO_DESACTIVADO', detalle, nombres)).toEqual(['Línea 2: Gaseosa 2 L'])
    expect(detalleDeObservacion('VENTA_SIN_COSTO', detalle, nombres)).toEqual(['Línea 2: Gaseosa 2 L'])
    expect(detalleDeObservacion('VENTA_SIN_COSTO', detalle)).toEqual([])
  })

  it('un código desconocido o un detalle nulo no da líneas ni falla', () => {
    expect(detalleDeObservacion('CODIGO_NUEVO', { x: 1 })).toEqual([])
    expect(detalleDeObservacion('DESCUENTO_DIFIERE', null)).toEqual([])
    expect(detalleDeObservacion('EXCESO_CREDITO_DETECTADO_SYNC', { dispositivo: 'basura' })).toEqual([])
  })
})

describe('nombresDeAviso y los nombres que manda el servidor (lote extra, 2026-11-06)', () => {
  it('el autorizador sale del nombre del servidor y no dice «un usuario»', () => {
    const detalle = { tipo: 'DESCUENTO', resolucion: 'PIN_SUPERVISOR', autorizador_id: 'u9', autorizador_con_permiso: true }
    const nombres = nombresDeAviso(detalle, { autorizador: 'Ana Supervisora', producto: null, linea: null, vendedor_de_jornada: null })

    expect(detalleDeObservacion('AUTORIZACION_OFFLINE', detalle, nombres)).toEqual([
      'Autorizó Ana Supervisora (descuento, con el PIN de un supervisor); conserva el permiso',
    ])
    expect(detalleDeObservacion('AUTORIZACION_OFFLINE', detalle, nombresDeAviso(detalle, null))).toEqual([
      'Autorizó un usuario (descuento, con el PIN de un supervisor); conserva el permiso',
    ])
  })

  it('un autorizador que ya no existe se lee «un usuario que no existe» (revisión del usuario, 2026-11-06)', () => {
    const detalle = { tipo: 'CREDITO', resolucion: 'PERMISO_PROPIO', autorizador_id: 'u9', autorizador_con_permiso: false }
    const nombres = nombresDeAviso(detalle, { autorizador: '(no existe)', producto: null, linea: null, vendedor_de_jornada: null })

    const [linea] = detalleDeObservacion('AUTORIZACION_OFFLINE', detalle, nombres)
    expect(linea?.startsWith('Autorizó un usuario que no existe (')).toBe(true)
    expect(linea).not.toContain('(no existe)')
  })

  it('la línea y el producto salen del servidor en STOCK_NEGATIVO, VENTA_SIN_COSTO y PRODUCTO_DESACTIVADO', () => {
    const detalle = { linea_id: 'l1', producto_id: 'p1', saldo_resultante: -3 }
    const nombres = nombresDeAviso(detalle, { autorizador: null, producto: 'Gaseosa 2 L', linea: 2, vendedor_de_jornada: null })

    expect(detalleDeObservacion('STOCK_NEGATIVO', detalle, nombres)).toEqual(['Saldo resultante: -3 unidades', 'Línea 2: Gaseosa 2 L'])
    expect(detalleDeObservacion('VENTA_SIN_COSTO', detalle, nombres)).toEqual(['Línea 2: Gaseosa 2 L'])
    expect(detalleDeObservacion('PRODUCTO_DESACTIVADO', detalle, nombres)).toEqual(['Línea 2: Gaseosa 2 L'])
  })

  it('sin número de línea muestra solo el producto', () => {
    const detalle = { linea_id: 'l1', producto_id: 'p1' }
    const nombres = nombresDeAviso(detalle, { autorizador: null, producto: '(no existe)', linea: null, vendedor_de_jornada: null })

    expect(detalleDeObservacion('VENTA_SIN_COSTO', detalle, nombres)).toEqual(['(no existe)'])
  })

  it('UBICACION_TOMADA_AL_SINCRONIZAR dice «Tomada por la jornada de {vendedor}»', () => {
    const detalle = { jornada_id: 'j1', ubicacion_id: 'u1' }
    const nombres = nombresDeAviso(detalle, { autorizador: null, producto: null, linea: null, vendedor_de_jornada: 'Beto Vendedor' })

    expect(detalleDeObservacion('UBICACION_TOMADA_AL_SINCRONIZAR', detalle, nombres)).toEqual(['Tomada por la jornada de Beto Vendedor'])
    expect(detalleDeObservacion('UBICACION_TOMADA_AL_SINCRONIZAR', detalle, nombresDeAviso(detalle, null))).toEqual([])
  })
})
