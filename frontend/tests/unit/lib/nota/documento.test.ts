/**
 * Definición del documento PDF de la nota (change 20, tarea 2.2; VTA-13, ADR-008; `design.md` D7, D14).
 * Se prueba la definición pura que pdfmake consume, no el PDF.
 */
import { describe, expect, it } from 'vitest'

import { armarNotaDeVenta, type DatosDeNotaDeVenta, type LineaDeNota } from '../../../../src/domain/ventas/notaDeVenta'
import { documentoDeNota } from '../../../../src/lib/nota/documento'

function linea(sobre: Partial<LineaDeNota> = {}): LineaDeNota {
  return {
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
    ...sobre,
  }
}

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
    lineas: [linea()],
    total_neto: '2400.00',
    total_iva: '0.00',
    total: '2400.00',
    cobranza: null,
    saldo_resultante: null,
    anulacion: null,
    ...sobre,
  }
}

/** Todos los textos de un árbol de contenido de pdfmake, en orden. */
function textosDe(nodo: unknown): string[] {
  if (typeof nodo === 'string') return [nodo]
  if (Array.isArray(nodo)) return nodo.flatMap(textosDe)
  if (nodo !== null && typeof nodo === 'object') {
    return Object.entries(nodo as Record<string, unknown>).flatMap(([clave, valor]) =>
      ['text', 'stack', 'columns', 'table', 'body', 'content'].includes(clave) ? textosDe(valor) : [],
    )
  }
  return []
}

/** Las tablas del documento, en orden de aparición. */
function tablasDe(nodo: unknown): { body: unknown[][] }[] {
  if (Array.isArray(nodo)) return nodo.flatMap(tablasDe)
  if (nodo !== null && typeof nodo === 'object') {
    const registro = nodo as Record<string, unknown>
    const propias = registro.table !== undefined ? [registro.table as { body: unknown[][] }] : []
    return [...propias, ...tablasDe(registro.stack), ...tablasDe(registro.columns)]
  }
  return []
}

function documento(sobre: Partial<DatosDeNotaDeVenta> = {}) {
  return documentoDeNota(armarNotaDeVenta(datos(sobre)))
}

describe('documentoDeNota (VTA-13, ADR-008, D7)', () => {
  it('es una página A4 vertical con el título y la leyenda al pie', () => {
    const definicion = documento()
    expect(definicion.pageSize).toBe('A4')
    expect(definicion.pageOrientation).toBe('portrait')
    const textos = textosDe(definicion.content)
    expect(textos).toContain('Nota de venta')
    expect(textosDe(definicion.footer)).toEqual(['Documento no válido como factura'])
  })

  it('la tabla de líneas tiene las seis columnas en orden y una fila por línea', () => {
    const definicion = documento({ lineas: [linea(), linea({ producto_nombre: 'Agua 2 L' })], total_neto: '4800.00', total: '4800.00' })
    const [lineas] = tablasDe(definicion.content)
    expect(lineas?.body).toHaveLength(3)
    expect(textosDe(lineas?.body[0])).toEqual(['Cantidad', 'Producto', 'Precio', 'Bruto', 'Descuento', 'Importe'])
    expect(textosDe(lineas?.body[1])).toEqual([
      '2 × Caja x12 (24 unidades)',
      'Gaseosa Cola 1,5 L · Caja x12',
      '$ 1.200,00',
      '$ 2.400,00',
      '',
      '$ 2.400,00',
    ])
    expect(textosDe(lineas?.body[2])).toContain('Agua 2 L · Caja x12')
  })

  it('muestra los totales y el Total destacado', () => {
    const textos = textosDe(documento().content)
    expect(textos).toContain('Subtotal')
    expect(textos).toContain('Total')
    expect(textos).toContain('$ 2.400,00')
  })

  it('una nota sin descuentos, cobranza ni saldo dice "Sin cobro en el acto" y no tiene marca', () => {
    const definicion = documento()
    const textos = textosDe(definicion.content)
    expect(textos).toContain('Sin cobro en el acto')
    expect(textos).not.toContain('Descuentos')
    expect(textos.some((texto) => texto.startsWith('Saldo'))).toBe(false)
    expect(definicion.watermark).toBeUndefined()
  })

  it('con cobranza lista cada medio y con "mostrar saldo" agrega el saldo', () => {
    const textos = textosDe(
      documento({
        muestra_saldo: true,
        saldo_resultante: '210000.00',
        cobranza: { importe: '20000.00', medios: [{ nombre: 'Efectivo', importe: '20000.00' }] },
      }).content,
    )
    expect(textos).toEqual(expect.arrayContaining(['Cobrado', 'Efectivo', '$ 20.000,00']))
    expect(textos).toEqual(expect.arrayContaining(['Saldo de la cuenta después de esta venta', '$ 210.000,00']))
  })

  it('una nota anulada lleva la marca de agua ANULADA y la constancia', () => {
    const definicion = documento({
      estado: 'ANULADA',
      anulacion: { anulada_en: '2026-10-21T13:05:00Z', motivo_nombre: 'Error de carga', devuelve_dinero: true },
      cobranza: { importe: '2400.00', medios: [{ nombre: 'Efectivo', importe: '2400.00' }] },
    })
    expect(definicion.watermark).toMatchObject({ text: 'ANULADA' })
    const textos = textosDe(definicion.content)
    expect(textos).toContain('Venta anulada el 21/10/2026 10:05. Motivo: Error de carga.')
    expect(textos).toContain('Se devolvió lo cobrado.')
  })

  it('una nota de modo B muestra Neto, el IVA por alícuota y Total en el bloque de totales (D14)', () => {
    const definicion = documento({
      modo_impositivo: 'B',
      lineas: [
        linea({ importe_bruto: '10000.00', importe_neto: '10000.00', importe_iva: '2100.00' }),
        linea({ importe_bruto: '2000.00', importe_neto: '2000.00', alicuota: '0.105000', importe_iva: '210.00' }),
      ],
      total_neto: '12000.00',
      total_iva: '2310.00',
      total: '14310.00',
    })
    const tablas = tablasDe(definicion.content)
    const totales = tablas[tablas.length - 1]
    const rotulos = totales?.body.map((fila) => textosDe(fila)[0])
    expect(rotulos).toEqual(['Subtotal', 'Neto', 'IVA 21 %', 'IVA 10,5 %', 'Total'])
    expect(textosDe(totales?.body[2])).toEqual(['IVA 21 %', '$ 2.100,00'])
    // Y la tabla de líneas sigue con seis columnas, sin "IVA %".
    expect(tablas[0]?.body[0]).toHaveLength(6)
  })
})
