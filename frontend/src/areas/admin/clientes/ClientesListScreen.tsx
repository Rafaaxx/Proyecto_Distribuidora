import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { Badge, type VarianteBadge } from '../../../components/ui/Badge'
import { Card } from '../../../components/ui/Card'
import { Boton } from '../../../components/ui/Button'
import { PageHeader } from '../../../components/ui/PageHeader'
import { Tabla } from '../../../components/ui/Table'
import { SiTienePermiso } from '../../../features/identidad/SiTienePermiso'
import type { Cliente } from '../../../features/clientes/api'
import { PermisoRequeridoClientesError } from '../../../features/clientes/errores'
import { useClientes } from '../../../features/clientes/useListados'

const SIN_PERMISO_DE_CLIENTES = 'No tenés permiso para gestionar clientes.'

/** Estado del catálogo cerrado de `clientes/domain/estado.py`: `ACTIVO`,
 * `SUSPENDIDO`, `INACTIVO` (`01` §18). */
const ESTADOS: readonly string[] = ['ACTIVO', 'SUSPENDIDO', 'INACTIVO']

const VARIANTE_POR_ESTADO: Record<string, VarianteBadge> = {
  ACTIVO: 'positivo',
  SUSPENDIDO: 'neutral',
  INACTIVO: 'negativo',
}

const ETIQUETA_POR_ESTADO: Record<string, string> = {
  ACTIVO: 'Activo',
  SUSPENDIDO: 'Suspendido',
  INACTIVO: 'Inactivo',
}

/** Estado sin permiso (y red de seguridad del 403): mismo texto en los dos
 * casos, para que el mensaje no revele por qué el usuario no ve la
 * pantalla (mismo criterio que `ProveedoresListScreen.tsx`). */
function ClientesSinPermiso() {
  return (
    <main className="flex flex-col gap-4">
      <PageHeader titulo="Clientes" />
      <p className="text-sm text-primary/70">{SIN_PERMISO_DE_CLIENTES}</p>
    </main>
  )
}

/**
 * Listado de clientes de `/admin/clientes` (change 07, grupo 5, tarea 5.2).
 * Filtro por texto y por estado, insignia de estado, marca de consumidor
 * final y "cargar más" (cursor, `useInfiniteQuery`).
 *
 * Qué se muestra lo decide **solo** la consulta de sesión `['yo']`, con
 * `<SiTienePermiso>` (`design.md` D3, ADR-027, mismo criterio que
 * `ProveedoresListScreen.tsx`): sin `GESTIONAR_CLIENTES` los hijos no se
 * montan, así que la pantalla no pide clientes para averiguar si el
 * usuario puede verlos.
 */
export function ClientesListScreen() {
  return (
    <SiTienePermiso permiso="GESTIONAR_CLIENTES" fallback={<ClientesSinPermiso />}>
      <ClientesListado />
    </SiTienePermiso>
  )
}

function ClientesListado() {
  const navigate = useNavigate()
  const [texto, setTexto] = useState('')
  const [estado, setEstado] = useState('')

  const clientes = useClientes({
    texto: texto.trim() || undefined,
    estado: estado || undefined,
  })

  const filas = clientes.data?.pages.flatMap((pagina) => pagina.items) ?? []

  if (clientes.isError) {
    if (clientes.error instanceof PermisoRequeridoClientesError) {
      return <ClientesSinPermiso />
    }
    return (
      <main className="flex flex-col gap-4">
        <PageHeader titulo="Clientes" />
        <p role="alert" className="rounded-md border border-danger/30 bg-danger/10 px-3 py-2 text-sm text-danger">
          No se pudieron obtener los clientes.
        </p>
      </main>
    )
  }

  return (
    <main className="flex flex-col gap-4">
      <PageHeader titulo="Clientes" />

      <form
        className="flex flex-wrap items-end gap-3 rounded-md border border-border bg-surface p-3"
        onSubmit={(evento) => evento.preventDefault()}
        role="search"
      >
        <div className="flex flex-col gap-1">
          <label htmlFor="filtro-texto-clientes" className="text-sm text-primary">
            Buscar
          </label>
          <input
            id="filtro-texto-clientes"
            type="search"
            value={texto}
            onChange={(evento) => setTexto(evento.target.value)}
            placeholder="Nombre, código o documento"
            className="rounded-md border border-border px-2 py-1 text-sm"
          />
        </div>

        <div className="flex flex-col gap-1">
          <label htmlFor="filtro-estado-clientes" className="text-sm text-primary">
            Estado
          </label>
          <select
            id="filtro-estado-clientes"
            value={estado}
            onChange={(evento) => setEstado(evento.target.value)}
            className="rounded-md border border-border px-2 py-1 text-sm"
          >
            <option value="">Todos</option>
            {ESTADOS.map((valor) => (
              <option key={valor} value={valor}>
                {ETIQUETA_POR_ESTADO[valor]}
              </option>
            ))}
          </select>
        </div>

        <Link
          to="/admin/clientes/nuevo"
          className="rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground hover:opacity-90"
        >
          Nuevo cliente
        </Link>

        {/* `ADMIN_CONFIGURACION` de `['yo']`, no una consulta al servidor
            para averiguarlo (ADR-027, D4): con las plantillas de rol
            vigentes, solo Administrador ve este enlace. */}
        <SiTienePermiso permiso="ADMIN_CONFIGURACION">
          <Link
            to="/admin/clientes/consumidor-final"
            className="text-sm text-primary/70 hover:text-primary hover:underline"
          >
            Consumidor final
          </Link>
        </SiTienePermiso>
      </form>

      {clientes.isPending && <p className="text-sm text-primary/70">Cargando…</p>}

      {clientes.isSuccess && (
        <Card className="overflow-x-auto p-0">
          <Tabla<Cliente>
            filas={filas}
            obtenerClave={(cliente) => cliente.id}
            onFilaClick={(cliente) => navigate(`/admin/clientes/${cliente.id}`)}
            columnas={[
              {
                clave: 'nombre',
                encabezado: 'Nombre',
                render: (c) => (
                  <div className="flex items-center gap-2">
                    <Link to={`/admin/clientes/${c.id}`} className="hover:underline">
                      {c.nombre}
                    </Link>
                    {c.es_consumidor_final && <Badge variante="neutral">Consumidor final</Badge>}
                  </div>
                ),
              },
              {
                clave: 'documento',
                encabezado: 'Documento',
                render: (c) => (c.documento_numero ? `${c.documento_tipo} ${c.documento_numero}` : '—'),
              },
              {
                clave: 'estado',
                encabezado: 'Estado',
                render: (c) => <Badge variante={VARIANTE_POR_ESTADO[c.estado]}>{ETIQUETA_POR_ESTADO[c.estado]}</Badge>,
              },
              {
                clave: 'editar',
                encabezado: '',
                render: (c) => (
                  <Link
                    to={`/admin/clientes/${c.id}`}
                    className="text-sm text-primary/70 hover:text-primary hover:underline"
                  >
                    Editar
                  </Link>
                ),
              },
            ]}
          />

          {filas.length === 0 && (
            <p className="px-3 py-3 text-sm text-primary/70">No hay clientes que coincidan con la búsqueda.</p>
          )}

          {clientes.hasNextPage && (
            <div className="p-3">
              <Boton
                variante="secundario"
                onClick={() => void clientes.fetchNextPage()}
                disabled={clientes.isFetchingNextPage}
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

export default ClientesListScreen
