import { Link } from 'react-router-dom'

import { Alert } from '../../../components/ui/Alert'
import { Badge } from '../../../components/ui/Badge'
import { Card } from '../../../components/ui/Card'
import { PageHeader } from '../../../components/ui/PageHeader'
import { Tabla, type ColumnaTabla } from '../../../components/ui/Table'
import { descripcionDeRedondeo } from '../../../domain/precios/presentacion'
import { SiTienePermiso } from '../../../features/identidad/SiTienePermiso'
import type { Lista } from '../../../features/precios/api'
import { PermisoRequeridoPreciosError } from '../../../features/precios/errores'
import { useListas } from '../../../features/precios/hooks'
import { PreciosSinPermiso } from './PreciosSinPermiso'

const TITULO = 'Listas de precios'

/**
 * Listado de `/admin/precios` (change 13, tarea 13.1; spec `administracion-de-listas`). Lo ve
 * quien tiene `GESTIONAR_LISTAS` o `PUBLICAR_LISTAS` (ADR-027); "Nueva lista" solo con
 * `GESTIONAR_LISTAS`. Sin ninguno de los dos, los hijos no se montan y no se pide nada.
 */
export function ListasListScreen() {
  return (
    <SiTienePermiso permiso={['GESTIONAR_LISTAS', 'PUBLICAR_LISTAS']} fallback={<PreciosSinPermiso titulo={TITULO} />}>
      <ListasListado />
    </SiTienePermiso>
  )
}

const COLUMNAS: ColumnaTabla<Lista>[] = [
  {
    clave: 'nombre',
    encabezado: 'Nombre',
    render: (l) => (
      <Link to={`/admin/precios/${l.id}`} className="font-medium text-primary hover:underline">
        {l.nombre}
      </Link>
    ),
  },
  {
    clave: 'redondeo',
    encabezado: 'Redondeo',
    render: (l) => descripcionDeRedondeo(l.redondeo_multiplo, l.redondeo_direccion),
  },
  {
    clave: 'vigente',
    encabezado: 'Versión vigente',
    render: (l) => (l.version_vigente === null ? 'Sin versión vigente' : `Versión ${l.version_vigente}`),
  },
  {
    clave: 'borrador',
    encabezado: 'Borrador',
    render: (l) => (l.tiene_borrador ? 'Con borrador' : 'Sin borrador'),
  },
  {
    clave: 'estado',
    encabezado: 'Estado',
    render: (l) => <Badge variante={l.activo ? 'positivo' : 'negativo'}>{l.activo ? 'Activa' : 'Inactiva'}</Badge>,
  },
]

function ListasListado() {
  const listas = useListas()

  if (listas.isError) {
    if (listas.error instanceof PermisoRequeridoPreciosError) return <PreciosSinPermiso titulo={TITULO} />
    return (
      <main className="flex flex-col gap-4">
        <PageHeader titulo={TITULO} />
        <Alert>No se pudieron obtener las listas de precios.</Alert>
      </main>
    )
  }

  const filas = listas.data?.items ?? []

  return (
    <main className="flex flex-col gap-4">
      <PageHeader
        titulo={TITULO}
        acciones={
          <SiTienePermiso permiso="GESTIONAR_LISTAS">
            <Link
              to="/admin/precios/nueva"
              className="rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground hover:opacity-90"
            >
              Nueva lista
            </Link>
          </SiTienePermiso>
        }
      />
      {listas.isPending && <p>Cargando…</p>}
      {listas.isSuccess && filas.length === 0 && (
        <p className="text-sm text-primary/70">Todavía no hay listas de precios.</p>
      )}
      {filas.length > 0 && (
        <Card>
          <Tabla filas={filas} columnas={COLUMNAS} obtenerClave={(l) => l.id} etiqueta="Listas de precios" />
        </Card>
      )}
    </main>
  )
}

export default ListasListScreen
