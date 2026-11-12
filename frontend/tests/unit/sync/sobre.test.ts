import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import { describe, expect, it } from 'vitest'

import {
  construirSolicitudDeVenta,
  type FormularioDeVenta,
  type LineaDelPedido,
} from '../../../src/domain/ventas/formularioVenta'
import type { ContenidoDeVentaLocal } from '../../../src/lib/dispositivo/db'
import { armarSobreDeVenta } from '../../../src/sync/sobre'

/**
 * Change 22a, tarea 3.2 (spec `sync/cola-local`, "La cola guarda el comando completo y en orden";
 * `design.md` D2; SYN-01, ADR-056, INV-03): la función pura que arma el sobre produce el fixture
 * de contrato `shared/fixtures/sync/venta-confirmar-offline.json`, que el backend valida y envía
 * al lote.
 */
const RUTA = resolve(dirname(fileURLToPath(import.meta.url)), '../../../../shared/fixtures/sync/venta-confirmar-offline.json')
const fixture = JSON.parse(readFileSync(RUTA, 'utf-8')) as { sobre: Record<string, unknown> }

const formulario: FormularioDeVenta = {
  clienteId: '{{cliente_id}}',
  ubicacionId: '',
  numero: '{{numero}}',
  listaId: '',
  versionId: '',
  motivoId: '',
  observacionCobranza: '',
  medios: [
    { medioPagoId: '{{medio_efectivo_id}}', importe: '10000.00', referencia: '' },
    { medioPagoId: '{{medio_transferencia_id}}', importe: '10000.00', referencia: 'TRF-0001' },
  ],
}

function lineaDelPedido(base: Partial<LineaDelPedido> & Pick<LineaDelPedido, 'lineaId' | 'presentacionId' | 'cantidad' | 'importeBruto'>): LineaDelPedido {
  return {
    productoId: '{{producto_id}}',
    listaVersionId: '{{lista_version_id}}',
    precioReferencia: '12500.00',
    unidadesReferencia: 6,
    ...base,
  }
}

function contenido(): ContenidoDeVentaLocal {
  const lineas = [
    lineaDelPedido({ lineaId: '{{linea_caja_id}}', presentacionId: '{{presentacion_caja_id}}', cantidad: 2, importeBruto: '25000.00' }),
    lineaDelPedido({ lineaId: '{{linea_botella_id}}', presentacionId: '{{presentacion_botella_id}}', cantidad: 3, importeBruto: '6250.00' }),
  ]
  const descuento = (importe: string) => ({
    origen: 'AUTOMATICO' as const,
    reglaId: '{{regla_id}}',
    porcentaje: '0.050000',
    importe,
  })
  const base = construirSolicitudDeVenta(
    formulario,
    lineas,
    '29687.50',
    '{{venta_id}}',
    '{{cobranza_id}}',
    false,
    {
      descuentoGeneral: null,
      motivoDescuentoId: null,
      descuentoAutorizadorId: null,
      aceptaExceso: false,
      creditoAutorizadorId: null,
      porLinea: new Map([
        ['{{linea_caja_id}}', { propio: null, descuentos: [descuento('1250.00')] }],
        ['{{linea_botella_id}}', { propio: null, descuentos: [descuento('312.50')] }],
      ]),
    },
  )
  return {
    ...base,
    credito: {
      limite: '150000.00',
      saldo_considerado: '150000.00',
      politica: 'AUTORIZAR',
      resolucion: 'TOLERANCIA_OFFLINE',
      acepta_exceso: true,
    },
  }
}

const entrada = {
  operationId: '{{operation_id}}',
  usuarioId: '{{usuario_id}}',
  dispositivoId: '{{dispositivo_id}}',
  jornadaId: '{{jornada_id}}',
  occurredAt: new Date('2026-10-19T12:00:00.000Z'),
  secuencia: 8,
  appVersion: '1.0.0',
}

describe('sobre de VENTA_CONFIRMAR sin conexión (change 22a, tarea 3.2)', () => {
  it('produce exactamente el fixture de contrato (SYN-01)', () => {
    expect(armarSobreDeVenta({ ...entrada, contenido: contenido() })).toEqual(fixture.sobre)
  })

  it('nunca incluye PIN ni credenciales aunque el contenido las traiga (ADR-056, SEG-05)', () => {
    const conPin = {
      ...contenido(),
      credenciales: [{ autorizador_id: '{{autorizador_id}}', pin: '123456' }],
    } as ContenidoDeVentaLocal

    const sobre = armarSobreDeVenta({ ...entrada, contenido: conPin })
    const texto = JSON.stringify(sobre)

    expect(texto).not.toContain('credenciales')
    expect(texto).not.toContain('123456')
    expect(texto).not.toContain('"pin"')
    expect(sobre).toEqual(fixture.sobre)
  })

  it('occurred_at sale en ISO UTC sin importar la zona del reloj (INV-03: nada pasa por number)', () => {
    const sobre = armarSobreDeVenta({
      ...entrada,
      occurredAt: new Date('2026-10-19T09:00:00-03:00'),
      contenido: contenido(),
    })

    expect(sobre.occurred_at).toBe('2026-10-19T12:00:00.000Z')
    expect(sobre.contenido.total).toBe('29687.50')
  })

  it('lleva la versión de la aplicación, la secuencia y el modo OFFLINE recibidos', () => {
    const sobre = armarSobreDeVenta({ ...entrada, secuencia: 9, appVersion: '2.3.1', contenido: contenido() })

    expect([sobre.app_version, sobre.secuencia, sobre.modo, sobre.version, sobre.tipo]).toEqual([
      '2.3.1',
      9,
      'OFFLINE',
      1,
      'VENTA_CONFIRMAR',
    ])
  })

  it('sin objeto de crédito el sobre no se arma (CRE-09: obligatorio sin conexión)', () => {
    const { credito: _credito, ...sinCredito } = contenido()
    void _credito
    expect(() => armarSobreDeVenta({ ...entrada, contenido: sinCredito as ContenidoDeVentaLocal })).toThrow(/crédito/)
  })
})
