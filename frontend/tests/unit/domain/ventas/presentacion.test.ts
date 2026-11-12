import { describe, expect, it } from 'vitest'

import {
  detalleDeObservacionDeVenta,
  etiquetaDeEstadoDeFacturacion,
  etiquetaDeEstadoDeVenta,
  etiquetaDeModoDeConfirmacion,
  etiquetaDeObservacionDeVenta,
  etiquetaDePoliticaDeCredito,
  etiquetaDeResolucionDeCredito,
  etiquetaDeVersion,
  observacionesDeLineaDeVenta,
  observacionesGeneralesDeVenta,
  textoDeCantidadDeLinea,
  textoDeDescuentoCongelado,
  type ObservacionDeVenta,
} from '../../../../src/domain/ventas/presentacion'
import { proponerTrasDuplicado } from '../../../../src/domain/ventas/numeracion'
import { cantidadInicialDeProducto } from '../../../../src/domain/ventas/composicion'

const STOCK_NEGATIVO: ObservacionDeVenta = {
  codigo: 'STOCK_NEGATIVO',
  estado: 'PENDIENTE',
  detalle: { linea_id: 'l1', producto_id: 'p', saldo_resultante: -4 },
}
const SIN_COSTO: ObservacionDeVenta = { codigo: 'VENTA_SIN_COSTO', estado: 'PENDIENTE', detalle: { linea_id: 'l2', producto_id: 'p' } }
const DEUDA: ObservacionDeVenta = { codigo: 'CONSUMIDOR_FINAL_CON_DEUDA', estado: 'PENDIENTE', detalle: { total: '4300.00', cobranza: '4000.00' } }

describe('observaciones de la venta (SYN-07, STK-05)', () => {
  it('las de una línea van junto a ella, por identificador, y las demás quedan como generales', () => {
    const todas = [STOCK_NEGATIVO, SIN_COSTO, DEUDA]
    expect(observacionesDeLineaDeVenta(todas, 'l1')).toEqual([STOCK_NEGATIVO])
    expect(observacionesDeLineaDeVenta(todas, 'l2')).toEqual([SIN_COSTO])
    expect(observacionesDeLineaDeVenta(todas, 'l3')).toEqual([])
    expect(observacionesGeneralesDeVenta(todas)).toEqual([DEUDA])
  })

  it('una observación de línea sin linea_id no se esconde: queda entre las generales', () => {
    const rara: ObservacionDeVenta = { codigo: 'STOCK_NEGATIVO', estado: 'PENDIENTE', detalle: {} }
    expect(observacionesGeneralesDeVenta([rara])).toEqual([rara])
  })

  it('etiquetas legibles y el código tal cual si no se conoce', () => {
    expect(etiquetaDeObservacionDeVenta('STOCK_NEGATIVO')).toBe('Stock negativo')
    expect(etiquetaDeObservacionDeVenta('VENTA_SIN_COSTO')).toBe('Venta sin costo')
    expect(etiquetaDeObservacionDeVenta('CODIGO_NUEVO')).toBe('CODIGO_NUEVO')
  })

  it('el stock negativo muestra el saldo resultante; el consumidor final con deuda, total y cobranza', () => {
    expect(detalleDeObservacionDeVenta(STOCK_NEGATIVO)).toBe('Saldo resultante: -4 unidades')
    expect(detalleDeObservacionDeVenta(DEUDA)).toBe('Total $ 4.300,00 · cobrado $ 4.000,00')
    expect(detalleDeObservacionDeVenta(SIN_COSTO)).toBeNull()
  })
})

describe('etiquetas de la venta', () => {
  it('estado, facturación y modo de confirmación', () => {
    expect(etiquetaDeEstadoDeVenta('CONFIRMADA')).toBe('Confirmada')
    expect(etiquetaDeEstadoDeVenta('ANULADA')).toBe('Anulada')
    expect(etiquetaDeEstadoDeFacturacion('NO_REQUIERE')).toBe('No requiere factura')
    expect(etiquetaDeEstadoDeFacturacion('PENDIENTE')).toBe('Pendiente de facturar')
    expect(etiquetaDeModoDeConfirmacion('ONLINE')).toBe('Con conexión')
    expect(etiquetaDeModoDeConfirmacion('OFFLINE')).toBe('Sin conexión')
  })

  it('versión de lista con su estado', () => {
    expect(etiquetaDeVersion(2, 'VIGENTE')).toBe('Versión 2 (vigente)')
    expect(etiquetaDeVersion(1, 'HISTORICA')).toBe('Versión 1 (anterior)')
    expect(etiquetaDeVersion(3, 'PROGRAMADA')).toBe('Versión 3 (programada)')
  })

  it('cantidad de una línea en su presentación con la equivalencia en unidades (CAT-08)', () => {
    expect(textoDeCantidadDeLinea({ cantidad: 2, presentacion_nombre: 'Caja x6', cantidad_base: 12 })).toBe('2 × Caja x6 (12 unidades)')
    expect(textoDeCantidadDeLinea({ cantidad: 1, presentacion_nombre: 'Botella', cantidad_base: 1 })).toBe('1 × Botella (1 unidad)')
    expect(textoDeCantidadDeLinea({ cantidad: 1, presentacion_nombre: null, cantidad_base: 6 })).toBe('1 × Presentación (6 unidades)')
  })
})

