import { useState } from 'react'
import { Link } from 'react-router-dom'

import { Alert } from '../../../components/ui/Alert'
import { Badge } from '../../../components/ui/Badge'
import { Boton } from '../../../components/ui/Button'
import { Card } from '../../../components/ui/Card'
import { PageHeader } from '../../../components/ui/PageHeader'
import { Tabla, type ColumnaTabla } from '../../../components/ui/Table'
import { ETIQUETA_DE_ESTADO_DE_PAGO, etiquetaDeOrigen } from '../../../domain/pagos-proveedores/presentacion'
import { SiTienePermiso } from '../../../features/identidad/SiTienePermiso'
import type { PagoResumen } from '../../../features/pagos-proveedores/api'
import type { FiltrosPagos } from '../../../features/pagos-proveedores/claves'
import { PermisoRequeridoPagosError } from '../../../features/pagos-proveedores/errores'
import { usePagos } from '../../../features/pagos-proveedores/hooks'
import { useOpcionesDeProveedores } from '../../../features/proveedores/useListados'
import { formatearFechaDeNegocio } from '../../../lib/fecha'
import { formatearImporte, parsearImporteDesdeApi } from '../../../lib/money'
import { PagosSinPermiso } from './PagosSinPermiso'

const CLASE_CONTROL = 'rounded-md border border-border px-2 py-1 text-sm'

/**
 * Listado de pagos a proveedores de `/admin/pagos-proveedores` (change 12, tarea 9.2; spec
 * `administracion-de-pagos`). Lo ve quien tiene `REGISTRAR_PAGO_PROVEEDOR` o
 * `ANULAR_PAGO_PROVEEDOR` (D7); "Nuevo pago" solo con `REGISTRAR_PAGO_PROVEEDOR`.
 */
export function PagosListScreen() {
  return (
    <SiTienePermiso permiso={['REGISTRAR_PAGO_PROVEEDOR', 'ANULAR_PAGO_PROVEEDOR']} fallback={<PagosSinPermiso titulo="Pagos a proveedores" />}>
      <PagosListado />
    </SiTienePermiso>
  )
}

function PagosListado() {
  const [filtros, setFiltros] = useState<FiltrosPagos>({})
  const pagos = usePagos(filtros)
  const proveedores = useOpcionesDeProveedores()
  const filas = pagos.data?.pages.flatMap((pagina) => pagina.items) ?? []

  const cambiar = (cambio: Partial<FiltrosPagos>) => setFiltros((actual) => ({ ...actual, ...cambio }))

  if (pagos.isError) {
    if (pagos.error instanceof PermisoRequeridoPagosError) return <PagosSinPermiso titulo="Pagos a proveedores" />
    return (
      <main className="flex flex-col gap-4">
        <PageHeader titulo="Pagos a proveedores" />
        <Alert>No se pudieron obtener los pagos.</Alert>
      </main>
    )
  }

  const columnas: ColumnaTabla<PagoResumen>[] = [
    { clave: 'fecha', encabezado: 'Fecha', render: (p) => formatearFechaDeNegocio(p.fecha) },
    { clave: 'proveedor', encabezado: 'Proveedor', render: (p) => p.proveedor_nombre },
    { clave: 'importe', encabezado: 'Importe', render: (p) => formatearImporte(parsearImporteDesdeApi(p.importe)) },
    { clave: 'origen', encabezado: 'Origen', render: (p) => etiquetaDeOrigen(p.origen) },
    {
      clave: 'estado',
      encabezado: 'Estado',
      render: (p) => (
        <Badge variante={p.estado === 'ANULADA' ? 'negativo' : 'positivo'}>{ETIQUETA_DE_ESTADO_DE_PAGO[p.estado] ?? p.estado}</Badge>
      ),
    },
    {
      clave: 'acciones',
      encabezado: 'Acciones',
      render: (p) => (
        <Link to={`/admin/pagos-proveedores/${p.pago_id}`} className="text-sm text-primary/70 hover:text-primary hover:underline">
          Ver detalle
        </Link>
      ),
    },
  ]

  return (
    <main className="flex flex-col gap-4">
      <PageHeader
        titulo="Pagos a proveedores"
        acciones={
          <SiTienePermiso permiso="REGISTRAR_PAGO_PROVEEDOR">
            <Link
              to="/admin/pagos-proveedores/nuevo"
              className="rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground hover:opacity-90"
            >
              Nuevo pago
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
              onChange={(e) => cambiar({ estado: (e.target.value || undefined) as FiltrosPagos['estado'] })}
            >
              <option value="">Todos</option>
              <option value="CONFIRMADA">Confirmados</option>
              <option value="ANULADA">Anulados</option>
            </select>
          </div>
          <div className="flex flex-col gap-1">
            <label htmlFor="filtro-origen" className="text-sm text-primary">
              Origen
            </label>
            <select
              id="filtro-origen"
              className={CLASE_CONTROL}
              value={filtros.origen ?? ''}
              onChange={(e) => cambiar({ origen: (e.target.value || undefined) as FiltrosPagos['origen'] })}
            >
              <option value="">Todos</option>
              <option value="INDEPENDIENTE">{etiquetaDeOrigen('INDEPENDIENTE')}</option>
              <option value="COMPRA">{etiquetaDeOrigen('COMPRA')}</option>
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

      {pagos.isPending && <p>Cargando…</p>}
      {pagos.isSuccess && filas.length === 0 && <p className="text-sm text-primary/70">Todavía no hay pagos.</p>}
      {filas.length > 0 && (
        <Card>
          <Tabla filas={filas} columnas={columnas} obtenerClave={(p) => p.pago_id} />
        </Card>
      )}
      {pagos.hasNextPage && (
        <div>
          <Boton variante="secundario" disabled={pagos.isFetchingNextPage} onClick={() => void pagos.fetchNextPage()}>
            Cargar más
          </Boton>
        </div>
      )}
    </main>
  )
}

export default PagosListScreen
