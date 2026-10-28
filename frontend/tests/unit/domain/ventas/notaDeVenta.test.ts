/**
 * Contenido de la nota de venta (change 20, tareas 1.1, 1.3 y 1.4; VTA-13, VTA-02, VTA-04, CAT-08,
 * PRC-22, CLI-03, CRE-02, ADR-008, ADR-045, ADR-058, ADR-059). Las pruebas de los modos B y C usan
 * datos fabricados: la confirmación rechaza esos modos hasta la etapa 4.
 */
import { describe, expect, it } from 'vitest'

import { parsearImporteDesdeApi } from '../../../../src/lib/money'
import {
  armarNotaDeVenta,
  formatearAlicuota,
  LEYENDA_DE_NOTA,
  NotaNoDisponibleParaModoC,
  TITULO_DE_NOTA,
  type DatosDeNotaDeVenta,
  type LineaDeNota,
} from '../../../../src/domain/ventas/notaDeVenta'

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
    organizacion: { nombre: 'Distribuidora Norte', cuit: '30-12345678-9', domicilio: 'Av. Siempreviva 742', telefono: '261 555-0100' },
    zona_horaria: 'America/Argentina/Mendoza',
    muestra_saldo: false,
    cliente: {
      nombre: 'Kiosco La Esquina',
      razon_social: 'La Esquina SRL',
      documento_tipo: 'CUIT',
      documento_numero: '30-98765432-1',
      direccion: 'San Martín 100',
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

describe('armarNotaDeVenta: contenido de VTA-13', () => {
  it('lleva el título y la leyenda de la constante (ADR-008)', () => {
    const nota = armarNotaDeVenta(datos())
    expect(TITULO_DE_NOTA).toBe('Nota de venta')
    expect(LEYENDA_DE_NOTA).toBe('Documento no válido como factura')
    expect(nota.titulo).toBe('Nota de venta')
    expect(nota.leyenda).toBe('Documento no válido como factura')
  })

  it('muestra número, fecha y hora en la zona de la organización y vendedor', () => {
    const nota = armarNotaDeVenta(datos())
    expect(nota.numero).toBe('V03-000142')
    expect(nota.fechaHora).toBe('20/10/2026 12:30')
    expect(nota.vendedor).toBe('Vendedor Uno')
    expect(armarNotaDeVenta(datos({ zona_horaria: 'UTC' })).fechaHora).toBe('20/10/2026 15:30')
  })

  it('muestra la organización con domicilio y teléfono, o sin esos renglones', () => {
    const completa = armarNotaDeVenta(datos()).organizacion
    expect(completa).toEqual({
      nombre: 'Distribuidora Norte',
      renglones: ['CUIT 30-12345678-9', 'Av. Siempreviva 742', 'Tel. 261 555-0100'],
    })
    const minima = armarNotaDeVenta(
      datos({ organizacion: { nombre: 'Distribuidora Norte', cuit: null, domicilio: null, telefono: null } }),
    ).organizacion
    expect(minima).toEqual({ nombre: 'Distribuidora Norte', renglones: [] })
  })

  it('muestra el cliente con razón social, documento y dirección, y omite lo que falta (CLI-01)', () => {
    expect(armarNotaDeVenta(datos()).cliente).toEqual({
      nombre: 'Kiosco La Esquina',
      renglones: ['La Esquina SRL', 'CUIT 30-98765432-1', 'San Martín 100'],
    })
    const base = datos().cliente
    expect(
      armarNotaDeVenta(
        datos({ cliente: { ...base, razon_social: null, documento_tipo: null, documento_numero: null, direccion: null } }),
      ).cliente,
    ).toEqual({ nombre: 'Kiosco La Esquina', renglones: [] })
  })

  it('muestra "Consumidor final" para el consumidor final (CLI-03)', () => {
    const base = datos().cliente
    const nota = armarNotaDeVenta(
      datos({
        cliente: { ...base, nombre: 'Consumidor final', razon_social: null, documento_tipo: null, documento_numero: null, direccion: null, es_consumidor_final: true },
      }),
    )
    expect(nota.cliente).toEqual({ nombre: 'Consumidor final', renglones: [] })
  })

  it('arma las líneas en su orden con cantidad en la presentación y precio por presentación (VTA-02, CAT-08, PRC-22)', () => {
    const nota = armarNotaDeVenta(
      datos({
        lineas: [
          linea(),
          linea({ cantidad: 3, unidades_presentacion: 1, presentacion_nombre: 'Unidad', importe_bruto: '300.00', importe_neto: '270.00', importe_descuento: '30.00' }),
        ],
        total_neto: '2670.00',
        total: '2670.00',
      }),
    )
    expect(nota.columnas).toEqual(['Cantidad', 'Producto', 'Precio', 'Bruto', 'Descuento', 'Importe'])
    expect(nota.lineas).toEqual([
      {
        cantidad: '2 × Caja x12 (24 unidades)',
        producto: 'Gaseosa Cola 1,5 L · Caja x12',
        precio: '$ 1.200,00',
        bruto: '$ 2.400,00',
        descuento: '',
        importe: '$ 2.400,00',
      },
      {
        cantidad: '3 × Unidad (3 unidades)',
        producto: 'Gaseosa Cola 1,5 L · Unidad',
        precio: '$ 100,00',
        bruto: '$ 300,00',
        descuento: '$ 30,00',
        importe: '$ 270,00',
      },
    ])
  })

  it('el precio por presentación sale de la regla del bruto con la referencia (PRC-22)', () => {
    const nota = armarNotaDeVenta(
      datos({
        lineas: [linea({ precio_referencia: '1800.00', unidades_referencia: 12, unidades_presentacion: 6, cantidad: 1, importe_bruto: '900.00', importe_neto: '900.00' })],
        total_neto: '900.00',
        total: '900.00',
      }),
    )
    expect(nota.lineas[0]?.precio).toBe('$ 900,00')
  })

  it('en modo A no hay filas de IVA aunque las líneas tengan alícuota congelada, y el total es el congelado (VTA-04, ADR-045)', () => {
    const nota = armarNotaDeVenta(
      datos({
        lineas: [linea({ alicuota: '0.210000' }), linea({ alicuota: '0.105000', importe_bruto: '1000.00', importe_neto: '1000.00' })],
        total_neto: '3400.00',
        total: '3400.00',
      }),
    )
    expect(nota.totales).toEqual([
      { rotulo: 'Subtotal', valor: '$ 3.400,00', destacado: false },
      { rotulo: 'Total', valor: '$ 3.400,00', destacado: true },
    ])
    expect(nota.columnas).not.toContain('IVA %')
  })

  it('muestra Subtotal, Descuentos y Total cuando hay descuentos', () => {
    const nota = armarNotaDeVenta(
      datos({
        lineas: [linea({ importe_bruto: '2400.00', importe_descuento: '240.00', importe_neto: '2160.00' })],
        total_neto: '2160.00',
        total: '2160.00',
      }),
    )
    expect(nota.totales).toEqual([
      { rotulo: 'Subtotal', valor: '$ 2.400,00', destacado: false },
      { rotulo: 'Descuentos', valor: '$ 240,00', destacado: false },
      { rotulo: 'Total', valor: '$ 2.160,00', destacado: true },
    ])
  })

  it('muestra la cobranza con cada medio e importe, o "Sin cobro en el acto"', () => {
    const con = armarNotaDeVenta(
      datos({
        cobranza: { importe: '2000.00', medios: [{ nombre: 'Efectivo', importe: '1500.00' }, { nombre: 'Transferencia', importe: '500.00' }] },
      }),
    ).cobranza
    expect(con).toEqual({
      rotulo: 'Cobrado',
      total: '$ 2.000,00',
      medios: [
        { nombre: 'Efectivo', importe: '$ 1.500,00' },
        { nombre: 'Transferencia', importe: '$ 500,00' },
      ],
    })
    expect(armarNotaDeVenta(datos()).cobranza).toEqual({ rotulo: 'Sin cobro en el acto', total: null, medios: [] })
  })

  it('una venta vigente sin parámetro de saldo no lleva saldo ni marca', () => {
    const nota = armarNotaDeVenta(datos())
    expect(nota.saldo).toBeNull()
    expect(nota.anulacion).toBeNull()
  })
})

describe('armarNotaDeVenta: saldo de la cuenta (D4; VTA-13, CRE-02, CLI-03)', () => {
  it('con "mostrar saldo" activo muestra el saldo ya calculado (150.000 + 80.000 - 20.000)', () => {
    const nota = armarNotaDeVenta(
      datos({
        muestra_saldo: true,
        saldo_resultante: '210000.00',
        total_neto: '80000.00',
        total: '80000.00',
        lineas: [linea({ importe_bruto: '80000.00', importe_neto: '80000.00' })],
        cobranza: { importe: '20000.00', medios: [{ nombre: 'Efectivo', importe: '20000.00' }] },
      }),
    )
    expect(nota.saldo).toEqual({ rotulo: 'Saldo de la cuenta después de esta venta', valor: '$ 210.000,00' })
  })

  it('un saldo negativo se muestra como saldo a favor', () => {
    const nota = armarNotaDeVenta(datos({ muestra_saldo: true, saldo_resultante: '-3000.00' }))
    expect(nota.saldo).toEqual({ rotulo: 'Saldo a favor del cliente después de esta venta', valor: '$ 3.000,00' })
  })

  it('un saldo en cero se muestra como saldo', () => {
    const nota = armarNotaDeVenta(datos({ muestra_saldo: true, saldo_resultante: '0.00' }))
    expect(nota.saldo).toEqual({ rotulo: 'Saldo de la cuenta después de esta venta', valor: '$ 0,00' })
  })

  it('no lo muestra con el parámetro inactivo', () => {
    expect(armarNotaDeVenta(datos({ muestra_saldo: false, saldo_resultante: '210000.00' })).saldo).toBeNull()
  })

  it('no lo muestra al consumidor final', () => {
    const base = datos().cliente
    const nota = armarNotaDeVenta(
      datos({ muestra_saldo: true, saldo_resultante: '100.00', cliente: { ...base, nombre: 'Consumidor final', es_consumidor_final: true } }),
    )
    expect(nota.saldo).toBeNull()
  })

  it('no lo muestra si no hay saldo congelado (saldo nulo)', () => {
    expect(armarNotaDeVenta(datos({ muestra_saldo: true, saldo_resultante: null })).saldo).toBeNull()
  })

  it('no lo muestra en una venta anulada', () => {
    const nota = armarNotaDeVenta(
      datos({
        muestra_saldo: true,
        saldo_resultante: '210000.00',
        estado: 'ANULADA',
        anulacion: { anulada_en: '2026-10-21T13:00:00Z', motivo_nombre: 'Error de carga', devuelve_dinero: false },
      }),
    )
    expect(nota.saldo).toBeNull()
  })
})

describe('armarNotaDeVenta: venta anulada (D5; VTA-20, VTA-22, ADR-058)', () => {
  const anulada = { anulada_en: '2026-10-21T13:05:00Z', motivo_nombre: 'Error de carga' }

  it('lleva la marca, la fecha, el motivo y "Se devolvió lo cobrado." con devolución', () => {
    const nota = armarNotaDeVenta(
      datos({
        estado: 'ANULADA',
        cobranza: { importe: '2000.00', medios: [{ nombre: 'Efectivo', importe: '2000.00' }] },
        anulacion: { ...anulada, devuelve_dinero: true },
      }),
    )
    expect(nota.anulacion).toEqual({
      marca: 'ANULADA',
      renglones: ['Venta anulada el 21/10/2026 10:05. Motivo: Error de carga.', 'Se devolvió lo cobrado.'],
    })
  })

  it('dice que lo cobrado quedó a favor del cliente si no se devolvió', () => {
    const nota = armarNotaDeVenta(
      datos({
        estado: 'ANULADA',
        cobranza: { importe: '2000.00', medios: [{ nombre: 'Efectivo', importe: '2000.00' }] },
        anulacion: { ...anulada, devuelve_dinero: false },
      }),
    )
    expect(nota.anulacion?.renglones).toEqual([
      'Venta anulada el 21/10/2026 10:05. Motivo: Error de carga.',
      'Lo cobrado quedó a favor del cliente.',
    ])
  })

  it('sin cobranza no habla del destino de lo cobrado', () => {
    const nota = armarNotaDeVenta(datos({ estado: 'ANULADA', anulacion: { ...anulada, devuelve_dinero: true } }))
    expect(nota.anulacion?.renglones).toEqual(['Venta anulada el 21/10/2026 10:05. Motivo: Error de carga.'])
  })

  it('una venta vigente no lleva marca', () => {
    expect(armarNotaDeVenta(datos({ estado: 'CONFIRMADA' })).anulacion).toBeNull()
  })
})

describe('formatearAlicuota (D14; VTA-04)', () => {
  it.each([
    ['0.210000', '21 %'],
    ['0.105000', '10,5 %'],
    ['0.000000', '0 %'],
    ['0.027000', '2,7 %'],
  ])('%s se muestra como %s', (fraccion, texto) => {
    expect(formatearAlicuota(fraccion)).toBe(texto)
  })
})

describe('armarNotaDeVenta: modo B, IVA discriminado (D14; VTA-04, VTA-03, INV-14, INV-10, ADR-009)', () => {
  const lineasB = [
    linea({ importe_bruto: '10000.00', importe_neto: '10000.00', alicuota: '0.210000', importe_iva: '2100.00' }),
    linea({ importe_bruto: '4000.00', importe_neto: '4000.00', alicuota: '0.210000', importe_iva: '840.00' }),
    linea({ importe_bruto: '2000.00', importe_neto: '2000.00', alicuota: '0.105000', importe_iva: '210.00' }),
  ]

  it('muestra Neto, una fila de IVA por alícuota en orden descendente y Total (ejemplo de la spec)', () => {
    const nota = armarNotaDeVenta(
      datos({ modo_impositivo: 'B', lineas: lineasB, total_neto: '16000.00', total_iva: '3150.00', total: '19150.00' }),
    )
    expect(nota.totales).toEqual([
      { rotulo: 'Subtotal', valor: '$ 16.000,00', destacado: false },
      { rotulo: 'Neto', valor: '$ 16.000,00', destacado: false },
      { rotulo: 'IVA 21 %', valor: '$ 2.940,00', destacado: false },
      { rotulo: 'IVA 10,5 %', valor: '$ 210,00', destacado: false },
      { rotulo: 'Total', valor: '$ 19.150,00', destacado: true },
    ])
    expect(nota.columnas).toEqual(['Cantidad', 'Producto', 'Precio', 'Bruto', 'Descuento', 'Importe'])
  })

  it('las filas de IVA suman el total_iva congelado', () => {
    const datosB = datos({ modo_impositivo: 'B', lineas: lineasB, total_neto: '16000.00', total_iva: '3150.00', total: '19150.00' })
    const filasDeIva = armarNotaDeVenta(datosB).totales.filter((fila) => fila.rotulo.startsWith('IVA '))
    const suma = filasDeIva.reduce(
      (acc, fila) => acc.add(parsearImporteDesdeApi(fila.valor.replace('$ ', '').replace(/\./g, '').replace(',', '.'))),
      parsearImporteDesdeApi('0'),
    )
    expect(suma.toFixed(2)).toBe(datosB.total_iva)
  })

  it('con una sola alícuota hay una sola fila de IVA', () => {
    const nota = armarNotaDeVenta(
      datos({
        modo_impositivo: 'B',
        lineas: [linea({ importe_bruto: '1000.00', importe_neto: '1000.00', alicuota: '0.210000', importe_iva: '210.00' })],
        total_neto: '1000.00',
        total_iva: '210.00',
        total: '1210.00',
      }),
    )
    expect(nota.totales.map((fila) => fila.rotulo)).toEqual(['Subtotal', 'Neto', 'IVA 21 %', 'Total'])
    expect(nota.totales[3]?.valor).toBe('$ 1.210,00')
  })

  it('una línea al 0 % genera la fila "IVA 0 %" de $ 0,00, al final', () => {
    const nota = armarNotaDeVenta(
      datos({
        modo_impositivo: 'B',
        lineas: [
          linea({ importe_bruto: '1000.00', importe_neto: '1000.00', alicuota: '0.210000', importe_iva: '210.00' }),
          linea({ importe_bruto: '500.00', importe_neto: '500.00', alicuota: '0.000000', importe_iva: '0.00' }),
        ],
        total_neto: '1500.00',
        total_iva: '210.00',
        total: '1710.00',
      }),
    )
    expect(nota.totales.slice(2, 4)).toEqual([
      { rotulo: 'IVA 21 %', valor: '$ 210,00', destacado: false },
      { rotulo: 'IVA 0 %', valor: '$ 0,00', destacado: false },
    ])
  })

  it('agrupa por valor de alícuota aunque venga escrita distinto', () => {
    const nota = armarNotaDeVenta(
      datos({
        modo_impositivo: 'B',
        lineas: [
          linea({ importe_neto: '100.00', importe_bruto: '100.00', alicuota: '0.21', importe_iva: '21.00' }),
          linea({ importe_neto: '100.00', importe_bruto: '100.00', alicuota: '0.210000', importe_iva: '21.00' }),
        ],
        total_neto: '200.00',
        total_iva: '42.00',
        total: '242.00',
      }),
    )
    expect(nota.totales.filter((fila) => fila.rotulo.startsWith('IVA '))).toEqual([
      { rotulo: 'IVA 21 %', valor: '$ 42,00', destacado: false },
    ])
  })

  it('el modo congelado manda: una venta de modo A sale sin IVA aunque la organización hoy sea inscripta (INV-10, ADR-045)', () => {
    // La nota no recibe ni usa la condición actual de la organización: los datos son los de la venta.
    const nota = armarNotaDeVenta(
      datos({ modo_impositivo: 'A', lineas: [linea({ alicuota: '0.210000', importe_iva: '0.00' })] }),
    )
    expect(nota.totales.map((fila) => fila.rotulo)).toEqual(['Subtotal', 'Total'])
  })
})

describe('armarNotaDeVenta: modo C no disponible (D14; deuda de la etapa 4, ADR-059)', () => {
  const lineasC = [
    linea({ alicuota: '0.210000', importe_iva: '416.53' }),
    linea({ alicuota: '0.105000', importe_iva: '227.15' }),
  ]

  it('rechaza una venta de modo C con NOTA_MODO_C_NO_DISPONIBLE y no devuelve contenido', () => {
    const intento = (): unknown => armarNotaDeVenta(datos({ modo_impositivo: 'C', lineas: lineasC }))
    expect(intento).toThrow(NotaNoDisponibleParaModoC)
    try {
      intento()
    } catch (error) {
      expect(error).toBeInstanceOf(NotaNoDisponibleParaModoC)
      expect((error as NotaNoDisponibleParaModoC).codigo).toBe('NOTA_MODO_C_NO_DISPONIBLE')
    }
  })

  it('rechaza también con una sola alícuota', () => {
    expect(() => armarNotaDeVenta(datos({ modo_impositivo: 'C', lineas: [linea({ alicuota: '0.210000' })] }))).toThrow(
      NotaNoDisponibleParaModoC,
    )
  })

  it('el rechazo por modo prevalece sobre una venta anulada', () => {
    expect(() =>
      armarNotaDeVenta(
        datos({
          modo_impositivo: 'C',
          estado: 'ANULADA',
          lineas: lineasC,
          anulacion: { anulada_en: '2026-10-21T13:00:00Z', motivo_nombre: 'Error de carga', devuelve_dinero: true },
        }),
      ),
    ).toThrow(NotaNoDisponibleParaModoC)
  })

  it('los modos A y B no lo lanzan', () => {
    expect(() => armarNotaDeVenta(datos({ modo_impositivo: 'A' }))).not.toThrow()
    expect(() => armarNotaDeVenta(datos({ modo_impositivo: 'B', lineas: lineasC }))).not.toThrow()
  })
})
