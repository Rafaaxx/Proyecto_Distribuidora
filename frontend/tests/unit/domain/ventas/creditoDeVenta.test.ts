/**
 * Change 18b, tarea 13.1: panel de crédito de la pantalla de venta con la gemela `cre01`
 * (CRE-01 a CRE-07, D5, D6, D16, D20). El servidor decide igual (TR-10): esto es lo que se pinta.
 */

import { describe, expect, it } from 'vitest'

import { calcularExceso } from '../../../../src/domain/credito/evaluacion'
import {
  evaluarPanelDeCredito,
  textoDeDecisionDeCredito,
  type DatosDeCreditoDeVenta,
} from '../../../../src/domain/ventas/creditoDeVenta'

const KIOSCO: DatosDeCreditoDeVenta = {
  limite: '200000.00',
  saldo: '150000.00',
  politica: 'ADVERTIR',
  toleranciaTipo: null,
  toleranciaValor: null,
}

function panel(parcial: Partial<DatosDeCreditoDeVenta> = {}, extra: Record<string, unknown> = {}) {
  return evaluarPanelDeCredito({
    datos: { ...KIOSCO, ...parcial },
    total: '80000.00',
    cobranza: '20000.00',
    aceptaExceso: false,
    puedeSuperar: false,
    ...extra,
  })
}

describe('calcularExceso (gemela de clientes/domain/credito.py::calcular_exceso)', () => {
  it('el ejemplo de 01 §9.2: disponible 50.000, resultante 210.000, exceso 10.000', () => {
    const r = calcularExceso({ limite: '200000.00', saldoActual: '150000.00', totalVenta: '80000.00', cobranza: '20000.00' })
    expect(r.disponible?.toFixed(2)).toBe('50000.00')
    expect(r.saldoResultante.toFixed(2)).toBe('210000.00')
    expect(r.exceso.toFixed(2)).toBe('10000.00')
  })

  it('sin límite no hay control ni exceso', () => {
    const r = calcularExceso({ limite: null, saldoActual: '999999.00', totalVenta: '80000.00', cobranza: '0.00' })
    expect(r.disponible).toBeNull()
    expect(r.exceso.toFixed(2)).toBe('0.00')
  })

  it('una venta cobrada entera de un cliente ya excedido no tiene exceso (D5)', () => {
    const r = calcularExceso({ limite: '200000.00', saldoActual: '250000.00', totalVenta: '30000.00', cobranza: '30000.00' })
    expect(r.exceso.toFixed(2)).toBe('0.00')
  })
})

describe('evaluarPanelDeCredito', () => {
  it('muestra los números del ejemplo de 01 §9.2 con la política ADVERTIR pidiendo aceptar el exceso', () => {
    const r = panel()
    expect(r).toMatchObject({
      decision: 'pide-aceptar',
      limite: '200000.00',
      saldo: '150000.00',
      disponible: '50000.00',
      saldoResultante: '210000.00',
      exceso: '10000.00',
      politica: 'ADVERTIR',
    })
  })

  it('ADVERTIR aceptado queda "aceptado" (CRE-04)', () => {
    expect(panel({}, { aceptaExceso: true }).decision).toBe('aceptado')
  })

  it('AUTORIZAR sin permiso propio pide un autorizador; con SUPERAR_CREDITO se autoriza solo (CRE-05)', () => {
    expect(panel({ politica: 'AUTORIZAR' }).decision).toBe('pide-autorizador')
    expect(panel({ politica: 'AUTORIZAR' }, { puedeSuperar: true }).decision).toBe('permiso-propio')
  })

  it('BLOQUEAR bloquea aunque tenga el permiso (CRE-07)', () => {
    expect(panel({ politica: 'BLOQUEAR' }).decision).toBe('bloqueado')
    expect(panel({ politica: 'BLOQUEAR' }, { puedeSuperar: true }).decision).toBe('bloqueado')
  })

  it('BLOQUEAR se resuelve cobrando más: con cobranza igual al total no hay exceso (D5)', () => {
    const r = panel({ politica: 'BLOQUEAR' }, { cobranza: '80000.00' })
    expect(r.decision).toBe('sin-exceso')
    expect(r.exceso).toBe('0.00')
  })

  it('un cliente excedido que paga todo en el acto no es bloqueado', () => {
    const r = panel({ saldo: '250000.00', politica: 'BLOQUEAR' }, { total: '30000.00', cobranza: '30000.00' })
    expect(r.decision).toBe('sin-exceso')
    expect(r.disponible).toBe('-50000.00')
  })

  it('sin límite cargado no hay control', () => {
    const r = panel({ limite: null })
    expect(r).toMatchObject({ decision: 'sin-control', disponible: null, exceso: '0.00' })
  })

  it('el límite cero es solo de contado: toda venta a cuenta se pasa', () => {
    const r = panel({ limite: '0.00', saldo: '0.00', politica: 'BLOQUEAR' }, { total: '1000.00', cobranza: '0.00' })
    expect(r.decision).toBe('bloqueado')
    expect(r.exceso).toBe('1000.00')
  })

  it('la tolerancia sin conexión no rige con conexión (el panel es de la venta con conexión)', () => {
    const r = panel({ politica: 'AUTORIZAR', toleranciaTipo: 'IMPORTE', toleranciaValor: '20000.00' })
    expect(r.decision).toBe('pide-autorizador')
  })

  it('datos que no se pueden evaluar no rompen la pantalla', () => {
    expect(panel({ politica: 'PERMITIR' }).decision).toBe('no-evaluable')
    expect(panel({ saldo: 'abc' }).decision).toBe('no-evaluable')
  })
})

