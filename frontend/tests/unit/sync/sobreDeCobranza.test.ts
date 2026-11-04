import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import { describe, expect, it } from 'vitest'

import { armarSobreDeCobranza } from '../../../src/sync/sobre'

/**
 * Change 23, tarea 1.1 (`design.md` D2; SYN-01, COB-01, INV-03): el fixture de contrato
 * `shared/fixtures/sync/cobranza-registrar-offline.json` que el backend valida con el esquema del
 * lote (`backend/tests/unit/test_fixture_cobranza_registrar_offline.py`) y que el teléfono arma
 * igual con `armarSobreDeCobranza` (usada por `sync/registrarCobranzaLocal.ts`).
 */
const RUTA = resolve(
  dirname(fileURLToPath(import.meta.url)),
  '../../../../shared/fixtures/sync/cobranza-registrar-offline.json',
)

interface SobreDeCobranza {
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
    cobranza_id: string
    cliente_id: string
    importe: string
    medios: { medio_pago_id: string; importe: string; referencia: string | null }[]
    observacion: string | null
  }
}

const NOMBRES = ['un_medio', 'dos_medios_con_referencia', 'con_observacion'] as const

const fixture = JSON.parse(readFileSync(RUTA, 'utf-8')) as {
  simbolos: string[]
  sobres: Record<(typeof NOMBRES)[number], SobreDeCobranza>
}

const IDS = {
  '{{operation_id}}': '0190a000-0000-7000-8000-000000000001',
  '{{usuario_id}}': '0190a000-0000-7000-8000-000000000002',
  '{{dispositivo_id}}': '0190a000-0000-7000-8000-000000000003',
  '{{jornada_id}}': '0190a000-0000-7000-8000-000000000004',
  '{{cobranza_id}}': '0190a000-0000-7000-8000-000000000005',
  '{{cliente_id}}': '0190a000-0000-7000-8000-000000000006',
  '{{medio_efectivo_id}}': '0190a000-0000-7000-8000-000000000007',
  '{{medio_transferencia_id}}': '0190a000-0000-7000-8000-000000000008',
} as const

function conIdsReales(sobre: SobreDeCobranza): SobreDeCobranza {
  let texto = JSON.stringify(sobre)
  for (const [simbolo, id] of Object.entries(IDS)) texto = texto.split(simbolo).join(id)
  return JSON.parse(texto) as SobreDeCobranza
}

describe('fixture cobranza-registrar-offline (SYN-01, COB-01, INV-03)', () => {
  it('trae los tres sobres de COBRANZA_REGISTRAR v1 en modo OFFLINE con la jornada y sin credenciales', () => {
    expect(Object.keys(fixture.sobres)).toEqual([...NOMBRES])
    for (const sobre of Object.values(fixture.sobres)) {
      expect(sobre.tipo).toBe('COBRANZA_REGISTRAR')
      expect(sobre.version).toBe(1)
      expect(sobre.modo).toBe('OFFLINE')
      expect(sobre.jornada_id).toBe('{{jornada_id}}')
      expect(sobre).not.toHaveProperty('credenciales')
      expect(sobre.occurred_at).toMatch(/Z$/)
    }
  })

  it('los importes viajan como string y los medios suman el importe (INV-03, INV-08)', () => {
    for (const sobre of Object.values(fixture.sobres)) {
      const { importe, medios } = sobre.contenido
      expect(importe).toMatch(/^\d+\.\d{2}$/)
      const centavos = medios.reduce((acumulado, m) => acumulado + Math.round(Number(m.importe) * 100), 0)
      expect(centavos).toBe(Math.round(Number(importe) * 100))
    }
  })

  it('declara exactamente los símbolos que usa', () => {
    const usados = new Set(JSON.stringify(fixture.sobres).match(/\{\{[a-z_]+\}\}/g) ?? [])
    expect([...usados].sort()).toEqual([...fixture.simbolos].sort())
  })
})

describe('el teléfono arma los tres sobres del fixture igual (SYN-01, COB-01)', () => {
  it.each(NOMBRES)('%s', (nombre) => {
    const esperado = fixture.sobres[nombre]
    const real = conIdsReales(esperado)

    const armado = armarSobreDeCobranza({
      operationId: IDS['{{operation_id}}'],
      usuarioId: IDS['{{usuario_id}}'],
      dispositivoId: IDS['{{dispositivo_id}}'],
      jornadaId: IDS['{{jornada_id}}'],
      occurredAt: new Date(esperado.occurred_at),
      secuencia: esperado.secuencia,
      appVersion: esperado.app_version,
      cobranzaId: real.contenido.cobranza_id,
      clienteId: real.contenido.cliente_id,
      importe: real.contenido.importe,
      medios: real.contenido.medios,
      observacion: real.contenido.observacion,
    })

    expect(armado).toEqual(real)
  })

  it('la observación ausente viaja como null y la referencia vacía como null, no como texto vacío', () => {
    const armado = armarSobreDeCobranza({
      operationId: IDS['{{operation_id}}'],
      usuarioId: IDS['{{usuario_id}}'],
      dispositivoId: IDS['{{dispositivo_id}}'],
      jornadaId: IDS['{{jornada_id}}'],
      occurredAt: new Date('2026-10-19T12:30:00.000Z'),
      secuencia: 8,
      appVersion: '1.0.0',
      cobranzaId: IDS['{{cobranza_id}}'],
      clienteId: IDS['{{cliente_id}}'],
      importe: '100.00',
      medios: [{ medio_pago_id: IDS['{{medio_efectivo_id}}'], importe: '100.00', referencia: null }],
      observacion: null,
    })

    expect(armado.contenido).toMatchObject({ observacion: null })
    expect((armado.contenido as { medios: { referencia: string | null }[] }).medios[0].referencia).toBeNull()
  })
})
