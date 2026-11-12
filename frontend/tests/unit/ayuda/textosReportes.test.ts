import { describe, expect, it } from 'vitest'

import { AYUDAS } from '../../../src/ayuda/textos'

/**
 * Change 26, tarea 13.1 (spec `sistema/ayuda-contextual`, sus cuatro escenarios; `design.md` D13; ADR-051): las
 * nueve claves `reportes.*` con los textos aprobados en 0.2, sin ejemplos ni «Ver más» y con las reglas en que se
 * apoyan. Que cada ID citado exista (ADR-070 ya existe como *Propuesto*) y que cada clave usada exista lo
 * comprueba `trazabilidad.test.ts`.
 */
describe('textos de ayuda de los reportes (change 26, tarea 13.1)', () => {
  it.each([
    [
      'reportes.periodo',
      'Período',
      'Cada operación entra por su fecha en la zona horaria de la organización. Las ventas sin conexión entran en el día en que se hicieron, aunque se envíen después. Sin fechas elegidas se muestra el mes en curso.',
      ['TR-04', 'REP-02'],
    ],
    [
      'reportes.anuladas',
      'Ventas anuladas',
      'Una venta anulada no suma en los totales del período en que se hizo, aunque se haya anulado después. Se muestran aparte, con la fecha y el motivo de la anulación.',
      ['REP-02'],
    ],
    [
      'reportes.cajasEquivalentes',
      'Cajas equivalentes',
      'Las unidades vendidas divididas por las unidades de la presentación de referencia que tenía el producto en cada venta. Permiten sumar productos y presentaciones distintas.',
      ['REP-03', 'REP-05'],
    ],
    [
      'reportes.utilidad',
      'Utilidad',
      'Neto vendido menos el costo congelado de cada línea al confirmar la venta. No cambia aunque después cambien los costos o los precios. Solo la ve quien tiene permiso para ver la utilidad.',
      ['REP-04', 'REP-05'],
    ],
    [
      'reportes.lineasSinCosto',
      'Líneas sin costo',
      'Ventas hechas sin conexión de productos que todavía no tenían costo promedio. Se informan aparte porque no tienen costo para calcular su utilidad.',
      ['REP-04', 'VTA-05', 'ADR-054'],
    ],
    [
      'reportes.rendiciones',
      'Rendiciones',
      'Las jornadas que empezaron en el período, con lo vendido, lo anulado y lo cobrado en cada una, y las diferencias del conteo. Lo que llegó después de la rendición se muestra aparte. El valor de las diferencias lo ve quien tiene permiso para ver costos.',
      ['RUT-07'],
    ],
    [
      'reportes.saldos',
      'Saldos',
      'Lo que cada cliente nos debe o lo que le debemos a cada proveedor, hoy. Un saldo «a favor» es dinero a favor de la otra parte en el caso del cliente y a nuestro favor en el del proveedor.',
      ['CC-04'],
    ],
    [
      'reportes.observacionesPorVendedor',
      'Observaciones por vendedor',
      'Cuántas ventas hizo cada vendedor sin conexión y cuántos avisos y operaciones rechazadas dejaron. Sirve para ver quién opera seguido sin señal y con qué resultados.',
      ['SYN-07', 'SYN-06'],
    ],
    [
      'reportes.ajustesPorMotivo',
      'Ajustes por motivo',
      'Las entradas y salidas de stock que se cargaron como ajuste, agrupadas por motivo, y las diferencias del conteo de las rendiciones. Los ajustes anulados no suman.',
      ['STK-03', 'RUT-06'],
    ],
  ] as const)('%s lleva el texto aprobado, cita sus reglas, sin ejemplo ni «Ver más»', (clave, titulo, texto, reglas) => {
    const entrada: { titulo: string; texto: string; ejemplo?: string; verMas?: string; reglas: readonly string[] } =
      AYUDAS[clave]
    expect(entrada.titulo).toBe(titulo)
    expect(entrada.texto).toBe(texto)
    expect([...entrada.reglas]).toEqual(reglas)
    expect(entrada.ejemplo).toBeUndefined()
    expect(entrada.verMas).toBeUndefined()
  })

  it('ninguna clave de reportes queda fuera de las nueve aprobadas', () => {
    const claves = Object.keys(AYUDAS).filter((clave) => clave.startsWith('reportes.'))

    expect(claves.sort()).toEqual([
      'reportes.ajustesPorMotivo',
      'reportes.anuladas',
      'reportes.cajasEquivalentes',
      'reportes.lineasSinCosto',
      'reportes.observacionesPorVendedor',
      'reportes.periodo',
      'reportes.rendiciones',
      'reportes.saldos',
      'reportes.utilidad',
    ])
  })
})
