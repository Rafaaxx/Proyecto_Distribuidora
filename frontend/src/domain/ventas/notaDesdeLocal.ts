import type { NotaCongelada, VentaLocal } from '../../lib/dispositivo/db'
import { parsearImporteDesdeApi, redondearImporte } from '../../lib/money'
import type { ClienteDeNota, DatosDeNotaDeVenta, OrganizacionDeNota } from './notaDeVenta'

/**
 * Nota de una venta del teléfono (change 22a, `design.md` D15; VTA-13, ADR-059, CRE-02, INV-03).
 * Al confirmar se congela todo lo que la nota necesita y no está en el contenido enviado
 * (`congelarNotaDeVenta`); después `datosDeNotaDesdeLocal` arma los mismos `DatosDeNotaDeVenta`
 * que el adaptador de la API, así `armarNotaDeVenta` y el PDF son los de siempre y funcionan sin
 * señal. Ningún importe pasa por `number`.
 */
export interface EntradaDeCongelado {
  organizacion: OrganizacionDeNota
  zonaHoraria: string
  muestraSaldo: boolean
  modoImpositivo: string
  vendedorNombre: string
  cliente: ClienteDeNota
  lineas: readonly {
    lineaId: string
    productoNombre: string
    presentacionNombre: string | null
    unidadesPresentacion: number
  }[]
  medios: readonly { medioPagoId: string; nombre: string }[]
  /** Saldo considerado del cliente antes de esta venta (CRE-08). */
  saldoConsiderado: string
  total: string
  cobrado: string
}

function modo(valor: string): 'A' | 'B' | 'C' {
  return valor === 'B' || valor === 'C' ? valor : 'A'
}

/** Saldo después de la venta = considerado + total - cobrado; nulo si el cliente es consumidor final. */
export function congelarNotaDeVenta(entrada: EntradaDeCongelado): NotaCongelada {
  const saldo = redondearImporte(
    parsearImporteDesdeApi(entrada.saldoConsiderado)
      .plus(parsearImporteDesdeApi(entrada.total))
      .minus(parsearImporteDesdeApi(entrada.cobrado)),
  )
  return {
    organizacion: { ...entrada.organizacion },
    zona_horaria: entrada.zonaHoraria,
    muestra_saldo: entrada.muestraSaldo,
    modo_impositivo: modo(entrada.modoImpositivo),
    vendedor_nombre: entrada.vendedorNombre,
    cliente: { ...entrada.cliente },
    lineas: entrada.lineas.map((l) => ({
      linea_id: l.lineaId,
      producto_nombre: l.productoNombre,
      presentacion_nombre: l.presentacionNombre,
      unidades_presentacion: l.unidadesPresentacion,
    })),
    medios: entrada.medios.map((m) => ({ medio_pago_id: m.medioPagoId, nombre: m.nombre })),
    saldo_resultante: entrada.cliente.es_consumidor_final ? null : saldo.toFixed(2),
  }
}

const SIN_NOMBRE = '—'

/** Los datos de la nota desde la venta local (contenido enviado + cálculo + lo congelado). */
export function datosDeNotaDesdeLocal(venta: VentaLocal): DatosDeNotaDeVenta {
  const congelada = venta.nota
  if (congelada === null) throw new Error(`La venta ${venta.numero} no tiene los datos de la nota guardados.`)
  const calculoPorLinea = new Map(venta.calculo.lineas.map((l) => [l.linea_id, l]))
  const nombrePorLinea = new Map(congelada.lineas.map((l) => [l.linea_id, l]))
  const nombreDeMedio = new Map(congelada.medios.map((m) => [m.medio_pago_id, m.nombre]))
  const cobranza = venta.contenido.cobranza ?? null

  return {
    organizacion: congelada.organizacion,
    zona_horaria: congelada.zona_horaria,
    muestra_saldo: congelada.muestra_saldo,
    cliente: congelada.cliente,
    numero: venta.numero,
    occurred_at: venta.occurred_at,
    vendedor_nombre: congelada.vendedor_nombre,
    modo_impositivo: congelada.modo_impositivo,
    estado: 'CONFIRMADA',
    lineas: venta.contenido.lineas.map((linea) => {
      const calculada = calculoPorLinea.get(linea.linea_id)
      const nombres = nombrePorLinea.get(linea.linea_id)
      if (calculada === undefined || nombres === undefined) {
        throw new Error(`La línea ${linea.linea_id} de la venta ${venta.numero} no tiene sus datos guardados.`)
      }
      return {
        producto_nombre: nombres.producto_nombre,
        presentacion_nombre: nombres.presentacion_nombre,
        cantidad: linea.cantidad,
        unidades_presentacion: nombres.unidades_presentacion,
        precio_referencia: linea.precio_referencia,
        unidades_referencia: linea.unidades_referencia,
        importe_bruto: calculada.bruto,
        importe_descuento: calculada.descuento_total,
        importe_neto: calculada.neto,
        alicuota: calculada.alicuota,
        importe_iva: calculada.importe_iva,
      }
    }),
    total_neto: venta.calculo.total_neto,
    total_iva: venta.calculo.total_iva,
    total: venta.calculo.total,
    cobranza:
      cobranza === null
        ? null
        : {
            importe: cobranza.medios
              .reduce((suma, m) => suma.plus(parsearImporteDesdeApi(m.importe)), parsearImporteDesdeApi('0'))
              .toFixed(2),
            medios: cobranza.medios.map((m) => ({
              nombre: nombreDeMedio.get(m.medio_pago_id) ?? SIN_NOMBRE,
              importe: m.importe,
            })),
          },
    saldo_resultante: congelada.saldo_resultante,
    anulacion: null,
  }
}
