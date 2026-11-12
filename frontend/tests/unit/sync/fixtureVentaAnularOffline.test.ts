import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import { describe, expect, it } from 'vitest'

import { armarSobreDeAnulacion } from '../../../src/sync/sobre'

/**
 * Change 22d, tarea 4.1 (`design.md` D1 y D6; SYN-01, VTA-24, VTA-22): el fixture de contrato
 * `shared/fixtures/sync/venta-anular-offline.json` que el backend valida con el esquema del lote
 * (`backend/tests/unit/test_fixture_venta_anular_offline.py`) y que el teléfono arma igual. Esta
 * mitad fija la forma que el teléfono debe producir; la comparación con la función que arma el
 * sobre de la anulación (`armarSobreDeAnulacion`, usada por `sync/anularVentaLocal.ts`) la agrega
 * la tarea 6.2.
 */
const RUTA = resolve(
  dirname(fileURLToPath(import.meta.url)),
  '../../../../shared/fixtures/sync/venta-anular-offline.json',
)

interface SobreDeAnulacion {
  operation_id: string
  tipo: string
  version: number
  modo: string
  usuario_id: string
  dispositivo_id: string
  jornada_id: string
  occurred_at: string
  secuencia: number
  app_version: string
  contenido: {
    venta_id: string
    motivo_id: string
    observacion: string | null
    devuelve_dinero?: boolean
  }
}

const fixture = JSON.parse(readFileSync(RUTA, 'utf-8')) as {
  simbolos: string[]
  sobres: Record<'con_devolucion' | 'sin_devolucion' | 'sin_cobro', SobreDeAnulacion>
}

describe('fixture venta-anular-offline (SYN-01, VTA-24)', () => {
  it('trae los tres sobres de VENTA_ANULAR v1 en modo OFFLINE con la jornada y sin credenciales', () => {
    expect(Object.keys(fixture.sobres)).toEqual(['con_devolucion', 'sin_devolucion', 'sin_cobro'])
    for (const sobre of Object.values(fixture.sobres)) {
      expect(sobre.tipo).toBe('VENTA_ANULAR')
      expect(sobre.version).toBe(1)
      expect(sobre.modo).toBe('OFFLINE')
      expect(sobre.jornada_id).toBe('{{jornada_id}}')
      expect(sobre).not.toHaveProperty('credenciales')
      expect(sobre.occurred_at).toMatch(/Z$/)
    }
  })

  it('indica la devolución solo cuando hubo cobro en el acto (VTA-22)', () => {
    expect(fixture.sobres.con_devolucion.contenido.devuelve_dinero).toBe(true)
    expect(fixture.sobres.sin_devolucion.contenido.devuelve_dinero).toBe(false)
    expect(fixture.sobres.sin_cobro.contenido).not.toHaveProperty('devuelve_dinero')
  })

  it('el contenido lleva solo la venta, el motivo y la observación, sin importes ni organización', () => {
    for (const sobre of Object.values(fixture.sobres)) {
      const claves = Object.keys(sobre.contenido).sort()
      expect(claves.filter((c) => c !== 'devuelve_dinero')).toEqual(['motivo_id', 'observacion', 'venta_id'])
    }
    expect(fixture.sobres.con_devolucion.contenido.observacion).toBe('El cliente no recibio la mercaderia')
    expect(fixture.sobres.sin_devolucion.contenido.observacion).toBeNull()
  })

  it('declara exactamente los símbolos que usa', () => {
    const texto = JSON.stringify(fixture.sobres)
    const usados = new Set(texto.match(/\{\{[a-z_]+\}\}/g) ?? [])
    expect([...usados].sort()).toEqual([...fixture.simbolos].sort())
  })
})

const IDS = {
  '{{operation_id}}': '0190a000-0000-7000-8000-000000000001',
  '{{usuario_id}}': '0190a000-0000-7000-8000-000000000002',
  '{{dispositivo_id}}': '0190a000-0000-7000-8000-000000000003',
  '{{jornada_id}}': '0190a000-0000-7000-8000-000000000004',
  '{{venta_id}}': '0190a000-0000-7000-8000-000000000005',
  '{{motivo_id}}': '0190a000-0000-7000-8000-000000000006',
} as const

function conIdsReales(sobre: SobreDeAnulacion): unknown {
  let texto = JSON.stringify(sobre)
  for (const [simbolo, id] of Object.entries(IDS)) texto = texto.split(simbolo).join(id)
  return JSON.parse(texto)
}

describe('el teléfono arma los tres sobres del fixture igual (SYN-01, VTA-24, VTA-22)', () => {
  const CASOS = [
    ['con_devolucion', true],
    ['sin_devolucion', false],
    ['sin_cobro', null],
  ] as const

  it.each(CASOS)('%s', (nombre, devuelveDinero) => {
    const esperado = fixture.sobres[nombre]
    const armado = armarSobreDeAnulacion({
      operationId: IDS['{{operation_id}}'],
      usuarioId: IDS['{{usuario_id}}'],
      dispositivoId: IDS['{{dispositivo_id}}'],
      jornadaId: IDS['{{jornada_id}}'],
      occurredAt: new Date(esperado.occurred_at),
      secuencia: esperado.secuencia,
      appVersion: esperado.app_version,
      ventaId: IDS['{{venta_id}}'],
      motivoId: IDS['{{motivo_id}}'],
      observacion: esperado.contenido.observacion,
      devuelveDinero,
    })

    expect(armado).toEqual(conIdsReales(esperado))
  })

  it('sin cobro el contenido no tiene devuelve_dinero, ni siquiera como undefined', () => {
    const armado = armarSobreDeAnulacion({
      operationId: IDS['{{operation_id}}'],
      usuarioId: IDS['{{usuario_id}}'],
      dispositivoId: IDS['{{dispositivo_id}}'],
      jornadaId: IDS['{{jornada_id}}'],
      occurredAt: new Date('2026-10-19T12:30:00.000Z'),
      secuencia: 9,
      appVersion: '1.0.0',
      ventaId: IDS['{{venta_id}}'],
      motivoId: IDS['{{motivo_id}}'],
      observacion: null,
      devuelveDinero: null,
    })
    expect(Object.keys(armado.contenido ?? {})).toEqual(['venta_id', 'motivo_id', 'observacion'])
  })
})
