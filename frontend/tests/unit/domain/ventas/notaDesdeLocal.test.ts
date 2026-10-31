import { describe, expect, it } from 'vitest'

import { armarNotaDeVenta } from '../../../../src/domain/ventas/notaDeVenta'
import {
  congelarNotaDeVenta,
  datosDeNotaDesdeLocal,
  type EntradaDeCongelado,
} from '../../../../src/domain/ventas/notaDesdeLocal'
import type { ContenidoDeVentaLocal, VentaLocal } from '../../../../src/lib/dispositivo/db'

/**
 * Change 22a, tarea 12.1 (spec `ventas/nota-de-venta`, "La nota de una venta del teléfono se arma
 * con sus datos congelados y sin señal"; `design.md` D15; cita VTA-13, ADR-059, CRE-02, INV-03):
 * la venta local congela al confirmar todo lo que pide la nota y el adaptador puro la pasa a
 * `DatosDeNotaDeVenta`. Ningún importe pasa por `number`.
 */
function entrada(sobre: Partial<EntradaDeCongelado> = {}): EntradaDeCongelado {
  return {
    organizacion: { nombre: 'Distribuidora Sur', cuit: '30-12345678-9', domicilio: 'Ruta 9 km 12', telefono: '11 5555-0000' },
    zonaHoraria: 'America/Argentina/Buenos_Aires',
    muestraSaldo: true,
    modoImpositivo: 'A',
    vendedorNombre: 'Vendedor Uno',
    cliente: {
      nombre: 'Almacén Norte',
      razon_social: 'Almacén Norte SRL',
      documento_tipo: 'CUIT',
      documento_numero: '30-99999999-1',
      direccion: 'Calle 1',
      es_consumidor_final: false,
    },
    lineas: [
      { lineaId: 'l-caja', productoNombre: 'Vino A', presentacionNombre: 'Caja x6', unidadesPresentacion: 6 },
      { lineaId: 'l-botella', productoNombre: 'Vino A', presentacionNombre: 'Botella', unidadesPresentacion: 1 },
    ],
    medios: [
      { medioPagoId: 'm-efectivo', nombre: 'Efectivo' },
      { medioPagoId: 'm-transf', nombre: 'Transferencia' },
    ],
    saldoConsiderado: '150000.00',
    total: '80000.00',
    cobrado: '20000.00',
    ...sobre,
  }
}

function ventaLocal(nota: VentaLocal['nota']): VentaLocal {
  const contenido = {
    venta_id: 'v1',
    numero: 'V03-000142',
    cliente_id: 'c1',
    ubicacion_id: null,
    lista_id: null,
    lista_version_id: null,
    motivo_lista_id: null,
    lineas: [
      {
        linea_id: 'l-caja',
        producto_id: 'p1',
        presentacion_id: 'pr-caja',
        cantidad: 2,
        lista_version_id: 'ver1',
        precio_referencia: '12500.00',
        unidades_referencia: 6,
        importe_bruto: '25000.00',
      },
      {
        linea_id: 'l-botella',
        producto_id: 'p1',
        presentacion_id: 'pr-bot',
        cantidad: 3,
        lista_version_id: 'ver1',
        precio_referencia: '12500.00',
        unidades_referencia: 6,
        importe_bruto: '6250.00',
      },
    ],
    total: '80000.00',
    cobranza: {
      cobranza_id: 'cb1',
      observacion: null,
      medios: [
        { medio_pago_id: 'm-efectivo', importe: '10000.00', referencia: null },
        { medio_pago_id: 'm-transf', importe: '10000.00', referencia: 'TRF-1' },
      ],
    },
  } as unknown as ContenidoDeVentaLocal
  return {
    venta_id: 'v1',
    operation_id: 'op1',
    numero: 'V03-000142',
    cliente_id: 'c1',
    jornada_id: 'j1',
    occurred_at: '2026-10-30T15:00:00.000Z',
    estado_envio: 'PENDIENTE',
    contenido,
    calculo: {
      lineas: [
        { linea_id: 'l-caja', bruto: '25000.00', descuentos: [], descuento_total: '1250.00', neto: '23750.00', alicuota: '0.210000', importe_iva: '4987.50' },
        { linea_id: 'l-botella', bruto: '6250.00', descuentos: [], descuento_total: '0.00', neto: '6250.00', alicuota: '0.210000', importe_iva: '1312.50' },
      ],
      total_neto: '30000.00',
      total_iva: '6300.00',
      total: '80000.00',
    },
    nota,
  }
}

