import { useState } from 'react'
import { Link } from 'react-router-dom'

import { Card } from '../../../components/ui/Card'
import { Tabla, type ColumnaTabla } from '../../../components/ui/Table'
import { formatearUnidades } from '../../../domain/reportes/presentacion'
import type { ObservacionesDeVendedor } from '../../../features/reportes/api'
import type { FiltrosDePeriodo } from '../../../features/reportes/claves'
import { useReporteDeObservaciones } from '../../../features/reportes/hooks'
import { SiTienePermiso } from '../../../features/identidad/SiTienePermiso'
import { FiltroDePeriodo } from './FiltroDePeriodo'
import { EstadoDelReporte, TituloDePestana } from './piezas'

/** Un contador de avisos o rechazos: el total y, debajo, cuántos siguen pendientes (SYN-07). */
function ConPendientes({ total, pendientes }: { total: number; pendientes: number }) {
  return (
    <div className="flex flex-col">
      <span>{formatearUnidades(total)}</span>
      <span className="text-primary/70">Pendientes: {formatearUnidades(pendientes)}</span>
    </div>
  )
}

const COLUMNAS: ColumnaTabla<ObservacionesDeVendedor>[] = [
  { clave: 'vendedor', encabezado: 'Vendedor', render: (f) => f.vendedor_nombre },
  { clave: 'sinConexion', encabezado: 'Ventas sin conexión', render: (f) => formatearUnidades(f.ventas_sin_conexion) },
  {
    clave: 'avisos',
    encabezado: 'Avisos',
    render: (f) => <ConPendientes total={f.avisos.total} pendientes={f.avisos.pendientes} />,
  },
  {
    clave: 'rechazadas',
    encabezado: 'Rechazadas',
    render: (f) => <ConPendientes total={f.rechazadas.total} pendientes={f.rechazadas.pendientes} />,
  },
  {
    clave: 'excesos',
    encabezado: 'Excesos de crédito detectados',
    render: (f) => (
      <ConPendientes total={f.excesos_de_credito_detectados.total} pendientes={f.excesos_de_credito_detectados.pendientes} />
    ),
  },
  {
    clave: 'revision',
    encabezado: '',
    render: (f) => (
      <SiTienePermiso permiso="REVISAR_OBSERVACIONES">
        <Link
          to={`/admin/revision?usuario=${f.vendedor_id}`}
          className="text-sm text-primary/70 hover:text-primary hover:underline"
        >
          Ver en Revisión
        </Link>
      </SiTienePermiso>
    ),
  },
]

/**
 * Pestaña «Observaciones por vendedor» de `/admin/reportes` (change 26, tarea 12.2; D9, D11, D12; SYN-07, SYN-06,
 * ADR-069): una fila por vendedor con sus cantidades, sin el detalle de cada aviso. «Ver en Revisión» solo con
 * `REVISAR_OBSERVACIONES` y lleva a la bandeja filtrada por ese vendedor.
 */
export function ObservacionesPorVendedorReporte() {
  const [filtros, setFiltros] = useState<FiltrosDePeriodo>({})
  const reporte = useReporteDeObservaciones(filtros)
  const datos = reporte.data

  return (
    <div className="flex flex-col gap-4">
      <TituloDePestana titulo="Observaciones por vendedor" ayuda="reportes.observacionesPorVendedor" />
      <Card>
        <div className="flex flex-wrap items-start gap-3">
          <FiltroDePeriodo
            periodo={datos?.periodo}
            desde={filtros.desde}
            hasta={filtros.hasta}
            onCambio={(periodo) => setFiltros((actual) => ({ ...actual, ...periodo }))}
          />
        </div>
      </Card>

      <EstadoDelReporte cargando={reporte.isPending} error={reporte.error} />
      {datos !== undefined &&
        !reporte.isError &&
        (datos.vendedores.length === 0 ? (
          <p className="text-sm text-primary/70">Sin operaciones sin conexión en el período.</p>
        ) : (
          <div className="overflow-x-auto">
            <Tabla
              etiqueta="Observaciones por vendedor"
              filas={datos.vendedores}
              columnas={COLUMNAS}
              obtenerClave={(f) => f.vendedor_id}
            />
          </div>
        ))}
    </div>
  )
}

export default ObservacionesPorVendedorReporte
