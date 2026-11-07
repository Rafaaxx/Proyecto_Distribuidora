import type { ReporteDeVentas } from '../../../../../src/features/reportes/api'

/** El sobre de una lista paginada del servidor (D14): por defecto, una sola página con todas las filas. */
export function sobreDePrueba<T>(filas: T[], campos: Partial<Record<string, unknown>> = {}) {
  return {
    filas,
    pagina: 1,
    tamano: 50,
    total_filas: filas.length,
    paginas: filas.length === 0 ? 0 : 1,
    ...campos,
  }
}

/** Cifras de una fila del reporte de ventas, con la utilidad (CON) o sin ella (SUP). */
export function cifras(
  campos: Partial<Record<string, unknown>> = {},
  conUtilidad = true,
): Record<string, unknown> {
  return {
    cantidad_ventas: 2,
    cajas_equivalentes: '2.50',
    unidades_base: 15,
    importe_bruto: '1600.00',
    importe_descuento: '100.00',
    importe_neto: '1500.00',
    importe_iva: '0.00',
    total: '1500.00',
    costo_vendido: conUtilidad ? '850.00' : null,
    utilidad: conUtilidad ? '350.00' : null,
    sin_costo: conUtilidad ? { lineas: 1, importe_neto: '300.00' } : null,
    ...campos,
  }
}

/** El cuerpo de `GET /reportes/ventas` (change 26, lote 3): una venta anulada fuera de los totales. */
export function reporteDeVentas(conUtilidad = true, campos: Partial<Record<string, unknown>> = {}): ReporteDeVentas {
  return {
    periodo: { desde: '2026-11-01', hasta: '2026-11-06', zona_horaria: 'America/Argentina/Mendoza' },
    ve_utilidad: conUtilidad,
    resumen: cifras({}, conUtilidad),
    por_dia: sobreDePrueba([
      cifras({ fecha: '2026-11-03', total: '777.00' }, conUtilidad),
      cifras({ fecha: '2026-11-02' }, conUtilidad),
    ]),
    por_vendedor: [
      cifras({ vendedor_id: 'v1', vendedor_nombre: 'Vendedor Uno', total: '1200.00' }, conUtilidad),
      cifras({ vendedor_id: 'v2', vendedor_nombre: 'Vendedor Dos', total: '300.00' }, conUtilidad),
    ],
    por_producto: sobreDePrueba([
      {
        producto_id: 'p1',
        codigo: 'VIN-001',
        nombre: 'Vino Tinto',
        cajas_equivalentes: '2.50',
        unidades_base: 15,
        importe_neto: '1200.00',
        presentaciones: [
          { presentacion_id: 'pr1', nombre: 'Caja x6', unidades_presentacion: 6, cantidad: 2, unidades_base: 12 },
          { presentacion_id: 'pr2', nombre: 'Botella', unidades_presentacion: 1, cantidad: 3, unidades_base: 3 },
        ],
      },
    ]),
    anuladas: {
      cantidad: 1,
      total: '500.00',
      ventas: sobreDePrueba([
        {
          venta_id: 'a1',
          numero: 'V-0007',
          occurred_at: '2026-10-30T15:00:00Z',
          cliente_id: 'c1',
          cliente_nombre: 'Almacén Norte',
          vendedor_id: 'v1',
          vendedor_nombre: 'Vendedor Uno',
          total: '500.00',
          anulada_en: '2026-11-02T13:00:00Z',
          motivo: 'Error de carga',
          devuelve_dinero: true,
        },
      ]),
    },
    ...campos,
  } as ReporteDeVentas
}

/** El reporte de un período sin ventas (REP-01). */
export function reporteVacio(): ReporteDeVentas {
  return reporteDeVentas(true, {
    resumen: cifras(
      {
        cantidad_ventas: 0,
        cajas_equivalentes: '0.00',
        unidades_base: 0,
        importe_bruto: '0.00',
        importe_descuento: '0.00',
        importe_neto: '0.00',
        total: '0.00',
        costo_vendido: '0.00',
        utilidad: '0.00',
        sin_costo: { lineas: 0, importe_neto: '0.00' },
      },
      true,
    ),
    por_dia: sobreDePrueba([]),
    por_vendedor: [],
    por_producto: sobreDePrueba([]),
    anuladas: { cantidad: 0, total: '0.00', ventas: sobreDePrueba([]) },
  })
}
