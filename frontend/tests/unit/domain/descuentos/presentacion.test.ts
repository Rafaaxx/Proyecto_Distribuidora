/**
 * Change 16, tarea 14.1: presentación de una regla de descuento y acciones según su estado
 * (DSC-01, DSC-03, DSC-04; `01` §18; `design.md` D15). Solo texto y decisiones de la interfaz:
 * el servidor valida y autoriza igual (SEG-06). Nada se convierte a `number` (INV-03).
 */

import { describe, expect, it } from 'vitest'

import {
  accionesDeRegla,
  describirRegla,
  describirVigencia,
  etiquetaDeEstadoDeRegla,
  type ReglaPresentable,
} from '../../../../src/domain/descuentos/presentacion'

const MARCA = '11111111-1111-4111-8111-111111111111'
const CATEGORIA = '22222222-2222-4222-8222-222222222222'

function regla(campos: Partial<ReglaPresentable> = {}): ReglaPresentable {
  return {
    tipo: 'VOLUMEN_OPERACION',
    medida: 'CAJAS_EQUIVALENTES',
    operador: 'GTE',
    umbral: '20.0000',
    accion_tipo: 'PORCENTAJE',
    accion_porcentaje: '0.050000',
    accion_importe: null,
    prioridad: 10,
    acumulable: false,
    vigencia_desde: null,
    vigencia_hasta: null,
    estado: 'BORRADOR',
    alcances: [],
    ...campos,
  }
}

describe('describirRegla (DSC-03, DSC-04)', () => {
  it('cajas equivalentes >= 20 con 5 %: "Cajas equivalentes ≥ 20 → 5 %" (ejemplo de 01 §10)', () => {
    const descripcion = describirRegla(regla())

    expect(descripcion.resumen).toBe('Cajas equivalentes ≥ 20 → 5 %')
    expect(descripcion.alcance).toBe('Sobre toda la venta')
    expect(descripcion.acumulable).toBe('No acumulable')
  })

  it.each([
    [{ medida: 'UNIDADES_BASE', operador: 'GT', umbral: '60.0000' }, 'Unidades base > 60 → 5 %'],
    [{ medida: 'IMPORTE_BRUTO', operador: 'GTE', umbral: '31250.0000' }, 'Importe bruto ≥ $ 31.250,00 → 5 %'],
    [{ umbral: '0.5000' }, 'Cajas equivalentes ≥ 0,5 → 5 %'],
    [{ accion_porcentaje: '0.125000' }, 'Cajas equivalentes ≥ 20 → 12,5 %'],
    [
      { accion_tipo: 'IMPORTE_FIJO', accion_porcentaje: null, accion_importe: '1000.00' },
      'Cajas equivalentes ≥ 20 → $ 1.000,00 fijos',
    ],
  ] as const)('combinación %j', (campos, esperado) => {
    expect(describirRegla(regla(campos as Partial<ReglaPresentable>)).resumen).toBe(esperado)
  })

  it('una regla acumulable lo dice, y la prioridad se informa', () => {
    const descripcion = describirRegla(regla({ acumulable: true, prioridad: 3 }))

    expect(descripcion.acumulable).toBe('Acumulable')
    expect(descripcion.prioridad).toBe('Prioridad 3')
  })

  it('una regla de alcance lista las entidades con su tipo', () => {
    const descripcion = describirRegla(
      regla({
        tipo: 'VOLUMEN_ALCANCE',
        alcances: [
          { tipo: 'MARCA', entidad_id: MARCA, nombre: 'Coca-Cola' },
          { tipo: 'CATEGORIA', entidad_id: CATEGORIA, nombre: 'Gaseosas' },
        ],
      }),
    )

    expect(descripcion.alcance).toBe('Sobre Marca Coca-Cola, Categoría Gaseosas')
  })
})

describe('describirVigencia (D16)', () => {
  it('sin fechas dice que no tiene vigencia definida', () => {
    expect(describirVigencia(null, null)).toBe('Sin vigencia definida')
  })

  it('con fin pero sin inicio', () => {
    expect(describirVigencia(null, '2026-12-31T23:00:00Z')).toMatch(/^Hasta \d{2}\/\d{2}\/\d{4} \d{2}:\d{2}$/)
  })

  it('con las dos fechas', () => {
    expect(describirVigencia('2026-10-01T12:00:00Z', '2026-12-31T23:00:00Z')).toMatch(
      /^Desde \d{2}\/\d{2}\/\d{4} \d{2}:\d{2} hasta \d{2}\/\d{2}\/\d{4} \d{2}:\d{2}$/,
    )
  })
})

describe('etiquetaDeEstadoDeRegla (01 §18)', () => {
  it.each([
    ['BORRADOR', 'Borrador'],
    ['ACTIVA', 'Activa'],
    ['PAUSADA', 'Pausada'],
    ['VENCIDA', 'Vencida'],
  ])('%s se muestra como %s', (estado, etiqueta) => {
    expect(etiquetaDeEstadoDeRegla(estado)).toBe(etiqueta)
  })
})

describe('accionesDeRegla (01 §18; D15)', () => {
  const TODOS = ['GESTIONAR_DESCUENTOS']

  it.each([
    ['BORRADOR', { editar: true, activar: true, pausar: false, ponerFin: false }],
    ['PAUSADA', { editar: false, activar: true, pausar: false, ponerFin: true }],
    ['ACTIVA', { editar: false, activar: false, pausar: true, ponerFin: true }],
    ['VENCIDA', { editar: false, activar: false, pausar: false, ponerFin: false }],
  ])('en estado %s con permiso ofrece %j', (estado, esperado) => {
    expect(accionesDeRegla(estado, TODOS)).toEqual(esperado)
  })

  it.each(['BORRADOR', 'ACTIVA', 'PAUSADA', 'VENCIDA'])('sin GESTIONAR_DESCUENTOS en %s no ofrece nada', (estado) => {
    expect(accionesDeRegla(estado, ['ADMIN_USUARIOS'])).toEqual({
      editar: false,
      activar: false,
      pausar: false,
      ponerFin: false,
    })
  })
})
