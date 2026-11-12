import { describe, expect, it } from 'vitest'

import { descripcionDeDiferencia, hayDiferencias } from '../../../../src/domain/sistema/consistencia'
import type { DiferenciaDeConsistencia } from '../../../../src/features/sistema/api'

const base: DiferenciaDeConsistencia = {
  tipo: 'SALDO_CUENTA',
  cuenta_tipo: null,
  entidad_id: null,
  entidad_nombre: null,
  saldo_materializado: null,
  suma_del_libro: null,
  producto_id: null,
  producto_nombre: null,
  ubicacion_id: null,
  ubicacion_nombre: null,
  materializado: null,
  esperado: null,
  promedio_vigente: null,
  promedio_historia: null,
}

/**
 * Change 28, tarea 3.2 (D5, D17; ADR-015, INV-03): cómo se cuenta cada tipo de diferencia. Los importes salen de
 * `lib/money.ts` (es-AR), nunca de `number`.
 */
describe('descripción de una diferencia de consistencia', () => {
  it('una cuenta de cliente nombra al cliente y compara el saldo guardado con la suma de sus movimientos', () => {
    const texto = descripcionDeDiferencia({
      ...base,
      cuenta_tipo: 'CLIENTE',
      entidad_nombre: 'Kiosco La Esquina',
      saldo_materializado: '31250.00',
      suma_del_libro: '1450.50',
    })

    expect(texto).toBe('Cuenta del cliente Kiosco La Esquina: saldo guardado $ 31.250,00, suma de sus movimientos $ 1.450,50.')
  })

  it('una cuenta de proveedor sin nombre legible lo dice sin inventarlo', () => {
    const texto = descripcionDeDiferencia({
      ...base,
      cuenta_tipo: 'PROVEEDOR',
      entidad_nombre: null,
      saldo_materializado: '0.00',
      suma_del_libro: '-10.00',
    })

    expect(texto).toBe('Cuenta de un proveedor (nombre no disponible): saldo guardado $ 0,00, suma de sus movimientos $ -10,00.')
  })

  it('el stock de un producto en una ubicación compara cantidades enteras', () => {
    const texto = descripcionDeDiferencia({
      ...base,
      tipo: 'STOCK_SALDO',
      producto_nombre: 'Vino A',
      ubicacion_nombre: 'Depósito',
      materializado: 7,
      esperado: 5,
    })

    expect(texto).toBe('Stock de Vino A en Depósito: guardado 7, según sus movimientos 5.')
  })

  it('el stock total de un producto compara con la suma de sus ubicaciones', () => {
    const texto = descripcionDeDiferencia({
      ...base,
      tipo: 'STOCK_TOTAL',
      producto_nombre: 'Vino A',
      materializado: 9,
      esperado: 5,
    })

    expect(texto).toBe('Stock total de Vino A: guardado 9, suma de sus ubicaciones 5.')
  })

  it('el costo promedio muestra seis decimales y dice cuándo no hay historial', () => {
    const con = descripcionDeDiferencia({
      ...base,
      tipo: 'PROMEDIO_COSTO',
      producto_nombre: 'Vino A',
      promedio_vigente: '10.500000',
      promedio_historia: '10.250000',
    })
    const sin = descripcionDeDiferencia({
      ...base,
      tipo: 'PROMEDIO_COSTO',
      producto_nombre: 'Vino A',
      promedio_vigente: '10.500000',
      promedio_historia: null,
    })

    expect(con).toBe('Costo promedio de Vino A: vigente $ 10,500000, según su historial $ 10,250000.')
    expect(sin).toBe('Costo promedio de Vino A: vigente $ 10,500000, sin historial para compararlo.')
  })

  it('hayDiferencias solo es verdadero con el resultado CON_DIFERENCIAS', () => {
    expect(hayDiferencias({ resultado: 'CON_DIFERENCIAS', ejecutada_en: '2026-11-10T05:00:00Z', diferencias: [] })).toBe(true)
    expect(hayDiferencias({ resultado: 'SIN_DIFERENCIAS', ejecutada_en: '2026-11-10T05:00:00Z', diferencias: [] })).toBe(false)
    expect(hayDiferencias({ resultado: null, ejecutada_en: null, diferencias: [] })).toBe(false)
    expect(hayDiferencias(undefined)).toBe(false)
  })
})
