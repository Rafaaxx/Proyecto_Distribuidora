import { Link, useParams } from 'react-router-dom'

import { Alert } from '../../../components/ui/Alert'
import { Badge } from '../../../components/ui/Badge'
import { Card } from '../../../components/ui/Card'
import { PageHeader } from '../../../components/ui/PageHeader'
import { descripcionDeRedondeo } from '../../../domain/precios/presentacion'
import { SiTienePermiso } from '../../../features/identidad/SiTienePermiso'
import { ErrorDePrecios, PermisoRequeridoPreciosError } from '../../../features/precios/errores'
import { useListaDetalle } from '../../../features/precios/hooks'
import { PreciosSinPermiso } from './PreciosSinPermiso'
import { RedondeosDeCategoria } from './RedondeosDeCategoria'
import { ReglasDeLista } from './ReglasDeLista'
import { VersionesDeLista } from './VersionesDeLista'

const TITULO = 'Lista de precios'
const ENLACE = 'text-sm text-primary/70 hover:text-primary hover:underline'

/**
 * Detalle de una lista de `/admin/precios/:listaId` (change 13, tarea 13.1 y 13.3; spec
 * `administracion-de-listas`): datos y redondeo, reglas de margen con su fórmula, redondeos por
 * categoría y versiones. Lo ve quien tiene `GESTIONAR_LISTAS` o `PUBLICAR_LISTAS`; las acciones
 * de edición, solo con `GESTIONAR_LISTAS`.
 */
export function ListaDetalleScreen() {
  const { listaId } = useParams<{ listaId: string }>()
  return (
    <SiTienePermiso permiso={['GESTIONAR_LISTAS', 'PUBLICAR_LISTAS']} fallback={<PreciosSinPermiso titulo={TITULO} />}>
      <ListaDetalle listaId={listaId as string} />
    </SiTienePermiso>
  )
}

function ListaDetalle({ listaId }: { listaId: string }) {
  const lista = useListaDetalle(listaId)

  if (lista.isPending) {
    return (
      <main>
        <p>Cargando…</p>
      </main>
    )
  }
  if (lista.isError) {
    if (lista.error instanceof PermisoRequeridoPreciosError) return <PreciosSinPermiso titulo={TITULO} />
    const noExiste = lista.error instanceof ErrorDePrecios && lista.error.estado === 404
    return (
      <main className="flex flex-col gap-4">
        <PageHeader titulo={TITULO} />
        <Alert>{noExiste ? 'No se encontró la lista.' : 'No se pudo obtener la lista.'}</Alert>
      </main>
    )
  }

  const detalle = lista.data
  return (
    <main className="flex flex-col gap-6">
      <PageHeader
        titulo={detalle.nombre}
        acciones={
          <>
            <Link to={`/admin/precios/${listaId}/borrador`} className={ENLACE}>
              Borrador
            </Link>
            <SiTienePermiso permiso="GESTIONAR_LISTAS">
              <Link to={`/admin/precios/${listaId}/editar`} className={ENLACE}>
                Editar lista
              </Link>
            </SiTienePermiso>
            <Link to="/admin/precios" className={ENLACE}>
              Volver
            </Link>
          </>
        }
      />
      <Card>
        <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
          <dt className="text-primary/70">Redondeo</dt>
          <dd>{descripcionDeRedondeo(detalle.redondeo_multiplo, detalle.redondeo_direccion)}</dd>
          <dt className="text-primary/70">Estado</dt>
          <dd>
            <Badge variante={detalle.activo ? 'positivo' : 'negativo'}>{detalle.activo ? 'Activa' : 'Inactiva'}</Badge>
          </dd>
          <dt className="text-primary/70">Versión vigente</dt>
          <dd>{detalle.version_vigente === null ? 'Sin versión vigente' : `Versión ${detalle.version_vigente}`}</dd>
          <dt className="text-primary/70">Borrador</dt>
          <dd>{detalle.tiene_borrador ? 'Con borrador' : 'Sin borrador'}</dd>
        </dl>
      </Card>
      <ReglasDeLista listaId={listaId} />
      <RedondeosDeCategoria listaId={listaId} redondeos={detalle.redondeos_categoria} />
      <VersionesDeLista listaId={listaId} />
    </main>
  )
}

export default ListaDetalleScreen
