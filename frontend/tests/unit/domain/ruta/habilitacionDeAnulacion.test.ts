/**
 * Change 22d, tarea 10.1 (spec `ruta/area-de-ruta`, «Una venta de la jornada se anula desde el
 * teléfono»; `design.md` D5; cita VTA-20, VTA-22, VTA-24, CLI-03, SEG-06, RUT-09): cuándo se
 * ofrece «Anular venta» y qué falta en el formulario.
 */
import { describe, expect, it } from 'vitest'

import {
  motivoDeNoAnular,
  validarFormularioDeAnulacion,
  type EntradaDeHabilitacion,
} from '../../../../src/domain/ruta/habilitacionDeAnulacion'

const BASE: EntradaDeHabilitacion = {
  permisos: ['VENDER', 'ANULAR_VENTA'],
  venta: { jornada_id: 'J1', estado_envio: 'PENDIENTE' },
  jornadaDeLaSesionId: 'J1',
  tieneAnulacion: false,
  jornadaNoAbierta: false,
  versionBloqueada: false,
}

describe('motivoDeNoAnular (D5; VTA-24, SEG-06)', () => {
  it('con todo en orden se ofrece', () => {
    expect(motivoDeNoAnular(BASE)).toBeNull()
  })

  it.each(['PENDIENTE', 'ACEPTADA', 'CON_OBSERVACIONES'] as const)('una venta %s se puede anular', (estado) => {
    expect(motivoDeNoAnular({ ...BASE, venta: { jornada_id: 'J1', estado_envio: estado } })).toBeNull()
  })

  it('sin ANULAR_VENTA no se ofrece (SEG-06)', () => {
    expect(motivoDeNoAnular({ ...BASE, permisos: ['VENDER'] })).toBe('SIN_PERMISO')
  })

  it('una venta rechazada no se ofrece', () => {
    expect(motivoDeNoAnular({ ...BASE, venta: { jornada_id: 'J1', estado_envio: 'RECHAZADA' } })).toBe('RECHAZADA')
  })

  it('una venta de otra jornada no se ofrece', () => {
    expect(motivoDeNoAnular({ ...BASE, venta: { jornada_id: 'J0', estado_envio: 'ACEPTADA' } })).toBe('OTRA_JORNADA')
  })

  it('una venta ya anulada no se ofrece', () => {
    expect(motivoDeNoAnular({ ...BASE, tieneAnulacion: true })).toBe('YA_ANULADA')
  })

  it('con la jornada marcada como no abierta no se ofrece (RUT-09)', () => {
    expect(motivoDeNoAnular({ ...BASE, jornadaNoAbierta: true })).toBe('JORNADA_NO_ABIERTA')
  })

  it('por debajo de la versión mínima no se ofrece', () => {
    expect(motivoDeNoAnular({ ...BASE, versionBloqueada: true })).toBe('VERSION_BLOQUEADA')
  })
})

describe('validarFormularioDeAnulacion (VTA-20, VTA-22, CLI-03)', () => {
  const OK = { motivoId: 'm-1', observacion: '', tieneCobro: false, esConsumidorFinal: false, eleccion: null }

  it('sin cobro no pregunta la devolución', () => {
    expect(validarFormularioDeAnulacion(OK)).toEqual([])
  })

  it('sin motivo falta el motivo', () => {
    expect(validarFormularioDeAnulacion({ ...OK, motivoId: '' })).toEqual(['MOTIVO_REQUERIDO'])
  })

  it('una observación de 500 caracteres alcanza y de 501 no', () => {
    expect(validarFormularioDeAnulacion({ ...OK, observacion: 'a'.repeat(500) })).toEqual([])
    expect(validarFormularioDeAnulacion({ ...OK, observacion: 'a'.repeat(501) })).toEqual(['OBSERVACION_LARGA'])
  })

  it('los espacios de los bordes no cuentan en el largo', () => {
    expect(validarFormularioDeAnulacion({ ...OK, observacion: `  ${'a'.repeat(500)}  ` })).toEqual([])
  })

  it('con cobro hay que elegir si se devuelve', () => {
    const conCobro = { ...OK, tieneCobro: true }
    expect(validarFormularioDeAnulacion(conCobro)).toEqual(['DEVOLUCION_REQUERIDA'])
    expect(validarFormularioDeAnulacion({ ...conCobro, eleccion: true })).toEqual([])
    expect(validarFormularioDeAnulacion({ ...conCobro, eleccion: false })).toEqual([])
  })

  it('el consumidor final con cobro no necesita elegir (CLI-03)', () => {
    expect(validarFormularioDeAnulacion({ ...OK, tieneCobro: true, esConsumidorFinal: true })).toEqual([])
  })

  it('junta todo lo que falta, en orden', () => {
    expect(
      validarFormularioDeAnulacion({ ...OK, motivoId: '', observacion: 'a'.repeat(501), tieneCobro: true }),
    ).toEqual(['MOTIVO_REQUERIDO', 'OBSERVACION_LARGA', 'DEVOLUCION_REQUERIDA'])
  })
})
