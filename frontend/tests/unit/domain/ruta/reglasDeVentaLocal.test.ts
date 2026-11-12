/**
 * Change 22a, tarea 7.1: reglas del cliente, la lista y el descuento antes de encolar (spec
 * `ventas/venta-en-ruta`; D7, D8; CLI-02, CLI-03, VTA-11, PRC-21, VTA-10, DSC-06, ADR-054).
 */
import { describe, expect, it } from 'vitest'

import {
  bloqueoPorCliente,
  bloqueoPorConsumidorFinal,
  bloqueoPorLista,
  creditoDeConsumidorFinal,
  estadoDelDescuentoManual,
  puedeAgregarProducto,
  puedeElegirOtraLista,
  versionesElegiblesComoAnterior,
} from '../../../../src/domain/ruta/reglasDeVentaLocal'
import type { VersionLocal } from '../../../../src/lib/dispositivo/db'

const AHORA = new Date('2026-10-30T12:00:00Z')

describe('cliente suspendido (CLI-02)', () => {
  it('sin VENDER_CLIENTE_SUSPENDIDO bloquea e informa que está suspendido', () => {
    expect(bloqueoPorCliente({ estado: 'SUSPENDIDO' }, ['VENDER'])).toMatch(/suspendido/i)
  })
  it('con el permiso o con un cliente activo no bloquea', () => {
    expect(bloqueoPorCliente({ estado: 'SUSPENDIDO' }, ['VENDER_CLIENTE_SUSPENDIDO'])).toBeNull()
    expect(bloqueoPorCliente({ estado: 'ACTIVO' }, ['VENDER'])).toBeNull()
  })
})

describe('consumidor final (CLI-03, VTA-11, ADR-054)', () => {
  const cf = { es_consumidor_final: true }
  it('cobro parcial ($4.000 de $4.300) y cobro de más ($5.000) bloquean con el texto de la spec', () => {
    const texto = 'Cargá una cobranza igual al total para poder confirmar.'
    expect(bloqueoPorConsumidorFinal(cf, '4300.00', '4000.00')).toBe(texto)
    expect(bloqueoPorConsumidorFinal(cf, '4300.00', '5000.00')).toBe(texto)
  })
  it('cobro exacto no bloquea y su crédito es SIN_EXCESO con límite cero', () => {
    expect(bloqueoPorConsumidorFinal(cf, '4300.00', '4300.00')).toBeNull()
    expect(creditoDeConsumidorFinal('0.00', '4300.00', '4300.00')).toMatchObject({
      limite: '0.00',
      resolucion: 'SIN_EXCESO',
    })
  })
  it('otro cliente no tiene esta exigencia', () => {
    expect(bloqueoPorConsumidorFinal({ es_consumidor_final: false }, '4300.00', '0.00')).toBeNull()
  })
})

describe('lista y versión (PRC-21)', () => {
  const v = (id: string, numero: number, desde: string, estado = 'HISTORICA'): VersionLocal => ({
    id,
    lista_id: 'L',
    numero,
    estado,
    vigencia_desde: desde,
    vigencia_hasta: null,
  })
  it('otra lista o versión anterior solo con USAR_LISTA_ANTERIOR', () => {
    expect(puedeElegirOtraLista(['VENDER'])).toBe(false)
    expect(puedeElegirOtraLista(['VENDER', 'USAR_LISTA_ANTERIOR'])).toBe(true)
  })
  it('una versión programada no es elegible; las anteriores sí, de mayor a menor número', () => {
    const r = versionesElegiblesComoAnterior(
      [
        v('v1', 1, '2026-01-01T00:00:00Z'),
        v('v3', 3, '2026-12-01T00:00:00Z', 'PROGRAMADA'),
        v('v2', 2, '2026-06-01T00:00:00Z', 'VIGENTE'),
        v('vb', 4, '2026-02-01T00:00:00Z', 'BORRADOR'),
      ],
      AHORA,
    )
    expect(r.map((x) => x.id)).toEqual(['v2', 'v1'])
  })
  it('con motivo exigido y otra versión elegida, sin motivo bloquea', () => {
    expect(bloqueoPorLista({ usaOtraVersion: true, motivoObligatorio: true, motivoId: '' })).toMatch(/motivo/i)
    expect(bloqueoPorLista({ usaOtraVersion: true, motivoObligatorio: true, motivoId: 'm1' })).toBeNull()
  })
  it('sin otra versión o sin exigencia no pide motivo', () => {
    expect(bloqueoPorLista({ usaOtraVersion: false, motivoObligatorio: true, motivoId: '' })).toBeNull()
    expect(bloqueoPorLista({ usaOtraVersion: true, motivoObligatorio: false, motivoId: '' })).toBeNull()
  })
})

describe('producto sin precio (VTA-10)', () => {
  it('no es agregable y dice por qué; con precio sí', () => {
    expect(puedeAgregarProducto(null)).toEqual({
      agregable: false,
      mensaje: 'Producto sin precio en la lista: no se puede vender.',
    })
    expect(puedeAgregarProducto('12500.00')).toEqual({ agregable: true, mensaje: null })
  })
})

describe('descuento manual (DSC-06)', () => {
  const ctx = { habilitado: true, motivoObligatorio: false, tienePermiso: true, tope: '0.100000', puedeAutorizar: false }
  it('dentro del tope no pide autorización', () => {
    expect(estadoDelDescuentoManual('0.050000', ctx).estado).toBe('dentro-del-tope')
  })
  it('sobre el tope sin permiso de autorizar pide autorizador', () => {
    expect(estadoDelDescuentoManual('0.150000', ctx).estado).toBe('requiere-autorizador')
  })
  it('sobre el tope con permiso de autorizar lo autoriza el propio usuario', () => {
    expect(estadoDelDescuentoManual('0.150000', { ...ctx, puedeAutorizar: true }).estado).toBe('permiso-propio')
  })
  it('sin descuento no hay nada que autorizar', () => {
    expect(estadoDelDescuentoManual(null, ctx).estado).toBe('sin-descuento')
  })
})
