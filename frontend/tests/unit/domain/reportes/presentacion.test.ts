import { describe, expect, it } from 'vitest'

import {
  etiquetaDeEstadoDeJornada,
  formatearCajas,
  formatearFechaDeNegocio,
  formatearMomento,
  formatearUnidades,
  formatearImporteDeReporte,
  formatearSaldoDeCuenta,
  formatearTotalAFavor,
  textoDeAjustesAnulados,
  textoDeAnuladas,
  textoDeLineasSinCosto,
  textoDePeriodo,
} from '../../../../src/domain/reportes/presentacion'
import { veSaldosDeProveedores } from '../../../../src/domain/reportes/permisos'

/**
 * Change 26, tarea 9.1 (D1, D5, D8 = B, D12; cita TR-04, INV-03): la presentación de los reportes sale del
 * string de la API, sin pasar por `number`, y la regla compuesta de los saldos de proveedores.
 */
describe('formatearImporteDeReporte (INV-03)', () => {
  it('formatea desde el string con miles y coma decimal', () => {
    expect(formatearImporteDeReporte('31250.00')).toBe('31.250,00')
  })

  it('conserva la exactitud de un importe que un number no representa', () => {
    expect(formatearImporteDeReporte('12345678901234.57')).toBe('12.345.678.901.234,57')
  })

  it('formatea un importe negativo y el cero', () => {
    expect(formatearImporteDeReporte('-1500.50')).toBe('-1.500,50')
    expect(formatearImporteDeReporte('0.00')).toBe('0,00')
  })
})

describe('formatearCajas (REP-03)', () => {
  it('muestra las cajas equivalentes con coma decimal', () => {
    expect(formatearCajas('2.50')).toBe('2,50')
    expect(formatearCajas('1234.50')).toBe('1.234,50')
  })
})

describe('formatearUnidades', () => {
  it('agrupa los miles de un entero', () => {
    expect(formatearUnidades(15)).toBe('15')
    expect(formatearUnidades(1234567)).toBe('1.234.567')
  })
})

describe('fechas de negocio (TR-04)', () => {
  it('formatea aaaa-mm-dd como dd/mm/aaaa sin construir un Date', () => {
    expect(formatearFechaDeNegocio('2026-11-02')).toBe('02/11/2026')
    expect(formatearFechaDeNegocio('2026-01-31')).toBe('31/01/2026')
  })

  it('formatea un momento en la zona horaria de la organización', () => {
    // 2026-11-01T02:30Z es el 31 de octubre a las 23:30 en Mendoza.
    expect(formatearMomento('2026-11-01T02:30:00Z', 'America/Argentina/Mendoza')).toBe('31/10/2026')
    expect(formatearMomento('2026-11-01T02:30:00Z', 'UTC')).toBe('01/11/2026')
  })

  it('«Período: {desde} al {hasta}» (D12)', () => {
    expect(textoDePeriodo('2026-11-01', '2026-11-06')).toBe('Período: 01/11/2026 al 06/11/2026')
  })
})

describe('textos con valores (D12)', () => {
  it('la nota de líneas sin costo', () => {
    expect(textoDeLineasSinCosto({ lineas: 1, importe_neto: '300.00' })).toBe(
      'Líneas sin costo: 1, con un neto de 300,00. No entran en el costo vendido ni en la utilidad.',
    )
    expect(textoDeLineasSinCosto({ lineas: 12, importe_neto: '1500.50' })).toBe(
      'Líneas sin costo: 12, con un neto de 1.500,50. No entran en el costo vendido ni en la utilidad.',
    )
  })

  it('la nota de ventas anuladas', () => {
    expect(textoDeAnuladas(2, '2500.00')).toBe('2 ventas anuladas por 2.500,00. No entran en los totales.')
    expect(textoDeAnuladas(1, '100.00')).toBe('1 ventas anuladas por 100,00. No entran en los totales.')
  })
})

describe('etiquetaDeEstadoDeJornada (D12)', () => {
  it.each([
    ['ABIERTA', 'En curso'],
    ['EN_RENDICION', 'En rendición'],
    ['CERRADA', 'Cerrada'],
    ['LIBERADA', 'Liberada'],
  ])('%s se muestra como «%s»', (estado, etiqueta) => {
    expect(etiquetaDeEstadoDeJornada(estado)).toBe(etiqueta)
  })

  it('un estado desconocido se muestra tal cual', () => {
    expect(etiquetaDeEstadoDeJornada('OTRO')).toBe('OTRO')
  })
})

describe('formatearSaldoDeCuenta (CC-04, D12 «a favor»)', () => {
  it('un saldo deudor se muestra tal cual', () => {
    expect(formatearSaldoDeCuenta('1000.00')).toBe('1.000,00')
  })

  it('un saldo negativo se muestra en positivo con la marca «a favor»', () => {
    expect(formatearSaldoDeCuenta('-200.00')).toBe('200,00 a favor')
    expect(formatearSaldoDeCuenta('-12345678901234.57')).toBe('12.345.678.901.234,57 a favor')
  })

  it('el cero no lleva marca', () => {
    expect(formatearSaldoDeCuenta('0.00')).toBe('0,00')
  })
})

describe('formatearTotalAFavor (CC-04)', () => {
  it('el total a favor llega negativo y se muestra sin signo', () => {
    expect(formatearTotalAFavor('-200.00')).toBe('200,00')
    expect(formatearTotalAFavor('0.00')).toBe('0,00')
  })
})

describe('textoDeAjustesAnulados (D12)', () => {
  it('arma la nota con la cantidad', () => {
    expect(textoDeAjustesAnulados(1)).toBe('Ajustes anulados: 1. No entran en los totales.')
    expect(textoDeAjustesAnulados(12)).toBe('Ajustes anulados: 12. No entran en los totales.')
  })
})

describe('veSaldosDeProveedores (D8 = B; SEG-06)', () => {
  const con = (...permisos: string[]) => (permiso: string) => permisos.includes(permiso)

  it('la plantilla de sup01 (sin GESTIONAR_PROVEEDORES, pagos ni utilidad) no los ve', () => {
    expect(veSaldosDeProveedores(con('VER_REPORTES', 'VENDER', 'AJUSTAR_STOCK', 'REVISAR_OBSERVACIONES'))).toBe(false)
  })

  it('la plantilla de consulta (VER_REPORTES y VER_UTILIDAD) los ve', () => {
    expect(veSaldosDeProveedores(con('VER_UTILIDAD', 'VER_REPORTES', 'VER_AUDITORIA'))).toBe(true)
  })

  it('solo VER_REPORTES no alcanza', () => {
    expect(veSaldosDeProveedores(con('VER_REPORTES'))).toBe(false)
  })

  it('VER_UTILIDAD sin VER_REPORTES no alcanza', () => {
    expect(veSaldosDeProveedores(con('VER_UTILIDAD'))).toBe(false)
  })

  it.each(['GESTIONAR_PROVEEDORES', 'REGISTRAR_PAGO_PROVEEDOR', 'VER_UTILIDAD'])(
    'VER_REPORTES con %s alcanza',
    (otro) => {
      expect(veSaldosDeProveedores(con('VER_REPORTES', otro))).toBe(true)
    },
  )
})
