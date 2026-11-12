import { useState } from 'react'
import { Link } from 'react-router-dom'

import { Alert } from '../../../components/ui/Alert'
import { Boton } from '../../../components/ui/Button'
import { Card } from '../../../components/ui/Card'
import { PageHeader } from '../../../components/ui/PageHeader'
import { Tabla, type ColumnaTabla } from '../../../components/ui/Table'
import { AMBITO_DE_AJUSTE } from '../../../domain/stock/operaciones'
import { SiTienePermiso } from '../../../features/identidad/SiTienePermiso'
import type { AjusteDelListado } from '../../../features/stock/api'
import type { FiltrosAjustes } from '../../../features/stock/claves'
import { useAjustes, useMotivosDeStock, useUbicaciones } from '../../../features/stock/hooks'
import { formatearFechaHora } from '../../../lib/fecha'
import { CLASE_CONTROL, CLASE_ENLACE, InsigniaDeEstado, PantallaSinPermiso } from './piezasDeOperacion'

const TITULO = 'Ajustes'

/**
 * Listado de ajustes de stock (change 14, tarea 13.2; `design.md` D7, D11): filtros de ubicación,
 * motivo y fechas, estado de cada ajuste y acceso al detalle y al alta. Lo ve quien tiene
 * `AJUSTAR_STOCK`: un Vendedor no ve los ajustes de la organización.
 */
export function AjustesListScreen() {
  return (
    <SiTienePermiso
      permiso="AJUSTAR_STOCK"
      fallback={<PantallaSinPermiso titulo={TITULO} mensaje="No tenés permiso para ver los ajustes." />}
    >
      <Listado />
    </SiTienePermiso>
  )
}

function Listado() {
  const [filtros, setFiltros] = useState<FiltrosAjustes>({})
  const ubicaciones = useUbicaciones(undefined)
  const motivos = useMotivosDeStock(AMBITO_DE_AJUSTE)
  const ajustes = useAjustes(filtros)
  const opcionesDeUbicacion = ubicaciones.data?.pages.flatMap((pagina) => pagina.items) ?? []
  const filas = ajustes.data?.pages.flatMap((pagina) => pagina.items) ?? []

  const cambiar = (cambios: Partial<FiltrosAjustes>) => {
    const siguiente = { ...filtros, ...cambios }
    setFiltros({
      ...(siguiente.ubicacionId ? { ubicacionId: siguiente.ubicacionId } : {}),
      ...(siguiente.motivoId ? { motivoId: siguiente.motivoId } : {}),
      ...(siguiente.desde ? { desde: siguiente.desde } : {}),
      ...(siguiente.hasta ? { hasta: siguiente.hasta } : {}),
    })
  }

  const columnas: ColumnaTabla<AjusteDelListado>[] = [
    { clave: 'fecha', encabezado: 'Fecha', render: (a) => formatearFechaHora(a.occurred_at) },
    { clave: 'ubicacion', encabezado: 'Ubicación', render: (a) => a.ubicacion_nombre },
    { clave: 'motivo', encabezado: 'Motivo', render: (a) => a.motivo_nombre ?? '' },
    { clave: 'usuario', encabezado: 'Usuario', render: (a) => a.usuario_nombre ?? '' },
    { clave: 'lineas', encabezado: 'Líneas', render: (a) => String(a.cantidad_de_lineas) },
    { clave: 'estado', encabezado: 'Estado', render: (a) => <InsigniaDeEstado estado={a.estado} /> },
    {
      clave: 'acciones',
      encabezado: 'Acciones',
      render: (a) => (
        <Link to={`/admin/stock/ajustes/${a.id}`} className={CLASE_ENLACE}>
          Ver detalle
        </Link>
      ),
    },
  ]

  return (
    <main className="flex flex-col gap-4">
      <PageHeader
        titulo={TITULO}
        acciones={
          <>
            <Link
              to="/admin/stock/ajustes/nueva"
              className="rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground hover:opacity-90"
            >
              Nuevo ajuste
            </Link>
            <Link to="/admin/stock" className={CLASE_ENLACE}>
              Volver a las ubicaciones
            </Link>
          </>
        }
      />

      <Card>
        <form onSubmit={(evento) => evento.preventDefault()} role="search" className="flex flex-wrap items-end gap-3">
          <label className="flex flex-col gap-1 text-sm text-primary">
            Ubicación
            <select
              className={CLASE_CONTROL}
              value={filtros.ubicacionId ?? ''}
              onChange={(evento) => cambiar({ ubicacionId: evento.target.value })}
            >
              <option value="">Todas</option>
              {opcionesDeUbicacion.map((ubicacion) => (
                <option key={ubicacion.id} value={ubicacion.id}>
                  {ubicacion.nombre}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1 text-sm text-primary">
            Motivo
            <select
              className={CLASE_CONTROL}
              value={filtros.motivoId ?? ''}
              onChange={(evento) => cambiar({ motivoId: evento.target.value })}
            >
              <option value="">Todos</option>
              {(motivos.data?.items ?? []).map((motivo) => (
                <option key={motivo.id} value={motivo.id}>
                  {motivo.nombre}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1 text-sm text-primary">
            Desde
            <input
              type="date"
              className={CLASE_CONTROL}
              value={filtros.desde ?? ''}
              onChange={(evento) => cambiar({ desde: evento.target.value })}
            />
          </label>
          <label className="flex flex-col gap-1 text-sm text-primary">
            Hasta
            <input
              type="date"
              className={CLASE_CONTROL}
              value={filtros.hasta ?? ''}
              onChange={(evento) => cambiar({ hasta: evento.target.value })}
            />
          </label>
        </form>
      </Card>

      {ajustes.isPending && <p>Cargando…</p>}
      {ajustes.isError && <Alert>No se pudieron obtener los ajustes.</Alert>}
      {ajustes.isSuccess && filas.length === 0 && <p className="text-sm text-primary/70">No hay ajustes para mostrar.</p>}
      {filas.length > 0 && (
        <Card>
          <Tabla filas={filas} columnas={columnas} obtenerClave={(a) => a.id} />
        </Card>
      )}
      {ajustes.hasNextPage && (
        <div>
          <Boton
            type="button"
            variante="secundario"
            disabled={ajustes.isFetchingNextPage}
            onClick={() => void ajustes.fetchNextPage()}
          >
            Cargar más
          </Boton>
        </div>
      )}
    </main>
  )
}

export default AjustesListScreen
