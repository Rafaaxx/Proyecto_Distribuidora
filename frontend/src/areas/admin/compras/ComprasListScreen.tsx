import { useState } from 'react'
import { Link } from 'react-router-dom'

import { Alert } from '../../../components/ui/Alert'
import { Badge } from '../../../components/ui/Badge'
import { Boton } from '../../../components/ui/Button'
import { Card } from '../../../components/ui/Card'
import { PageHeader } from '../../../components/ui/PageHeader'
import { Tabla, type ColumnaTabla } from '../../../components/ui/Table'
import type { CompraResumen } from '../../../features/compras/api'
import { PermisoRequeridoComprasError } from '../../../features/compras/errores'
import type { FiltrosCompras } from '../../../features/compras/claves'
import { useCompras } from '../../../features/compras/hooks'
import { SiTienePermiso } from '../../../features/identidad/SiTienePermiso'
import { useOpcionesDeProveedores } from '../../../features/proveedores/useListados'
import { formatearFechaDeNegocio } from '../../../lib/fecha'
import { formatearImporte, parsearImporteDesdeApi } from '../../../lib/money'
import { ETIQUETA_DE_CONDICION, ETIQUETA_DE_ESTADO } from './etiquetas'

const SIN_PERMISO = 'No tenés permiso para ver las compras.'
const CLASE_CONTROL = 'rounded-md border border-border px-2 py-1 text-sm'


function ComprasSinPermiso() {
  return (
    <main className="flex flex-col gap-4">
      <PageHeader titulo="Compras" />
      <p className="text-sm text-primary/70">{SIN_PERMISO}</p>
    </main>
  )
}

/**
 * Listado de compras de `/admin/compras` (change 11, tarea 12.3; spec
 * `administracion-de-compras`). Lo ve quien tiene `REGISTRAR_COMPRA` o `ANULAR_COMPRA`
 * (D14); "Nueva compra" solo con `REGISTRAR_COMPRA`.
 */
export function ComprasListScreen() {
  return (
    <SiTienePermiso permiso={['REGISTRAR_COMPRA', 'ANULAR_COMPRA']} fallback={<ComprasSinPermiso />}>
      <ComprasListado />
    </SiTienePermiso>
  )
}

function ComprasListado() {
  const [filtros, setFiltros] = useState<FiltrosCompras>({})
  const compras = useCompras(filtros)
  const proveedores = useOpcionesDeProveedores()
  const filas = compras.data?.pages.flatMap((pagina) => pagina.items) ?? []

  const cambiar = (cambio: Partial<FiltrosCompras>) => setFiltros((actual) => ({ ...actual, ...cambio }))

  if (compras.isError) {
    if (compras.error instanceof PermisoRequeridoComprasError) return <ComprasSinPermiso />
    return (
      <main className="flex flex-col gap-4">
        <PageHeader titulo="Compras" />
        <Alert>No se pudieron obtener las compras.</Alert>
      </main>
    )
  }

  const columnas: ColumnaTabla<CompraResumen>[] = [
    { clave: 'fecha', encabezado: 'Fecha', render: (c) => formatearFechaDeNegocio(c.fecha) },
    { clave: 'proveedor', encabezado: 'Proveedor', render: (c) => c.proveedor_nombre },
    { clave: 'condicion', encabezado: 'Condición', render: (c) => ETIQUETA_DE_CONDICION[c.condicion] ?? c.condicion },
    { clave: 'total', encabezado: 'Total de factura', render: (c) => formatearImporte(parsearImporteDesdeApi(c.total_factura)) },
    {
      clave: 'estado',
      encabezado: 'Estado',
      render: (c) => (
        <Badge variante={c.estado === 'ANULADA' ? 'negativo' : 'positivo'}>{ETIQUETA_DE_ESTADO[c.estado] ?? c.estado}</Badge>
      ),
    },
    {
      clave: 'acciones',
      encabezado: 'Acciones',
      render: (c) => (
        <Link to={`/admin/compras/${c.id}`} className="text-sm text-primary/70 hover:text-primary hover:underline">
          Ver detalle
        </Link>
      ),
    },
  ]

  return (
    <main className="flex flex-col gap-4">
      <PageHeader
        titulo="Compras"
        acciones={
          <SiTienePermiso permiso="REGISTRAR_COMPRA">
            <Link
              to="/admin/compras/nueva"
              className="rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground hover:opacity-90"
            >
              Nueva compra
            </Link>
          </SiTienePermiso>
        }
      />

      <Card>
        <form onSubmit={(evento) => evento.preventDefault()} role="search" className="flex flex-wrap items-end gap-3">
          <div className="flex flex-col gap-1">
            <label htmlFor="filtro-proveedor" className="text-sm text-primary">
              Proveedor
            </label>
            <select
              id="filtro-proveedor"
              className={CLASE_CONTROL}
              value={filtros.proveedorId ?? ''}
              onChange={(e) => cambiar({ proveedorId: e.target.value || undefined })}
            >
              <option value="">Todos</option>
              {(proveedores.data?.pages.flatMap((pagina) => pagina.items) ?? []).map((p) => (
                <option key={p.id} value={p.id}>
                  {p.nombre}
                </option>
              ))}
            </select>
          </div>
          <div className="flex flex-col gap-1">
            <label htmlFor="filtro-estado" className="text-sm text-primary">
              Estado
            </label>
            <select
              id="filtro-estado"
              className={CLASE_CONTROL}
              value={filtros.estado ?? ''}
              onChange={(e) => cambiar({ estado: (e.target.value || undefined) as FiltrosCompras['estado'] })}
            >
              <option value="">Todos</option>
              <option value="CONFIRMADA">Confirmadas</option>
              <option value="ANULADA">Anuladas</option>
            </select>
          </div>
          <div className="flex flex-col gap-1">
            <label htmlFor="filtro-desde" className="text-sm text-primary">
              Desde
            </label>
            <input
              id="filtro-desde"
              type="date"
              className={CLASE_CONTROL}
              value={filtros.desde ?? ''}
              onChange={(e) => cambiar({ desde: e.target.value || undefined })}
            />
          </div>
          <div className="flex flex-col gap-1">
            <label htmlFor="filtro-hasta" className="text-sm text-primary">
              Hasta
            </label>
            <input
              id="filtro-hasta"
              type="date"
              className={CLASE_CONTROL}
              value={filtros.hasta ?? ''}
              onChange={(e) => cambiar({ hasta: e.target.value || undefined })}
            />
          </div>
        </form>
      </Card>

      {compras.isPending && <p>Cargando…</p>}
      {compras.isSuccess && filas.length === 0 && <p className="text-sm text-primary/70">Todavía no hay compras.</p>}
      {filas.length > 0 && (
        <Card>
          <Tabla filas={filas} columnas={columnas} obtenerClave={(c) => c.id} />
        </Card>
      )}
      {compras.hasNextPage && (
        <div>
          <Boton variante="secundario" disabled={compras.isFetchingNextPage} onClick={() => void compras.fetchNextPage()}>
            Cargar más
          </Boton>
        </div>
      )}
    </main>
  )
}

export default ComprasListScreen
