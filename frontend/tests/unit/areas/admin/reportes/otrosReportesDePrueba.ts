import type {
  ReporteDeAjustes,
  ReporteDeObservaciones,
  ReporteDeRendiciones,
  ReporteDeSaldosDeClientes,
  ReporteDeSaldosDeProveedores,
  ResumenDeJornadaDeReporte,
} from '../../../../../src/features/reportes/api'
import { sobreDePrueba } from './reporteDePrueba'

/** Fixtures de los demás reportes (change 26, lote 5): la forma de los cuerpos del servidor. */

const PERIODO = { desde: '2026-11-01', hasta: '2026-11-06', zona_horaria: 'America/Argentina/Mendoza' }

const total = (cantidad: number, importe: string) => ({ cantidad, total: importe })

const cobranzas = (cantidad: number, importe: string, medios: [string, string][] = []) => ({
  cantidad,
  total: importe,
  por_medio: medios.map(([nombre, monto], i) => ({ medio_pago_id: `m${String(i)}`, nombre, total: monto })),
})

/** Una jornada del reporte; sobreescribible por campo. */
export function jornadaDeRendicion(campos: Partial<Record<string, unknown>> = {}) {
  return {
    jornada_id: 'j1',
    vendedor_id: 'v1',
    vendedor_nombre: 'Vendedor Uno',
    ubicacion_id: 'u1',
    ubicacion_nombre: 'Camión 1',
    estado: 'CERRADA',
    en_curso: false,
    abierta_en: '2026-11-02T11:00:00Z',
    rendida_en: '2026-11-02T22:00:00Z',
    cerrada_en: '2026-11-03T12:00:00Z',
    liberada_en: null,
    con_conteo: true,
    ventas: total(2, '1500.00'),
    anuladas: total(1, '300.00'),
    cobranzas: cobranzas(2, '1200.00', [
      ['Efectivo', '900.00'],
      ['Transferencia', '300.00'],
    ]),
    despues_de_la_rendicion: null,
    faltantes: 2,
    sobrantes: 1,
    valor_de_diferencias: '750.00',
    ...campos,
  }
}

/** El reporte de rendiciones: una jornada cerrada, una en curso y una liberada sin conteo. */
export function reporteDeRendiciones(conCostos = true, campos: Partial<Record<string, unknown>> = {}): ReporteDeRendiciones {
  const valor = (v: string) => (conCostos ? v : null)
  return {
    periodo: PERIODO,
    ve_costos: conCostos,
    jornadas: sobreDePrueba([
      jornadaDeRendicion({ valor_de_diferencias: valor('750.00') }),
      jornadaDeRendicion({
        jornada_id: 'j2',
        vendedor_id: 'v2',
        vendedor_nombre: 'Vendedor Dos',
        ubicacion_nombre: 'Camión 2',
        estado: 'ABIERTA',
        en_curso: true,
        rendida_en: null,
        cerrada_en: null,
        con_conteo: false,
        ventas: total(1, '400.00'),
        anuladas: total(0, '0.00'),
        cobranzas: cobranzas(0, '0.00'),
        faltantes: null,
        sobrantes: null,
        valor_de_diferencias: null,
      }),
      jornadaDeRendicion({
        jornada_id: 'j3',
        vendedor_id: 'v2',
        vendedor_nombre: 'Vendedor Dos',
        ubicacion_nombre: 'Camión 2',
        estado: 'LIBERADA',
        rendida_en: null,
        cerrada_en: null,
        liberada_en: '2026-11-04T09:00:00Z',
        con_conteo: false,
        ventas: total(3, '2000.00'),
        anuladas: total(0, '0.00'),
        cobranzas: cobranzas(1, '500.00', [['Efectivo', '500.00']]),
        despues_de_la_rendicion: {
          ventas: total(1, '100.00'),
          anuladas: total(0, '0.00'),
          cobranzas: cobranzas(0, '0.00'),
        },
        faltantes: null,
        sobrantes: null,
        valor_de_diferencias: null,
      }),
    ]),
    por_vendedor: [
      {
        vendedor_id: 'v1',
        vendedor_nombre: 'Vendedor Uno',
        jornadas: 1,
        ventas: total(2, '1500.00'),
        anuladas: total(1, '300.00'),
        cobranzas: cobranzas(2, '1200.00', [
          ['Efectivo', '900.00'],
          ['Transferencia', '300.00'],
        ]),
        faltantes: 2,
        sobrantes: 1,
        valor_de_diferencias: valor('750.00'),
      },
      {
        vendedor_id: 'v2',
        vendedor_nombre: 'Vendedor Dos',
        jornadas: 2,
        ventas: total(4, '2400.00'),
        anuladas: total(0, '0.00'),
        cobranzas: cobranzas(1, '500.00', [['Efectivo', '500.00']]),
        faltantes: 0,
        sobrantes: 0,
        valor_de_diferencias: valor('0.00'),
      },
    ],
    ...campos,
  } as unknown as ReporteDeRendiciones
}

/** El resumen de RUT-07 de una jornada desde el reporte (sin valores de costo salvo `conCostos`). */
export function detalleDeRendicion(conCostos = false): ResumenDeJornadaDeReporte {
  const dinero = {
    ventas: total(2, '1500.00'),
    anuladas: total(1, '300.00'),
    cobranzas: cobranzas(1, '900.00', [['Efectivo', '900.00']]),
    cobranzas_anuladas: cobranzas(0, '0.00'),
  }
  return {
    jornada_id: 'j1',
    estado: 'CERRADA',
    con_conteo: true,
    rendida_en: '2026-11-02T22:00:00Z',
    lineas: [
      {
        producto_id: 'p1',
        producto_codigo: 'V1',
        producto_nombre: 'Vino A',
        unidades_referencia: 6,
        nombre_referencia: 'Caja x6',
        al_abrir: 20,
        ingresos: 0,
        ventas: 12,
        anulaciones: 0,
        otros: 0,
        esperado: 8,
        contado: 6,
        diferencia: -2,
        ...(conCostos ? { valor_diferencia: '750.00' } : {}),
      },
    ],
    dinero,
    despues_de_la_rendicion: null,
    ...(conCostos ? { valor_de_diferencias: '750.00' } : {}),
  } as unknown as ResumenDeJornadaDeReporte
}

