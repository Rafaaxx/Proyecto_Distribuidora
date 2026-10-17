import { useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'

import { Alert } from '../../../components/ui/Alert'
import { Badge } from '../../../components/ui/Badge'
import { Boton } from '../../../components/ui/Button'
import { Card } from '../../../components/ui/Card'
import { PageHeader } from '../../../components/ui/PageHeader'
import { Tabla, type ColumnaTabla } from '../../../components/ui/Table'
import { ETIQUETA_DE_ESTADO_DE_COBRANZA, etiquetaDeOrigenDeCobranza } from '../../../domain/cobranzas/presentacion'
import type { CobranzaResumen } from '../../../features/cobranzas/api'
import type { FiltrosCobranzas } from '../../../features/cobranzas/claves'
import { PermisoRequeridoCobranzasError } from '../../../features/cobranzas/errores'
import { useCobranzas, useOpcionesDeClientes } from '../../../features/cobranzas/hooks'
import { SiTienePermiso } from '../../../features/identidad/SiTienePermiso'
import { formatearFechaHora } from '../../../lib/fecha'
import { formatearImporte, parsearImporteDesdeApi } from '../../../lib/money'
import { CobranzasSinPermiso } from './CobranzasSinPermiso'

const CLASE_CONTROL = 'rounded-md border border-border px-2 py-1 text-sm'
const TITULO = 'Cobranzas'

/**
 * Listado de cobranzas de `/admin/cobranzas` (change 17, tarea 14.1; spec
 * `administracion-de-cobranzas`). Lo ve quien tiene `REGISTRAR_COBRANZA` o `ANULAR_COBRANZA`
 * (D14); "Registrar cobranza" solo con `REGISTRAR_COBRANZA`. Los filtros de usuario y de
 * jornada no tienen selector (no hay una lectura de usuarios ni de jornadas abierta a quien
 * cobra): llegan por la URL (`?jornada=` y `?usuario=`), por ejemplo desde el detalle.
 */
export function CobranzasListScreen() {
  return (
    <SiTienePermiso permiso={['REGISTRAR_COBRANZA', 'ANULAR_COBRANZA']} fallback={<CobranzasSinPermiso titulo={TITULO} />}>
      <CobranzasListado />
    </SiTienePermiso>
  )
}

function CobranzasListado() {
  const [parametros, setParametros] = useSearchParams()
  const [filtrosLocales, setFiltrosLocales] = useState<FiltrosCobranzas>({})
  const jornadaId = parametros.get('jornada') ?? undefined
  const usuarioId = parametros.get('usuario') ?? undefined
  const filtros: FiltrosCobranzas = { ...filtrosLocales, jornadaId, usuarioId }
  const cobranzas = useCobranzas(filtros)
  const clientes = useOpcionesDeClientes()
  const filas = cobranzas.data?.pages.flatMap((pagina) => pagina.items) ?? []

  const cambiar = (cambio: Partial<FiltrosCobranzas>) => setFiltrosLocales((actual) => ({ ...actual, ...cambio }))
  const quitarDeLaUrl = (clave: string) => {
    const nuevos = new URLSearchParams(parametros)
    nuevos.delete(clave)
    setParametros(nuevos)
  }

  if (cobranzas.isError) {
    if (cobranzas.error instanceof PermisoRequeridoCobranzasError) return <CobranzasSinPermiso titulo={TITULO} />
    return (
      <main className="flex flex-col gap-4">
        <PageHeader titulo={TITULO} />
        <Alert>No se pudieron obtener las cobranzas.</Alert>
      </main>
    )
  }

  const columnas: ColumnaTabla<CobranzaResumen>[] = [
    { clave: 'fecha', encabezado: 'Fecha', render: (c) => formatearFechaHora(c.occurred_at) },
    { clave: 'cliente', encabezado: 'Cliente', render: (c) => c.cliente_nombre ?? c.cliente_id },
    { clave: 'importe', encabezado: 'Importe', render: (c) => formatearImporte(parsearImporteDesdeApi(c.importe)) },
    { clave: 'origen', encabezado: 'Origen', render: (c) => etiquetaDeOrigenDeCobranza(c.origen) },
    {
      clave: 'estado',
      encabezado: 'Estado',
      render: (c) => (
        <Badge variante={c.estado === 'ANULADA' ? 'negativo' : 'positivo'}>{ETIQUETA_DE_ESTADO_DE_COBRANZA[c.estado] ?? c.estado}</Badge>
      ),
    },
    {
      clave: 'acciones',
      encabezado: 'Acciones',
      render: (c) => (
        <Link to={`/admin/cobranzas/${c.cobranza_id}`} className="text-sm text-primary/70 hover:text-primary hover:underline">
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
          <SiTienePermiso permiso="REGISTRAR_COBRANZA">
            <Link
              to="/admin/cobranzas/nuevo"
              className="rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground hover:opacity-90"
            >
              Registrar cobranza
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
            <label htmlFor="filtro-estado" className="text-sm text-primary">
              Estado
            </label>
            <select
              id="filtro-estado"
              className={CLASE_CONTROL}
              value={filtros.estado ?? ''}
              onChange={(e) => cambiar({ estado: (e.target.value || undefined) as FiltrosCobranzas['estado'] })}
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

      {cobranzas.isPending && <p>Cargando…</p>}
      {cobranzas.isSuccess && filas.length === 0 && <p className="text-sm text-primary/70">Todavía no hay cobranzas.</p>}
      {filas.length > 0 && (
        <Card>
          <Tabla filas={filas} columnas={columnas} obtenerClave={(c) => c.cobranza_id} />
        </Card>
      )}
      {cobranzas.hasNextPage && (
        <div>
          <Boton variante="secundario" disabled={cobranzas.isFetchingNextPage} onClick={() => void cobranzas.fetchNextPage()}>
            Cargar más
          </Boton>
        </div>
      )}
    </main>
  )
}

export default CobranzasListScreen
