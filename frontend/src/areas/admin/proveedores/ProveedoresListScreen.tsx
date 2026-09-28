import { useState } from 'react'
import { Link } from 'react-router-dom'

import { Badge } from '../../../components/ui/Badge'
import { Card } from '../../../components/ui/Card'
import { Boton } from '../../../components/ui/Button'
import { PageHeader } from '../../../components/ui/PageHeader'
import { Tabla } from '../../../components/ui/Table'
import { SiTienePermiso } from '../../../features/identidad/SiTienePermiso'
import type { Proveedor } from '../../../features/proveedores/api'
import { PermisoRequeridoProveedoresError } from '../../../features/proveedores/errores'
import { useProveedores } from '../../../features/proveedores/useListados'

const SIN_PERMISO_DE_PROVEEDORES = 'No tenés permiso para gestionar proveedores.'

/** Estado sin permiso (y red de seguridad del 403): mismo texto en los dos
 * casos, para que el mensaje no revele por qué el usuario no ve la
 * pantalla. */
function ProveedoresSinPermiso() {
  return (
    <main className="flex flex-col gap-4">
      <PageHeader titulo="Proveedores" />
      <p className="text-sm text-primary/70">{SIN_PERMISO_DE_PROVEEDORES}</p>
    </main>
  )
}

/**
 * Listado de proveedores de `/admin/proveedores` (tarea 11.3). Búsqueda
 * por nombre/CUIT, filtro por actividad y "cargar más" (cursor,
 * `useInfiniteQuery`).
 *
 * Qué se muestra lo decide **solo** la consulta de sesión `['yo']`, con el
 * mecanismo compartido `<SiTienePermiso>` (tarea 8.4 del change 06b,
 * `design.md` D4-A / **B2**): sin `GESTIONAR_PROVEEDORES` los hijos no se
 * montan, así que la pantalla no pide proveedores para averiguar si el
 * usuario puede verlos. El 403 del servidor
 * (`PermisoRequeridoProveedoresError`) se sigue tratando, pero **solo como
 * red de seguridad**: ocurre si el permiso se quitó del rol entre dos
 * renovaciones del access token (SEG-06).
 */
export function ProveedoresListScreen() {
  return (
    <SiTienePermiso permiso="GESTIONAR_PROVEEDORES" fallback={<ProveedoresSinPermiso />}>
      <ProveedoresListado />
    </SiTienePermiso>
  )
}

/** Componente interno: es el único que consulta y filtra. Sin permiso no se
 * monta, así que no dispara ninguna petición (**B2**). */
function ProveedoresListado() {
  const [texto, setTexto] = useState('')
  const [soloActivos, setSoloActivos] = useState(true)

  const proveedores = useProveedores({
    texto: texto.trim() || undefined,
    activo: soloActivos ? true : undefined,
  })

  const filas = proveedores.data?.pages.flatMap((pagina) => pagina.items) ?? []

  if (proveedores.isError) {
    if (proveedores.error instanceof PermisoRequeridoProveedoresError) {
      return <ProveedoresSinPermiso />
    }
    return (
      <main className="flex flex-col gap-4">
        <PageHeader titulo="Proveedores" />
        <p role="alert" className="rounded-md border border-danger/30 bg-danger/10 px-3 py-2 text-sm text-danger">
          No se pudieron obtener los proveedores.
        </p>
      </main>
    )
  }

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