describe('número tras NUMERO_DUPLICADO (D4)', () => {
  it('propone el siguiente del mayor entre el servidor, el navegador y el número que acaba de fallar', () => {
    expect(proponerTrasDuplicado({ prefijo: 'V01', ultimoCorrelativo: 42 }, null, 'V01-000042')).toBe('V01-000043')
    expect(proponerTrasDuplicado({ prefijo: 'V01', ultimoCorrelativo: 41 }, null, 'V01-000042')).toBe('V01-000043')
    expect(proponerTrasDuplicado({ prefijo: 'V01', ultimoCorrelativo: 41 }, 50, 'V01-000042')).toBe('V01-000051')
  })
})

describe('cantidad inicial al agregar un producto', () => {
  const botella = { presentacionId: 'b', nombre: 'Botella', unidadesBase: 1, esReferencia: false }
  const caja = { presentacionId: 'c', nombre: 'Caja x6', unidadesBase: 6, esReferencia: true }
  it('una caja si se vende por caja; si no, una unidad', () => {
    expect(cantidadInicialDeProducto([botella, caja])).toEqual({ cajas: 1, unidades: 0 })
    expect(cantidadInicialDeProducto([botella])).toEqual({ cajas: 0, unidades: 1 })
    expect(cantidadInicialDeProducto([caja])).toEqual({ cajas: 1, unidades: 0 })
  })
})

describe('descuentos y crédito congelados (change 18b, D20; DSC-08, CRE-10)', () => {
  it('un descuento automático dice la regla, el porcentaje y el importe', () => {
    expect(
      textoDeDescuentoCongelado({
        origen: 'AUTOMATICO',
        regla_nombre: 'Volumen vinos',
        porcentaje: '0.050000',
        importe: '1562.50',
        motivo_nombre: null,
        autorizador_nombre: null,
      }),
    ).toBe('Descuento automático «Volumen vinos» 5 %: −$ 1.562,50')
  })

  it('uno de importe fijo no inventa un porcentaje', () => {
    expect(
      textoDeDescuentoCongelado({
        origen: 'AUTOMATICO',
        regla_nombre: 'Promo',
        porcentaje: null,
        importe: '500.00',
        motivo_nombre: null,
        autorizador_nombre: null,
      }),
    ).toBe('Descuento automático «Promo»: −$ 500,00')
  })

  it('un descuento manual dice el porcentaje, el motivo y quién autorizó', () => {
    expect(
      textoDeDescuentoCongelado({
        origen: 'MANUAL',
        regla_nombre: null,
        porcentaje: '0.100000',
        importe: '3125.00',
        motivo_nombre: 'Cliente frecuente',
        autorizador_nombre: 'Marta',
      }),
    ).toBe('Descuento manual 10 % (motivo: Cliente frecuente; autorizó Marta): −$ 3.125,00')
    expect(
      textoDeDescuentoCongelado({
        origen: 'MANUAL',
        regla_nombre: null,
        porcentaje: '0.050000',
        importe: '10.00',
        motivo_nombre: null,
        autorizador_nombre: null,
      }),
    ).toBe('Descuento manual 5 %: −$ 10,00')
  })

  it('la resolución y la política del crédito se dicen en palabras; una desconocida se muestra tal cual', () => {
    expect(etiquetaDeResolucionDeCredito('PIN_SUPERVISOR')).toBe('Autorizado con el PIN de un supervisor')
    expect(etiquetaDeResolucionDeCredito('SIN_EXCESO')).toBe('Sin exceso')
    expect(etiquetaDeResolucionDeCredito('NUEVA')).toBe('NUEVA')
    expect(etiquetaDePoliticaDeCredito('BLOQUEAR')).toBe('Bloquear')
  })

  it('las observaciones nuevas tienen su título (los mismos del tema de ayuda)', () => {
    expect(etiquetaDeObservacionDeVenta('AUTORIZACION_OFFLINE')).toBe('Autorización sin señal')
    expect(etiquetaDeObservacionDeVenta('DESCUENTO_DIFIERE')).toBe('Descuentos distintos')
    expect(etiquetaDeObservacionDeVenta('EXCESO_CREDITO_DETECTADO_SYNC')).toBe('Exceso de crédito detectado al sincronizar')
  })
})