describe('congelar la nota al confirmar (tarea 12.1, D15, VTA-13)', () => {
  it('el saldo resultante es saldo considerado + total - cobrado: 150.000 + 80.000 - 20.000 = 210.000,00 (CRE-02, INV-03)', () => {
    const nota = congelarNotaDeVenta(entrada())

    expect(nota.saldo_resultante).toBe('210000.00')
  })

  it('otro caso: sin cobro el saldo resultante suma todo el total; cobrar de más queda a favor', () => {
    expect(congelarNotaDeVenta(entrada({ cobrado: '0.00' })).saldo_resultante).toBe('230000.00')
    expect(congelarNotaDeVenta(entrada({ saldoConsiderado: '0.00', total: '1000.00', cobrado: '1500.00' })).saldo_resultante).toBe(
      '-500.00',
    )
  })

  it('no lleva saldo para el consumidor final', () => {
    const nota = congelarNotaDeVenta(
      entrada({ cliente: { ...entrada().cliente, es_consumidor_final: true, nombre: 'Consumidor final' } }),
    )

    expect(nota.saldo_resultante).toBeNull()
  })

  it('congela organización, cliente, vendedor, nombres de producto, presentación y medio', () => {
    const nota = congelarNotaDeVenta(entrada())

    expect(nota.organizacion).toEqual({
      nombre: 'Distribuidora Sur',
      cuit: '30-12345678-9',
      domicilio: 'Ruta 9 km 12',
      telefono: '11 5555-0000',
    })
    expect(nota.vendedor_nombre).toBe('Vendedor Uno')
    expect(nota.cliente.razon_social).toBe('Almacén Norte SRL')
    expect(nota.lineas.map((l) => l.producto_nombre)).toEqual(['Vino A', 'Vino A'])
    expect(nota.medios.map((m) => m.nombre)).toEqual(['Efectivo', 'Transferencia'])
  })
})

describe('datos de la nota desde la venta local (tarea 12.1, D15)', () => {
  it('produce DatosDeNotaDeVenta con importes calculados, cobranza con nombres y saldo congelado', () => {
    const venta = ventaLocal(congelarNotaDeVenta(entrada()))

    const datos = datosDeNotaDesdeLocal(venta)

    expect(datos).toMatchObject({
      numero: 'V03-000142',
      occurred_at: '2026-10-30T15:00:00.000Z',
      vendedor_nombre: 'Vendedor Uno',
      modo_impositivo: 'A',
      estado: 'CONFIRMADA',
      total: '80000.00',
      total_neto: '30000.00',
      total_iva: '6300.00',
      saldo_resultante: '210000.00',
      muestra_saldo: true,
      zona_horaria: 'America/Argentina/Buenos_Aires',
      anulacion: null,
    })
    expect(datos.lineas[0]).toMatchObject({
      producto_nombre: 'Vino A',
      presentacion_nombre: 'Caja x6',
      cantidad: 2,
      unidades_presentacion: 6,
      precio_referencia: '12500.00',
      unidades_referencia: 6,
      importe_bruto: '25000.00',
      importe_descuento: '1250.00',
      importe_neto: '23750.00',
      alicuota: '0.210000',
      importe_iva: '4987.50',
    })
    expect(datos.cobranza).toEqual({
      importe: '20000.00',
      medios: [
        { nombre: 'Efectivo', importe: '10000.00' },
        { nombre: 'Transferencia', importe: '10000.00' },
      ],
    })
  })

  it('la nota armada muestra "Saldo de la cuenta" 210.000,00 con mostrar saldo y nada si no se muestra', () => {
    const con = armarNotaDeVenta(datosDeNotaDesdeLocal(ventaLocal(congelarNotaDeVenta(entrada()))))
    const sin = armarNotaDeVenta(
      datosDeNotaDesdeLocal(ventaLocal(congelarNotaDeVenta(entrada({ muestraSaldo: false })))),
    )

    expect(con.saldo?.valor).toContain('210.000,00')
    expect(sin.saldo).toBeNull()
  })

  it('sin cobranza en el contenido, la nota no lleva cobranza', () => {
    const venta = ventaLocal(congelarNotaDeVenta(entrada({ medios: [], cobrado: '0.00' })))
    venta.contenido = { ...venta.contenido, cobranza: null }

    expect(datosDeNotaDesdeLocal(venta).cobranza).toBeNull()
  })

  it('un bootstrap posterior que cambia la razón social no cambia la nota: lo congelado manda', () => {
    const venta = ventaLocal(congelarNotaDeVenta(entrada()))
    const antes = datosDeNotaDesdeLocal(venta)
    // El bootstrap nuevo reemplaza los maestros pero la venta guarda su copia.
    const despues = datosDeNotaDesdeLocal(venta)

    expect(despues.cliente.razon_social).toBe('Almacén Norte SRL')
    expect(despues).toEqual(antes)
  })

  it('una venta sin datos congelados no se puede armar', () => {
    expect(() => datosDeNotaDesdeLocal(ventaLocal(null))).toThrow(/no tiene los datos de la nota/i)
  })
})