describe('textoDeDecisionDeCredito', () => {
  it('dice qué hacer en cada caso, con el exceso formateado', () => {
    const base = panel()
    expect(textoDeDecisionDeCredito(base)).toBe('La venta se pasa del límite por $ 10.000,00.')
    expect(textoDeDecisionDeCredito({ ...base, decision: 'bloqueado' })).toBe(
      'No se puede confirmar: el cliente se pasa del límite por $ 10.000,00. Aumentá la cobranza o sacá productos.',
    )
    expect(textoDeDecisionDeCredito({ ...base, decision: 'pide-autorizador' })).toBe(
      'La venta deja al cliente $ 10.000,00 sobre su límite y necesita autorización.',
    )
    expect(textoDeDecisionDeCredito({ ...base, decision: 'permiso-propio' })).toBe(
      'La venta deja al cliente $ 10.000,00 sobre su límite; la autorizás vos con tu permiso.',
    )
    expect(textoDeDecisionDeCredito({ ...base, decision: 'sin-exceso' })).toBe('Dentro del límite de crédito.')
    expect(textoDeDecisionDeCredito({ ...base, decision: 'sin-control' })).toBe('El cliente no tiene límite de crédito.')
  })
})

describe('evaluarPanelDeCredito en el dispositivo (change 22a, tarea 6.1; D9; CRE-04 a CRE-07, CRE-10)', () => {
  const autorizar = (tolerancia: string) => ({
    politica: 'AUTORIZAR',
    toleranciaTipo: 'IMPORTE',
    toleranciaValor: tolerancia,
  })
  const sinConexion = { modo: 'SIN_CONEXION' as const }

  it('SIN_CONEXION dentro de la tolerancia ($20.000) resuelve por tolerancia offline (CRE-06)', () => {
    const r = panel(autorizar('20000.00'), sinConexion)
    expect(r.decision).toBe('tolerancia-offline')
    expect(r.exceso).toBe('10000.00')
  })

  it('SIN_CONEXION fuera de la tolerancia ($5.000) pide autorizador, no bloquea (CRE-06, CRE-05)', () => {
    expect(panel(autorizar('5000.00'), sinConexion).decision).toBe('pide-autorizador')
  })

  it('SIN_CONEXION fuera de la tolerancia con permiso propio autoriza el usuario (CRE-05)', () => {
    expect(panel(autorizar('5000.00'), { ...sinConexion, puedeSuperar: true }).decision).toBe('permiso-propio')
  })

  it('BLOQUEAR bloquea también sin conexión (CRE-07)', () => {
    expect(panel({ politica: 'BLOQUEAR' }, sinConexion).decision).toBe('bloqueado')
  })

  it('ADVERTIR pide aceptar sin conexión y, aceptado, queda aceptado (CRE-04)', () => {
    expect(panel({ politica: 'ADVERTIR' }, sinConexion).decision).toBe('pide-aceptar')
    expect(panel({ politica: 'ADVERTIR' }, { ...sinConexion, aceptaExceso: true }).decision).toBe('aceptado')
  })

  it('sin exceso no cambia nada en ningún modo (CRE-10)', () => {
    expect(panel({ saldo: '10000.00' }, sinConexion).decision).toBe('sin-exceso')
  })

  it('/admin sigue en CON_CONEXION: la misma entrada sin modo pide autorizador aun dentro de la tolerancia', () => {
    expect(panel(autorizar('20000.00')).decision).toBe('pide-autorizador')
    expect(panel(autorizar('20000.00'), { modo: 'CON_CONEXION' }).decision).toBe('pide-autorizador')
  })

  it('el texto de la tolerancia dice que se confirma por tolerancia', () => {
    const texto = textoDeDecisionDeCredito(panel(autorizar('20000.00'), sinConexion))
    expect(texto).toMatch(/tolerancia/i)
  })
})
