import { describe, expect, it } from 'vitest'

import {
  AMBITO_DE_ANULACION_DE_COBRANZA,
  ETIQUETA_DE_ESTADO_DE_COBRANZA,
  detalleDeObservacion,
  etiquetaDeObservacion,
  etiquetaDeOrigenDeCobranza,
  observacionesDeLinea,
  observacionesGenerales,
  puedeAnularse,
  textoDeSaldoTrasAnular,
} from '../../../../src/domain/cobranzas/presentacion'

const obs = (codigo: string, detalle: Record<string, unknown> | null = null) => ({ codigo, estado: 'PENDIENTE', detalle })

describe('anular (COB-05, D7)', () => {
  it('se ofrece solo en una cobranza CONFIRMADA de origen INDEPENDIENTE', () => {
    expect(puedeAnularse({ estado: 'CONFIRMADA', origen: 'INDEPENDIENTE' })).toBe(true)
    expect(puedeAnularse({ estado: 'ANULADA', origen: 'INDEPENDIENTE' })).toBe(false)
    expect(puedeAnularse({ estado: 'CONFIRMADA', origen: 'VENTA' })).toBe(false)
  })

  it('el saldo tras anular devuelve el importe a la deuda (CC-02)', () => {
    expect(textoDeSaldoTrasAnular('100000.00', '50000.00')).toBe('Nos debe $ 150.000,00')
    expect(textoDeSaldoTrasAnular('-50000.00', '50000.00')).toBe('Saldo $ 0,00')
  })

  it('usa el ámbito de motivos de la anulación de cobranzas', () => {
    expect(AMBITO_DE_ANULACION_DE_COBRANZA).toBe('ANULACION_COBRANZA')
  })
})

describe('etiquetas', () => {
  it('estado y origen en palabras; lo desconocido se muestra tal cual', () => {
    expect(ETIQUETA_DE_ESTADO_DE_COBRANZA.CONFIRMADA).toBe('Confirmada')
    expect(ETIQUETA_DE_ESTADO_DE_COBRANZA.ANULADA).toBe('Anulada')
    expect(etiquetaDeOrigenDeCobranza('INDEPENDIENTE')).toBe('Cobranza independiente')
    expect(etiquetaDeOrigenDeCobranza('OTRO')).toBe('OTRO')
  })

  it.each([
    ['MEDIO_INACTIVO', 'Medio de pago inactivo'],
    ['REFERENCIA_FALTANTE', 'Falta la referencia'],
    ['PERMISO_REVOCADO', 'Permiso revocado'],
    ['JORNADA_LIBERADA', 'Jornada liberada'],
    ['CLIENTE_NO_HABILITADO', 'Cliente no habilitado'],
    ['STOCK_NEGATIVO', 'STOCK_NEGATIVO'],
  ])('la observación %s se llama "%s" (SYN-07)', (codigo, esperado) => {
    expect(etiquetaDeObservacion(codigo)).toBe(esperado)
  })
})

describe('observaciones por línea (SYN-07, D13)', () => {
  const lista = [
    obs('MEDIO_INACTIVO', { medio: 0, medio_pago_id: 'a', nombre: 'Billetera', importe: '10000.00' }),
    obs('REFERENCIA_FALTANTE', { medio: 1, medio_pago_id: 'b', nombre: 'Transferencia', importe: '20000.00' }),
    obs('MEDIO_INACTIVO', { medio: 1, medio_pago_id: 'b', nombre: 'Transferencia', importe: '20000.00' }),
    obs('PERMISO_REVOCADO', { permiso: 'REGISTRAR_COBRANZA', motivo: 'PERMISO_QUITADO' }),
    obs('CLIENTE_NO_HABILITADO'),
  ]

  it('reparte las de medio por línea y deja las demás como generales', () => {
    expect(observacionesDeLinea(lista, 0).map((o) => o.codigo)).toEqual(['MEDIO_INACTIVO'])
    expect(observacionesDeLinea(lista, 1).map((o) => o.codigo)).toEqual(['REFERENCIA_FALTANTE', 'MEDIO_INACTIVO'])
    expect(observacionesDeLinea(lista, 2)).toEqual([])
    expect(observacionesGenerales(lista).map((o) => o.codigo)).toEqual(['PERMISO_REVOCADO', 'CLIENTE_NO_HABILITADO'])
  })

  it('una de medio sin posición legible pasa a las generales (no se esconde)', () => {
    const rara = [obs('MEDIO_INACTIVO', { medio: 'x' }), obs('REFERENCIA_FALTANTE', null)]

    expect(observacionesGenerales(rara)).toHaveLength(2)
    expect(observacionesDeLinea(rara, 0)).toEqual([])
  })

  it('el detalle de una línea muestra medio e importe; el de permiso, el motivo en palabras', () => {
    expect(detalleDeObservacion(lista[0] as never)).toBe('Billetera · $ 10.000,00')
    expect(detalleDeObservacion(lista[3] as never)).toBe('Se le quitó el permiso de cobrar')
    expect(detalleDeObservacion(obs('PERMISO_REVOCADO', { motivo: 'USUARIO_INACTIVO' }))).toBe('El usuario estaba dado de baja')
    expect(detalleDeObservacion(obs('PERMISO_REVOCADO', { motivo: 'ROL_INACTIVO' }))).toBe('El rol estaba dado de baja')
    expect(detalleDeObservacion(obs('CLIENTE_NO_HABILITADO'))).toBeNull()
  })
})