const CONTADOR_VACIO = { total: 0, pendientes: 0 }

/** El reporte de observaciones: `vendedor` con avisos y rechazos, `vendedor2` solo con una venta sin conexión. */
export function reporteDeObservaciones(campos: Partial<Record<string, unknown>> = {}): ReporteDeObservaciones {
  return {
    periodo: PERIODO,
    vendedores: [
      {
        vendedor_id: 'v1',
        vendedor_nombre: 'Vendedor Uno',
        ventas_sin_conexion: 3,
        avisos: { total: 3, pendientes: 2 },
        avisos_por_codigo: [
          { codigo: 'STOCK_NEGATIVO', total: 2, pendientes: 1 },
          { codigo: 'EXCESO_CREDITO_DETECTADO_SYNC', total: 1, pendientes: 1 },
        ],
        rechazadas: { total: 1, pendientes: 1 },
        excesos_de_credito_detectados: { total: 1, pendientes: 1 },
      },
      {
        vendedor_id: 'v2',
        vendedor_nombre: 'Vendedor Dos',
        ventas_sin_conexion: 1,
        avisos: CONTADOR_VACIO,
        avisos_por_codigo: [],
        rechazadas: CONTADOR_VACIO,
        excesos_de_credito_detectados: CONTADOR_VACIO,
      },
    ],
    ...campos,
  } as unknown as ReporteDeObservaciones
}

const producto = (campos: Partial<Record<string, unknown>> = {}) => ({
  producto_id: 'p1',
  codigo: 'VIN-001',
  nombre: 'Vino Tinto',
  entradas: 0,
  salidas: 9,
  valor_de_entradas: '0.00',
  valor_de_salidas: '4500.00',
  unidades_sin_costo: 0,
  ...campos,
})

/** El reporte de ajustes: «Rotura» (9 unidades salidas), «Diferencias de rendición» y un ajuste anulado. */
export function reporteDeAjustes(conCostos = true, campos: Partial<Record<string, unknown>> = {}): ReporteDeAjustes {
  const valor = (v: string) => (conCostos ? v : null)
  const sinCosto = (n: number) => (conCostos ? n : null)
  return {
    periodo: PERIODO,
    ve_costos: conCostos,
    motivos: [
      {
        motivo_id: 'mo1',
        motivo_nombre: 'Rotura',
        ajustes: 2,
        entradas: 0,
        salidas: 9,
        valor_de_entradas: valor('0.00'),
        valor_de_salidas: valor('4500.00'),
        unidades_sin_costo: sinCosto(0),
        productos: [
          producto({
            valor_de_entradas: valor('0.00'),
            valor_de_salidas: valor('4500.00'),
            unidades_sin_costo: sinCosto(0),
          }),
        ],
      },
    ],
    diferencias_de_rendicion: {
      entradas: 1,
      salidas: 2,
      valor_de_entradas: valor('100.00'),
      valor_de_salidas: valor('250.00'),
      unidades_sin_costo: sinCosto(0),
      productos: [],
    },
    ajustes_anulados: 1,
    ...campos,
  } as unknown as ReporteDeAjustes
}

/** Saldos de clientes: un deudor con límite, uno a favor y uno sin límite sin vendedor. */
export function reporteDeSaldosDeClientes(campos: Partial<Record<string, unknown>> = {}): ReporteDeSaldosDeClientes {
  return {
    clientes: sobreDePrueba([
      {
        cliente_id: 'c1',
        codigo: 'CLI-001',
        nombre: 'Almacén Norte',
        razon_social: 'Almacén Norte SRL',
        vendedor_id: 'v1',
        vendedor_nombre: 'Vendedor Uno',
        estado: 'ACTIVO',
        limite_credito: '5000.00',
        saldo: '1000.00',
        disponible: '4000.00',
      },
      {
        cliente_id: 'c2',
        codigo: 'CLI-002',
        nombre: 'Kiosco Sur',
        razon_social: null,
        vendedor_id: null,
        vendedor_nombre: null,
        estado: 'SUSPENDIDO',
        limite_credito: null,
        saldo: '-200.00',
        disponible: null,
      },
    ]),
    // «Vendedor Dos» tiene clientes solo en otra página: no aparece en las filas.
    vendedores: [
      { id: 'v1', nombre: 'Vendedor Uno' },
      { id: 'v2', nombre: 'Vendedor Dos' },
    ],
    total_adeudado: '1000.00',
    total_a_favor: '-200.00',
    ...campos,
  } as unknown as ReporteDeSaldosDeClientes
}

/** Saldos de proveedores: uno con deuda y otro con saldo a favor. */
export function reporteDeSaldosDeProveedores(campos: Partial<Record<string, unknown>> = {}): ReporteDeSaldosDeProveedores {
  return {
    proveedores: sobreDePrueba([
      { proveedor_id: 'pr1', nombre: 'Bodega Sur', estado: 'ACTIVO', saldo: '5000.00' },
      { proveedor_id: 'pr2', nombre: 'Distribuidora Este', estado: 'INACTIVO', saldo: '-80.00' },
    ]),
    total_adeudado: '5000.00',
    total_a_favor: '-80.00',
    ...campos,
  } as unknown as ReporteDeSaldosDeProveedores
}
