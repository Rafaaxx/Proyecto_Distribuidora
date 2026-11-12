import { useState } from 'react'
import { Link } from 'react-router-dom'

import { Alert } from '../../../components/ui/Alert'
import { Boton } from '../../../components/ui/Button'
import { Card } from '../../../components/ui/Card'
import { PageHeader } from '../../../components/ui/PageHeader'
import { Tabla, type ColumnaTabla } from '../../../components/ui/Table'
import { SiTienePermiso } from '../../../features/identidad/SiTienePermiso'
import type { TransferenciaDelListado } from '../../../features/stock/api'
import type { FiltrosTransferencias } from '../../../features/stock/claves'
import { useTransferencias, useUbicaciones } from '../../../features/stock/hooks'
import { formatearFechaHora } from '../../../lib/fecha'
import { CLASE_CONTROL, CLASE_ENLACE, InsigniaDeEstado, PantallaSinPermiso } from './piezasDeOperacion'

const TITULO = 'Transferencias'

/**
 * Listado de transferencias (change 14, tarea 13.1; `design.md` D7, D11): filtros de ubicación y
 * fechas, estado de cada una y acceso al detalle y al alta. Lo ve quien tiene `TRANSFERIR_STOCK`.
 */
export function TransferenciasListScreen() {
  return (
    <SiTienePermiso
      permiso="TRANSFERIR_STOCK"
      fallback={<PantallaSinPermiso titulo={TITULO} mensaje="No tenés permiso para ver las transferencias." />}
    >
      <Listado />
    </SiTienePermiso>
  )
}

function Listado() {
  const [filtros, setFiltros] = useState<FiltrosTransferencias>({})
  const ubicaciones = useUbicaciones(undefined)
  const transferencias = useTransferencias(filtros)
  const opciones = ubicaciones.data?.pages.flatMap((pagina) => pagina.items) ?? []
  const filas = transferencias.data?.pages.flatMap((pagina) => pagina.items) ?? []

  const cambiar = (cambios: Partial<FiltrosTransferencias>) => {
    const siguiente = { ...filtros, ...cambios }
    setFiltros({
      ...(siguiente.ubicacionId ? { ubicacionId: siguiente.ubicacionId } : {}),
      ...(siguiente.desde ? { desde: siguiente.desde } : {}),
      ...(siguiente.hasta ? { hasta: siguiente.hasta } : {}),
    })
  }

  const columnas: ColumnaTabla<TransferenciaDelListado>[] = [
    { clave: 'fecha', encabezado: 'Fecha', render: (t) => formatearFechaHora(t.occurred_at) },
    { clave: 'origen', encabezado: 'Origen', render: (t) => t.ubicacion_origen_nombre },
    { clave: 'destino', encabezado: 'Destino', render: (t) => t.ubicacion_destino_nombre },
    { clave: 'usuario', encabezado: 'Usuario', render: (t) => t.usuario_nombre ?? '' },
    { clave: 'lineas', encabezado: 'Líneas', render: (t) => String(t.cantidad_de_lineas) },
    { clave: 'estado', encabezado: 'Estado', render: (t) => <InsigniaDeEstado estado={t.estado} /> },
    {
      clave: 'acciones',
      encabezado: 'Acciones',
      render: (t) => (
        <Link to={`/admin/stock/transferencias/${t.id}`} className={CLASE_ENLACE}>
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
              to="/admin/stock/transferencias/nueva"
              className="rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground hover:opacity-90"
            >
              Nueva transferencia
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
              {opciones.map((ubicacion) => (
                <option key={ubicacion.id} value={ubicacion.id}>
                  {ubicacion.nombre}
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

      {transferencias.isPending && <p>Cargando…</p>}
      {transferencias.isError && <Alert>No se pudieron obtener las transferencias.</Alert>}
      {transferencias.isSuccess && filas.length === 0 && (
        <p className="text-sm text-primary/70">No hay transferencias para mostrar.</p>
      )}
      {filas.length > 0 && (
        <Card>
          <Tabla filas={filas} columnas={columnas} obtenerClave={(t) => t.id} />
        </Card>
      )}
      {transferencias.hasNextPage && (
        <div>
          <Boton
            type="button"
            variante="secundario"
            disabled={transferencias.isFetchingNextPage}
            onClick={() => void transferencias.fetchNextPage()}
          >
            Cargar más
          </Boton>
        </div>
      )}
    </main>
  )
}

export default TransferenciasListScreen
