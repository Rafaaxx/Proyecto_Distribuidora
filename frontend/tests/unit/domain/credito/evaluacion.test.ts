/**
 * Change 18b, tarea 2.2: motor de evaluación de crédito (CRE-01 a CRE-07, INV-03, ADR-032;
 * `design.md` D5, D6, D8) más allá de los casos compartidos de
 * `tests/unit/calculo/cre01.fixtures.test.ts`. Gemela de
 * `backend/tests/unit/test_clientes_domain_credito.py`.
 */

import { describe, expect, it } from 'vitest'

import { ErrorDeCredito } from '../../../../src/domain/credito/errores'
import type { EntradaCredito } from '../../../../src/domain/credito/evaluacion'
import { evaluarCredito } from '../../../../src/domain/credito/evaluacion'

function entrada(parcial: Partial<EntradaCredito> = {}): EntradaCredito {
  return {
    limite: '200000.00',
    saldoActual: '150000.00',
    totalVenta: '80000.00',
    cobranza: '20000.00',
    politica: 'ADVERTIR',
    toleranciaTipo: null,
    toleranciaValor: null,
    modo: 'CON_CONEXION',
    aceptaExceso: true,
    usuarioId: 'u-vendedor',
    permisosUsuario: [],
    autorizador: null,
    ...parcial,
  }
}

function codigoDelError(f: () => unknown): string | undefined {
  try {
    f()
  } catch (error) {
    return (error as ErrorDeCredito).codigo
  }
  return undefined
}

