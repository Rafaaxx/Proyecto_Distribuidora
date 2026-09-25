import { useState } from 'react'
import { Link } from 'react-router-dom'

import { Badge } from '../../../components/ui/Badge'
import { Card } from '../../../components/ui/Card'
import { Boton } from '../../../components/ui/Button'
import { PageHeader } from '../../../components/ui/PageHeader'
import { Tabla } from '../../../components/ui/Table'
import type { Proveedor } from '../../../features/proveedores/api'
import { PermisoRequeridoProveedoresError } from '../../../features/proveedores/errores'
import { useProveedores } from '../../../features/proveedores/useListados'

/**
 * Listado de proveedores de `/admin/proveedores` (tarea 11.3). Búsqueda
 * por nombre/CUIT, filtro por actividad y "cargar más" (cursor,
 * `useInfiniteQuery`); ante `PERMISO_REQUERIDO` (403 de
 * `GET /proveedores`, `GESTIONAR_PROVEEDORES`) la pantalla solo refleja la
 * respuesta real del servidor, mismo criterio que `ProductosListScreen`.
 */
export function ProveedoresListScreen() {
  const [texto, setTexto] = useState('')
  const [soloActivos, setSoloActivos] = useState(true)

  const proveedores = useProveedores({
    texto: texto.trim() || undefined,
    activo: soloActivos ? true : undefined,
  })

  const filas = proveedores.data?.pages.flatMap((pagina) => pagina.items) ?? []

  return (
    <main className="flex flex-col gap-4">
      <PageHeader titulo="Proveedores" />

      <form
        className="flex flex-wrap items-end gap-3 rounded-md border border-border bg-surface p-3"
        onSubmit={(evento) => evento.preventDefault()}
        role="search"
      >
        <div className="flex flex-col gap-1">
          <label htmlFor="filtro-texto-proveedores" className="text-sm text-primary">
            Buscar
          </label>
          <input
            id="filtro-texto-proveedores"
            type="search"
            value={texto}
            onChange={(evento) => setTexto(evento.target.value)}
            placeholder="Nombre o CUIT"
            className="rounded-md border border-border px-2 py-1 text-sm"
          />
        </div>

        <label className="flex items-center gap-2 text-sm text-primary">
          <input
            type="checkbox"
            checked={soloActivos}
            onChange={(evento) => setSoloActivos(evento.target.checked)}
          />
          Solo activos
        </label>

        <Link
          to="/admin/proveedores/nuevo"
          className="rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground hover:opacity-90"
        >
          Nuevo proveedor
        </Link>
      </form>

      {proveedores.isPending && <p className="text-sm text-primary/70">Cargando…</p>}

      {proveedores.isError &&
        (proveedores.error instanceof PermisoRequeridoProveedoresError ? (
          <p className="text-sm text-primary/70">No tenés permiso para gestionar proveedores.</p>
        ) : (
          <p role="alert" className="rounded-md border border-danger/30 bg-danger/10 px-3 py-2 text-sm text-danger">
            No se pudieron obtener los proveedores.
          </p>
        ))}

      {proveedores.isSuccess && (
        <Card className="overflow-x-auto p-0">
          <Tabla<Proveedor>
            filas={filas}
            obtenerClave={(proveedor) => proveedor.id}
            columnas={[
              {
                clave: 'nombre',
                encabezado: 'Nombre',
                render: (p) => (
                  <Link to={`/admin/proveedores/${p.id}`} className="block hover:underline">
                    {p.nombre}
                  </Link>
                ),
              },
              {
                clave: 'cuit',
                encabezado: 'CUIT',
                render: (p) => p.cuit ?? '—',
              },
              {
                clave: 'activo',
                encabezado: 'Estado',
                render: (p) => (
                  <Badge variante={p.activo ? 'positivo' : 'neutral'}>{p.activo ? 'Activo' : 'Inactivo'}</Badge>
                ),
              },
              {
                clave: 'editar',
                encabezado: '',
                render: (p) => (
                  <Link
                    to={`/admin/proveedores/${p.id}`}
                    className="text-sm text-primary/70 hover:text-primary hover:underline"
                  >
                    Editar
                  </Link>
                ),
              },
            ]}
          />

          {filas.length === 0 && (
            <p className="px-3 py-3 text-sm text-primary/70">No hay proveedores que coincidan con la búsqueda.</p>
          )}

          {proveedores.hasNextPage && (
            <div className="p-3">
              <Boton
                variante="secundario"
                onClick={() => void proveedores.fetchNextPage()}
                disabled={proveedores.isFetchingNextPage}
              >
                Cargar más
              </Boton>
            </div>
          )}
        </Card>
      )}
    </main>
  )
}

export default ProveedoresListScreen
