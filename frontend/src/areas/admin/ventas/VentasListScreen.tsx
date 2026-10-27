import { useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'

import { Alert } from '../../../components/ui/Alert'
import { Badge } from '../../../components/ui/Badge'
import { Boton } from '../../../components/ui/Button'
import { Card } from '../../../components/ui/Card'
import { PageHeader } from '../../../components/ui/PageHeader'
import { Tabla, type ColumnaTabla } from '../../../components/ui/Table'
import { etiquetaDeEstadoDeVenta, etiquetaDeModoDeConfirmacion } from '../../../domain/ventas/presentacion'
import { useOpcionesDeClientes } from '../../../features/cobranzas/hooks'
import { SiTienePermiso } from '../../../features/identidad/SiTienePermiso'
import { useUbicaciones } from '../../../features/stock/hooks'
import type { VentaResumen } from '../../../features/ventas/api'
import type { FiltrosVentas } from '../../../features/ventas/claves'
import { PermisoRequeridoVentasError } from '../../../features/ventas/errores'
import { useVentas } from '../../../features/ventas/hooks'
import { formatearFechaHora } from '../../../lib/fecha'
import { formatearImporte, parsearImporteDesdeApi } from '../../../lib/money'
import { VentasSinPermiso } from './VentasSinPermiso'

const CLASE_CONTROL = 'rounded-md border border-border px-2 py-1 text-sm'
const TITULO = 'Ventas'

function opcionDeEstado(valor: string): FiltrosVentas['estado'] {
  return valor === 'CONFIRMADA' || valor === 'ANULADA' ? valor : undefined
}

/**
 * Listado de ventas de `/admin/ventas` (change 18a, tarea 12.3; spec `administracion-de-ventas`).
 * Lo ve quien tiene `VENDER` o `ANULAR_VENTA` (D19); "Nueva venta" solo con `VENDER`. Los filtros
 * de usuario y de jornada no tienen selector (no hay una lectura de usuarios ni de jornadas abierta
 * a quien vende): llegan por la URL (`?jornada=` y `?usuario=`), por ejemplo desde el detalle.
 */
export function VentasListScreen() {
  return (
    <SiTienePermiso permiso={['VENDER', 'ANULAR_VENTA']} fallback={<VentasSinPermiso titulo={TITULO} />}>
      <VentasListado />
    </SiTienePermiso>
  )
}

function VentasListado() {
  const [parametros, setParametros] = useSearchParams()
  const [filtrosLocales, setFiltrosLocales] = useState<FiltrosVentas>({})
  const jornadaId = parametros.get('jornada') ?? undefined
  const usuarioId = parametros.get('usuario') ?? undefined
  const filtros: FiltrosVentas = { ...filtrosLocales, jornadaId, usuarioId }
  const ventas = useVentas(filtros)
  const clientes = useOpcionesDeClientes()
  const ubicaciones = useUbicaciones()
  const filas = ventas.data?.pages.flatMap((pagina) => pagina.items) ?? []

  const cambiar = (cambio: Partial<FiltrosVentas>) => setFiltrosLocales((actual) => ({ ...actual, ...cambio }))
  const quitarDeLaUrl = (clave: string) => {
    const nuevos = new URLSearchParams(parametros)
    nuevos.delete(clave)
    setParametros(nuevos)
  }

  if (ventas.isError) {
    if (ventas.error instanceof PermisoRequeridoVentasError) return <VentasSinPermiso titulo={TITULO} />
    return (
      <main className="flex flex-col gap-4">
        <PageHeader titulo={TITULO} />
        <Alert>No se pudieron obtener las ventas.</Alert>
      </main>
    )
  }

  const columnas: ColumnaTabla<VentaResumen>[] = [
    { clave: 'numero', encabezado: 'Número', render: (v) => v.numero },
    { clave: 'fecha', encabezado: 'Fecha', render: (v) => formatearFechaHora(v.occurred_at) },
    { clave: 'cliente', encabezado: 'Cliente', render: (v) => v.cliente_nombre ?? v.cliente_id },
    { clave: 'total', encabezado: 'Total', render: (v) => `$ ${formatearImporte(parsearImporteDesdeApi(v.total))}` },
    { clave: 'modo', encabezado: 'Confirmación', render: (v) => etiquetaDeModoDeConfirmacion(v.modo_confirmacion) },
    {
      clave: 'estado',
      encabezado: 'Estado',
      render: (v) => <Badge variante={v.estado === 'ANULADA' ? 'negativo' : 'positivo'}>{etiquetaDeEstadoDeVenta(v.estado)}</Badge>,
    },
    {
      clave: 'acciones',
      encabezado: 'Acciones',
      render: (v) => (
        <Link to={`/admin/ventas/${v.venta_id}`} className="text-sm text-primary/70 hover:text-primary hover:underline">
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
          <SiTienePermiso permiso="VENDER">
            <Link
              to="/admin/ventas/nueva"
              className="rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground hover:opacity-90"
            >
              Nueva venta
            </Link>
          </SiTienePermiso>
        }
      />

      <Card className="flex flex-col gap-3">
        <form onSubmit={(evento) => evento.preventDefault()} role="search" className="flex flex-wrap items-end gap-3">
          <div className="flex flex-col gap-1">
            <label htmlFor="filtro-cliente" className="text-sm text-primary">
              Cliente
            </label>
            <select
              id="filtro-cliente"
              className={CLASE_CONTROL}
              value={filtros.clienteId ?? ''}
              onChange={(e) => cambiar({ clienteId: e.target.value || undefined })}
            >
              <option value="">Todos</option>
              {(clientes.data?.pages.flatMap((pagina) => pagina.items) ?? []).map((c) => (
                <option key={c.id} value={c.id}>
                  {c.nombre}
                </option>
              ))}
            </select>
          </div>
          <div className="flex flex-col gap-1">
            <label htmlFor="filtro-ubicacion" className="text-sm text-primary">
              Ubicación
            </label>
            <select
              id="filtro-ubicacion"
              className={CLASE_CONTROL}
              value={filtros.ubicacionId ?? ''}
              onChange={(e) => cambiar({ ubicacionId: e.target.value || undefined })}
            >
              <option value="">Todas</option>
              {(ubicaciones.data?.pages.flatMap((pagina) => pagina.items) ?? []).map((u) => (
                <option key={u.id} value={u.id}>
                  {u.nombre}
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
              onChange={(e) => cambiar({ estado: opcionDeEstado(e.target.value) })}
            >
              <option value="">Todas</option>
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
        {(jornadaId || usuarioId) && (
          <div className="flex flex-wrap gap-3 text-sm text-primary">
            {jornadaId && (
              <span className="flex items-center gap-2">
                Filtrando por una jornada
                <Boton variante="secundario" onClick={() => quitarDeLaUrl('jornada')}>
                  Quitar filtro de jornada
                </Boton>
              </span>
            )}
            {usuarioId && (
              <span className="flex items-center gap-2">
                Filtrando por un usuario
                <Boton variante="secundario" onClick={() => quitarDeLaUrl('usuario')}>
                  Quitar filtro de usuario
                </Boton>
              </span>
            )}
          </div>
        )}
      </Card>

      {ventas.isPending && <p>Cargando…</p>}
      {ventas.isSuccess && filas.length === 0 && <p className="text-sm text-primary/70">Todavía no hay ventas.</p>}
      {filas.length > 0 && (
        <Card>
          <Tabla filas={filas} columnas={columnas} obtenerClave={(v) => v.venta_id} />
        </Card>
      )}
      {ventas.hasNextPage && (
        <div>
          <Boton variante="secundario" disabled={ventas.isFetchingNextPage} onClick={() => void ventas.fetchNextPage()}>
            Cargar más
          </Boton>
        </div>
      )}
    </main>
  )
}

export default VentasListScreen
