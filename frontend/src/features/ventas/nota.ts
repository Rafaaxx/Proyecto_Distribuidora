import type { DatosDeNotaDeVenta } from '../../domain/ventas/notaDeVenta'
import type { NotaDeVenta } from './api'

/**
 * Adaptador de la respuesta de `GET /ventas/{id}/nota` a los datos neutros de la nota (change 20,
 * tarea 7.1; VTA-13, INV-03; `design.md` D1). Los importes viajan como texto y se conservan así:
 * ninguno pasa por `number`. No decide nada de negocio (ni rechaza el modo C: eso es del armado).
 */

const SIN_NOMBRE = '—'

export function datosDeNotaDesdeApi(nota: NotaDeVenta): DatosDeNotaDeVenta {
  return {
    organizacion: nota.organizacion,
    zona_horaria: nota.zona_horaria,
    muestra_saldo: nota.muestra_saldo,
    cliente: { ...nota.cliente, direccion: nota.cliente.direccion === '' ? null : nota.cliente.direccion },
    numero: nota.numero,
    occurred_at: nota.occurred_at,
    vendedor_nombre: nota.vendedor_nombre ?? SIN_NOMBRE,
    modo_impositivo: nota.modo_impositivo as DatosDeNotaDeVenta['modo_impositivo'],
    estado: nota.estado,
    lineas: nota.lineas.map((linea) => ({
      producto_nombre: linea.producto_nombre ?? SIN_NOMBRE,
      presentacion_nombre: linea.presentacion_nombre,
      cantidad: linea.cantidad,
      unidades_presentacion: linea.unidades_presentacion,
      precio_referencia: linea.precio_referencia,
      unidades_referencia: linea.unidades_referencia,
      importe_bruto: linea.importe_bruto,
      importe_descuento: linea.importe_descuento,
      importe_neto: linea.importe_neto,
      alicuota: linea.alicuota,
      importe_iva: linea.importe_iva,
    })),
    total_neto: nota.total_neto,
    total_iva: nota.total_iva,
    total: nota.total,
    cobranza:
      nota.cobranza === null
        ? null
        : {
            importe: nota.cobranza.importe,
            medios: nota.cobranza.medios.map((medio) => ({ nombre: medio.nombre ?? SIN_NOMBRE, importe: medio.importe })),
          },
    saldo_resultante: nota.saldo_resultante,
    anulacion:
      nota.anulacion === null
        ? null
        : {
            anulada_en: nota.anulacion.anulada_en,
            motivo_nombre: nota.anulacion.motivo_nombre ?? SIN_NOMBRE,
            devuelve_dinero: nota.anulacion.devuelve_dinero === true,
          },
  }
}
