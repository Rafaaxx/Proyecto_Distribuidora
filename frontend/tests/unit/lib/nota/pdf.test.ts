/**
 * Generación del PDF de la nota (change 20, tarea 2.3; ADR-008; `design.md` D8). Prueba de humo:
 * pdfmake se carga bajo demanda y el resultado es un PDF válido (cabecera `%PDF`).
 */
import { describe, expect, it } from 'vitest'

import { armarNotaDeVenta, type DatosDeNotaDeVenta } from '../../../../src/domain/ventas/notaDeVenta'
import { generarPdfDeNota } from '../../../../src/lib/nota/pdf'

function datos(sobre: Partial<DatosDeNotaDeVenta> = {}): DatosDeNotaDeVenta {
  return {
    organizacion: { nombre: 'Distribuidora Norte', cuit: '30-12345678-9', domicilio: null, telefono: null },
    zona_horaria: 'America/Argentina/Mendoza',
    muestra_saldo: false,
    cliente: {
      nombre: 'Kiosco La Esquina',
      razon_social: null,
      documento_tipo: null,
      documento_numero: null,
      direccion: null,
      es_consumidor_final: false,
    },
    numero: 'V03-000142',
    occurred_at: '2026-10-20T15:30:00Z',
    vendedor_nombre: 'Vendedor Uno',
    modo_impositivo: 'A',
    estado: 'CONFIRMADA',
    lineas: [
      {
        producto_nombre: 'Gaseosa Cola 1,5 L',
        presentacion_nombre: 'Caja x12',
        cantidad: 2,
        unidades_presentacion: 12,
        precio_referencia: '100.00',
        unidades_referencia: 1,
        importe_bruto: '2400.00',
        importe_descuento: '0.00',
        importe_neto: '2400.00',
        alicuota: '0.210000',
        importe_iva: '0.00',
      },
    ],
    total_neto: '2400.00',
    total_iva: '0.00',
    total: '2400.00',
    cobranza: null,
    saldo_resultante: null,
    anulacion: null,
    ...sobre,
  }
}

async function cabecera(blob: Blob): Promise<string> {
  return new TextDecoder('latin1').decode(await blob.slice(0, 5).arrayBuffer())
}

describe('generarPdfDeNota (ADR-008, D8)', () => {
  it('devuelve un Blob application/pdf que empieza con %PDF', async () => {
    const blob = await generarPdfDeNota(armarNotaDeVenta(datos()))
    expect(blob.type).toBe('application/pdf')
    expect(await cabecera(blob)).toBe('%PDF-')
    expect(blob.size).toBeGreaterThan(1000)
  }, 30000)

  it('también genera la nota anulada, con la marca de agua', async () => {
    const blob = await generarPdfDeNota(
      armarNotaDeVenta(
        datos({
          estado: 'ANULADA',
          anulacion: { anulada_en: '2026-10-21T13:05:00Z', motivo_nombre: 'Error de carga', devuelve_dinero: false },
        }),
      ),
    )
    expect(await cabecera(blob)).toBe('%PDF-')
  }, 30000)
})