describe('evaluarCredito', () => {
  it('el ejemplo de 01 §9.2 da disponible, resultante y exceso (CRE-01, CRE-02, CRE-03)', () => {
    const r = evaluarCredito(entrada())

    expect(r.disponible?.toFixed(2)).toBe('50000.00')
    expect(r.saldoResultante.toFixed(2)).toBe('210000.00')
    expect(r.exceso.toFixed(2)).toBe('10000.00')
    expect(r.resolucion).toBe('ADVERTENCIA_ACEPTADA')
    expect(r.autorizadorId).toBeNull()
  })

  it.each([
    ['30000.00', '30000.00', '0.00'], // cobrada entera: nunca exceso (D5)
    ['30000.00', '40000.00', '0.00'], // cobra de más
    ['30000.00', '29999.99', '0.01'], // un centavo de deuda en un cliente excedido
    ['30000.00', '0.00', '30000.00'], // toda la venta a cuenta
  ])('cliente ya excedido: venta %s cobranza %s -> exceso %s (D5)', (total, cobranza, esperado) => {
    const r = evaluarCredito(
      entrada({ saldoActual: '250000.00', totalVenta: total, cobranza }),
    )

    expect(r.exceso.toFixed(2)).toBe(esperado)
  })

  it('el exceso nunca es negativo ni supera la parte no cobrada (D5, CRE-02)', () => {
    for (const saldoActual of ['-5000.00', '0.00', '100000.00', '199999.99', '260000.00']) {
      for (const totalVenta of ['0.00', '0.01', '50000.00', '120000.00']) {
        for (const cobranza of ['0.00', '0.01', '50000.00', '130000.00']) {
          const r = evaluarCredito(entrada({ saldoActual, totalVenta, cobranza }))
          const noCobrado = Math.max(0, Number(totalVenta) - Number(cobranza))

          expect(r.exceso.greaterThanOrEqualTo(0)).toBe(true)
          expect(r.exceso.lessThanOrEqualTo(noCobrado.toFixed(2))).toBe(true)
        }
      }
    }
  })

  it('sin límite no hay disponible ni exceso con ninguna política (CRE-01)', () => {
    for (const politica of ['ADVERTIR', 'AUTORIZAR', 'BLOQUEAR']) {
      const r = evaluarCredito(entrada({ limite: null, politica, aceptaExceso: false }))

      expect(r.disponible).toBeNull()
      expect(r.exceso.toFixed(2)).toBe('0.00')
      expect(r.resolucion).toBe('SIN_EXCESO')
    }
  })

  it('sin límite la tolerancia porcentual vale cero (D8)', () => {
    const r = evaluarCredito(
      entrada({
        limite: null,
        toleranciaTipo: 'PORCENTAJE',
        toleranciaValor: '5.00',
        modo: 'SIN_CONEXION',
      }),
    )

    expect(r.tolerancia.toFixed(2)).toBe('0.00')
  })

  it('ADVERTIR sin aceptar se rechaza; sin exceso no pide aceptación (CRE-04)', () => {
    expect(codigoDelError(() => evaluarCredito(entrada({ aceptaExceso: false })))).toBe(
      'EXCESO_CREDITO_SIN_ACEPTAR',
    )
    expect(
      evaluarCredito(entrada({ cobranza: '80000.00', aceptaExceso: false })).resolucion,
    ).toBe('SIN_EXCESO')
  })

  it('BLOQUEAR no admite excepción ni con permiso propio ni con autorizador (CRE-07, D6)', () => {
    const r = () =>
      evaluarCredito(
        entrada({
          politica: 'BLOQUEAR',
          permisosUsuario: ['SUPERAR_CREDITO'],
          autorizador: { usuarioId: 'u-sup', permisos: ['SUPERAR_CREDITO'] },
        }),
      )

    expect(codigoDelError(r)).toBe('CREDITO_EXCEDIDO')
  })

  it('AUTORIZAR: otro permiso no cuenta, solo SUPERAR_CREDITO (CRE-05)', () => {
    expect(
      codigoDelError(() =>
        evaluarCredito(
          entrada({ politica: 'AUTORIZAR', permisosUsuario: ['AUTORIZAR_DESCUENTO'] }),
        ),
      ),
    ).toBe('AUTORIZACION_CREDITO_REQUERIDA')
    expect(
      codigoDelError(() =>
        evaluarCredito(
          entrada({
            politica: 'AUTORIZAR',
            autorizador: { usuarioId: 'u-sup', permisos: ['AUTORIZAR_DESCUENTO'] },
          }),
        ),
      ),
    ).toBe('AUTORIZADOR_SIN_PERMISO')
  })

  it('sin conexión el exceso igual a la tolerancia pasa y un centavo más no (D8)', () => {
    const base = { politica: 'AUTORIZAR', modo: 'SIN_CONEXION', toleranciaTipo: 'IMPORTE' }

    expect(evaluarCredito(entrada({ ...base, toleranciaValor: '10000.00' })).resolucion).toBe(
      'TOLERANCIA_OFFLINE',
    )
    expect(codigoDelError(() => evaluarCredito(entrada({ ...base, toleranciaValor: '9999.99' })))).toBe(
      'CREDITO_EXCEDIDO',
    )
  })

  it('dentro de la tolerancia gana la tolerancia y no se registra autorizador (CRE-06)', () => {
    const r = evaluarCredito(
      entrada({
        politica: 'AUTORIZAR',
        modo: 'SIN_CONEXION',
        toleranciaTipo: 'IMPORTE',
        toleranciaValor: '10000.00',
        permisosUsuario: ['SUPERAR_CREDITO'],
      }),
    )

    expect(r.resolucion).toBe('TOLERANCIA_OFFLINE')
    expect(r.autorizadorId).toBeNull()
  })

  it.each(['limite', 'saldoActual', 'totalVenta', 'cobranza', 'toleranciaValor'] as const)(
    'rechaza un número nativo o un booleano en %s (INV-03)',
    (campo) => {
      for (const invalido of [1.5, true]) {
        const parcial = { [campo]: invalido, toleranciaTipo: 'IMPORTE' } as unknown as Partial<EntradaCredito>

        expect(codigoDelError(() => evaluarCredito(entrada(parcial)))).toBe(
          'ENTRADA_NO_ES_DINERO_EXACTO',
        )
      }
    },
  )

  it('rechaza política y modo fuera del catálogo y tolerancia a medias o negativa', () => {
    expect(codigoDelError(() => evaluarCredito(entrada({ politica: 'PERMITIR' })))).toBe(
      'POLITICA_CREDITO_INVALIDA',
    )
    expect(codigoDelError(() => evaluarCredito(entrada({ politica: '' })))).toBe(
      'POLITICA_CREDITO_INVALIDA',
    )
    expect(codigoDelError(() => evaluarCredito(entrada({ modo: 'HIBRIDO' })))).toBe(
      'MODO_CREDITO_INVALIDO',
    )
    expect(
      codigoDelError(() =>
        evaluarCredito(entrada({ toleranciaTipo: 'IMPORTE', toleranciaValor: null })),
      ),
    ).toBe('TOLERANCIA_OFFLINE_INVALIDA')
    expect(
      codigoDelError(() =>
        evaluarCredito(entrada({ toleranciaTipo: 'PORCENTAJE', toleranciaValor: '-1.00' })),
      ),
    ).toBe('TOLERANCIA_OFFLINE_INVALIDA')
  })

  it('un límite negativo o con más de dos decimales se rechaza (CRE-01, INV-03)', () => {
    expect(codigoDelError(() => evaluarCredito(entrada({ limite: '-1.00' })))).toBe(
      'LIMITE_CREDITO_INVALIDO',
    )
    expect(codigoDelError(() => evaluarCredito(entrada({ limite: '100.005' })))).toBe(
      'LIMITE_CREDITO_INVALIDO',
    )
  })
})
