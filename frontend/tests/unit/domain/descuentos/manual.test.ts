/**
 * Change 16, tarea 12.3: evaluación del descuento manual (DSC-06, TR-02, INV-03; `design.md` D11,
 * D12). Lo que comparte con el servidor corre en `tests/unit/calculo/dsc06.fixtures.test.ts`;
 * acá, la forma del resultado y el encadenamiento con el motor.
 */

import { describe, expect, it } from 'vitest'

import { ErrorDeDescuentos } from '../../../../src/domain/descuentos/errores'
import type { EntradaManual } from '../../../../src/domain/descuentos/manual'
import { evaluarDescuentoManual } from '../../../../src/domain/descuentos/manual'
import { calcularDescuentos } from '../../../../src/domain/descuentos/motor'
import type { LineaVenta } from '../../../../src/domain/descuentos/tipos'

const DM = 'DESCUENTO_MANUAL'
const AU = 'AUTORIZAR_DESCUENTO'

function entrada(parcial: Partial<EntradaManual> = {}): EntradaManual {
  return {
    usuarioId: 'u-vendedor',
    descuentoManualHabilitado: true,
    motivoObligatorio: null,
    permisosUsuario: [DM],
    topeRol: '0.050000',
    topePropio: null,
    porcentajeMaximo: '0.030000',
    motivo: null,
    autorizador: null,
    ...parcial,
  }
}

function linea(id: string, bruto: string, manual: string | null = null): LineaVenta {
  return {
    id,
    bruto,
    cantidadBase: 1,
    unidadesReferencia: 1,
    productoId: `p-${id}`,
    categoriaId: 'c',
    marcaId: 'm',
    descuentoManual: manual,
  }
}

function codigoDelError(accion: () => unknown): string | undefined {
  try {
    accion()
  } catch (error) {
    return (error as ErrorDeDescuentos).codigo
  }
  return undefined
}

describe('evaluarDescuentoManual', () => {
  it('informa tope, autorización, resolución y autorizador', () => {
    const resultado = evaluarDescuentoManual(
      entrada({
        porcentajeMaximo: '0.100000',
        autorizador: { usuarioId: 'u-supervisora', permisos: [DM, AU] },
      }),
    )

    expect(resultado.topeAplicado.toFixed(6)).toBe('0.050000')
    expect(resultado.requirioAutorizacion).toBe(true)
    expect(resultado.resolucion).toBe('AUTORIZADO_POR_SUPERVISOR')
    expect(resultado.autorizadorId).toBe('u-supervisora')
  })

  it('dentro del tope no informa autorizador', () => {
    const resultado = evaluarDescuentoManual(entrada())

    expect(resultado.requirioAutorizacion).toBe(false)
    expect(resultado.resolucion).toBe('DENTRO_DEL_TOPE')
    expect(resultado.autorizadorId).toBeNull()
  })

  it('el propio usuario sin permiso no se autoriza pasándose como autorizador', () => {
    const codigo = codigoDelError(() =>
      evaluarDescuentoManual(
        entrada({
          porcentajeMaximo: '0.100000',
          autorizador: { usuarioId: 'u-vendedor', permisos: [DM] },
        }),
      ),
    )

    expect(codigo).toBe('AUTORIZADOR_SIN_PERMISO')
  })

  it('evalúa el mayor porcentaje que entrega el motor: general 5% y una línea de 10%', () => {
    const motor = calcularDescuentos(
      [linea('a', '135240.00', '0.100000'), linea('b', '84280.00')],
      [],
      '0.050000',
    )
    expect(motor.porcentajeManualMaximo?.toFixed(6)).toBe('0.100000')
    const maximo = (motor.porcentajeManualMaximo as NonNullable<typeof motor.porcentajeManualMaximo>)
      .toFixed(6)

    expect(codigoDelError(() => evaluarDescuentoManual(entrada({ porcentajeMaximo: maximo })))).toBe(
      'AUTORIZACION_REQUERIDA',
    )
    const conSupervisora = evaluarDescuentoManual(
      entrada({
        porcentajeMaximo: maximo,
        autorizador: { usuarioId: 'u-supervisora', permisos: [DM, AU] },
      }),
    )
    expect(conSupervisora.resolucion).toBe('AUTORIZADO_POR_SUPERVISOR')
  })

  it('un propio menor que el general no dispara la autorización', () => {
    const motor = calcularDescuentos(
      [linea('a', '135240.00', '0.030000'), linea('b', '84280.00')],
      [],
      '0.050000',
    )
    const maximo = (motor.porcentajeManualMaximo as NonNullable<typeof motor.porcentajeManualMaximo>)
      .toFixed(6)

    expect(evaluarDescuentoManual(entrada({ porcentajeMaximo: maximo })).resolucion).toBe(
      'DENTRO_DEL_TOPE',
    )
  })

  it.each(['0', '-0.01', '1.000001'])('rechaza el porcentaje fuera de dominio %s', (invalido) => {
    expect(codigoDelError(() => evaluarDescuentoManual(entrada({ porcentajeMaximo: invalido })))).toBe(
      'DESCUENTO_MANUAL_INVALIDO',
    )
  })

  it('rechaza un porcentaje que llega como número (INV-03)', () => {
    const codigo = codigoDelError(() =>
      evaluarDescuentoManual(entrada({ porcentajeMaximo: 0.05 as unknown as string })),
    )

    expect(codigo).toBe('DESCUENTO_MANUAL_INVALIDO')
  })
})
