import { useState } from 'react'
import { Link } from 'react-router-dom'

import { Alert } from '../../../components/ui/Alert'
import { Badge } from '../../../components/ui/Badge'
import { Boton } from '../../../components/ui/Button'
import { Card } from '../../../components/ui/Card'
import { PageHeader } from '../../../components/ui/PageHeader'
import { Tabla, type ColumnaTabla } from '../../../components/ui/Table'
import { etiquetaDeTipoDeUbicacion } from '../../../domain/stock/ubicacionSchema'
import { SiTienePermiso } from '../../../features/identidad/SiTienePermiso'
import type { Ubicacion } from '../../../features/stock/api'
import { PermisoRequeridoStockError } from '../../../features/stock/errores'
import { useUbicaciones } from '../../../features/stock/hooks'

const SIN_PERMISO = 'No tenés permiso para ver el stock.'
const CLASE_ENLACE = 'text-sm text-primary/70 hover:text-primary hover:underline'

function StockSinPermiso() {
  return (
    <main className="flex flex-col gap-4">
      <PageHeader titulo="Stock" />
      <p className="text-sm text-primary/70">{SIN_PERMISO}</p>
    </main>
  )
}

/**
 * Listado de ubicaciones de `/admin/stock` (change 09, tarea 8.2; `design.md` D2,
 * D3, D15; spec `administracion-de-stock`). Lo ve quien tiene `TRANSFERIR_STOCK`
 * (D3); crear y editar exigen `ADMIN_CONFIGURACION` (D2) y cargar stock inicial
 * `IMPORTAR_DATOS` (D1), decididos con `['yo']` vía `<SiTienePermiso>` (ADR-027):
 * sin el permiso, la acción no se monta.
 */
export function UbicacionesListScreen() {
  return (
    <SiTienePermiso permiso="TRANSFERIR_STOCK" fallback={<StockSinPermiso />}>
      <UbicacionesListado />
    </SiTienePermiso>
  )
}

function UbicacionesListado() {
  const [estado, setEstado] = useState('')
  const activo = estado === '' ? undefined : estado === 'true'
  const ubicaciones = useUbicaciones(activo)
  const filas = ubicaciones.data?.pages.flatMap((pagina) => pagina.items) ?? []

  if (ubicaciones.isError) {
    if (ubicaciones.error instanceof PermisoRequeridoStockError) return <StockSinPermiso />
    return (
      <main className="flex flex-col gap-4">
        <PageHeader titulo="Stock" />
        <Alert>No se pudieron obtener las ubicaciones.</Alert>
      </main>
    )
  }

  const columnas: ColumnaTabla<Ubicacion>[] = [
    { clave: 'nombre', encabezado: 'Nombre', render: (u) => u.nombre },
    { clave: 'tipo', encabezado: 'Tipo', render: (u) => etiquetaDeTipoDeUbicacion(u.tipo) },
    { clave: 'toma', encabezado: 'Requiere toma', render: (u) => (u.requiere_toma ? 'Sí' : 'No') },
    {
      clave: 'estado',
      encabezado: 'Estado',
      render: (u) => <Badge variante={u.activo ? 'positivo' : 'negativo'}>{u.activo ? 'Activa' : 'Inactiva'}</Badge>,
    },
    {
      clave: 'acciones',
      encabezado: 'Acciones',
      render: (u) => (
        <span className="flex items-center gap-3">
          <Link to={`/admin/stock/ubicaciones/${u.id}/stock`} className={CLASE_ENLACE}>
            Ver stock
          </Link>
          <SiTienePermiso permiso="ADMIN_CONFIGURACION">
            <Link to={`/admin/stock/ubicaciones/${u.id}`} className={CLASE_ENLACE}>
              Editar
            </Link>
          </SiTienePermiso>
          <SiTienePermiso permiso="IMPORTAR_DATOS">
            {u.activo && (
              <Link to={`/admin/stock/ubicaciones/${u.id}/stock-inicial`} className={CLASE_ENLACE}>
                Cargar stock inicial
              </Link>
            )}
          </SiTienePermiso>
        </span>
      ),
    },
  ]

  return (
    <main className="flex flex-col gap-4">
      <PageHeader
        titulo="Stock"
        acciones={
          <>
            <SiTienePermiso permiso="TRANSFERIR_STOCK">
              <Link to="/admin/stock/transferencias" className={CLASE_ENLACE}>
                Transferencias
              </Link>
            </SiTienePermiso>
            <SiTienePermiso permiso="AJUSTAR_STOCK">
              <Link to="/admin/stock/ajustes" className={CLASE_ENLACE}>
                Ajustes
              </Link>
            </SiTienePermiso>
            <SiTienePermiso permiso="ADMIN_CONFIGURACION">
              <Link
                to="/admin/stock/ubicaciones/nueva"
                className="rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground hover:opacity-90"
              >
                Nueva ubicación
              </Link>
            </SiTienePermiso>
          </>
        }
      />

      <Card>
        <form onSubmit={(evento) => evento.preventDefault()} role="search" className="flex items-end gap-3">
          <div className="flex flex-col gap-1">
            <label htmlFor="filtro-estado-ubicaciones" className="text-sm text-primary">
              Estado
            </label>
            <select
              id="filtro-estado-ubicaciones"
              value={estado}
              onChange={(evento) => setEstado(evento.target.value)}
              className="rounded-md border border-border px-2 py-1 text-sm"
            >
              <option value="">Todas</option>
              <option value="true">Activas</option>
              <option value="false">Inactivas</option>
            </select>
          </div>
        </form>
      </Card>

      {ubicaciones.isPending && <p>Cargando…</p>}
      {ubicaciones.isSuccess && filas.length === 0 && (
        <p className="text-sm text-primary/70">Todavía no hay ubicaciones.</p>
      )}
      {filas.length > 0 && (
        <Card>
          <Tabla filas={filas} columnas={columnas} obtenerClave={(u) => u.id} />
        </Card>
      )}
      {ubicaciones.hasNextPage && (
        <div>
          <Boton
            type="button"
            variante="secundario"
            disabled={ubicaciones.isFetchingNextPage}
            onClick={() => void ubicaciones.fetchNextPage()}
          >
            Cargar más
          </Boton>
        </div>
      )}
    </main>
  )
}

export default UbicacionesListScreen
