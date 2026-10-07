import { Link } from 'react-router-dom'

import { Alert } from '../../../components/ui/Alert'
import { Badge } from '../../../components/ui/Badge'
import { Card } from '../../../components/ui/Card'
import { Tabla, type ColumnaTabla } from '../../../components/ui/Table'
import { etiquetaDeEstadoDeVersion } from '../../../domain/precios/presentacion'
import type { Version } from '../../../features/precios/api'
import { useVersiones } from '../../../features/precios/hooks'
import { formatearFechaHora } from '../../../lib/fecha'

function variante(version: Version) {
  const clave = version.estado_derivado ?? version.estado
  if (clave === 'VIGENTE') return 'positivo' as const
  if (clave === 'ANULADA') return 'negativo' as const
  return 'neutral' as const
}

const SIN_FECHA = '—'

/**
 * Versiones de una lista, de la más nueva a la más antigua, con su estado derivado (change 13,
 * tarea 13.3; PRC-03). El borrador lleva a su pantalla de edición; las demás, a la vista de solo
 * lectura.
 */
export function VersionesDeLista({ listaId }: { listaId: string }) {
  const versiones = useVersiones(listaId)

  const columnas: ColumnaTabla<Version>[] = [
    { clave: 'numero', encabezado: 'Versión', render: (v) => `N.º ${v.numero}` },
    {
      clave: 'estado',
      encabezado: 'Estado',
      render: (v) => <Badge variante={variante(v)}>{etiquetaDeEstadoDeVersion(v.estado, v.estado_derivado)}</Badge>,
    },
    {
      clave: 'desde',
      encabezado: 'Vigencia desde',
      render: (v) => (v.vigencia_desde ? formatearFechaHora(v.vigencia_desde) : SIN_FECHA),
    },
    {
      clave: 'hasta',
      encabezado: 'Vigencia hasta',
      render: (v) => (v.vigencia_hasta ? formatearFechaHora(v.vigencia_hasta) : SIN_FECHA),
    },
    { clave: 'publicada', encabezado: 'Publicada por', render: (v) => v.publicado_por_nombre ?? SIN_FECHA },
    {
      clave: 'acciones',
      encabezado: 'Acciones',
      render: (v) => (
        <Link
          to={
            v.estado === 'BORRADOR'
              ? `/admin/precios/${listaId}/borrador`
              : `/admin/precios/${listaId}/versiones/${v.id}`
          }
          className="text-sm text-primary/70 hover:text-primary hover:underline"
        >
          {v.estado === 'BORRADOR' ? 'Abrir' : 'Ver'}
        </Link>
      ),
    },
  ]

  const filas = versiones.data?.items ?? []

  return (
    <section className="flex flex-col gap-3" aria-labelledby="titulo-versiones">
      <h2 id="titulo-versiones" className="text-base font-semibold text-primary">
        Versiones
      </h2>
      {versiones.isPending && <p className="text-sm">Cargando…</p>}
      {versiones.isError && <Alert>No se pudieron obtener las versiones.</Alert>}
      {versiones.isSuccess && filas.length === 0 && (
        <p className="text-sm text-primary/70">Todavía no hay versiones: generá el primer borrador.</p>
      )}
      {filas.length > 0 && (
        <Card>
          <Tabla filas={filas} columnas={columnas} obtenerClave={(v) => v.id} etiqueta="Versiones" />
        </Card>
      )}
    </section>
  )
}
