import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'

import { Alert } from '../../../components/ui/Alert'
import { Badge } from '../../../components/ui/Badge'
import { Boton } from '../../../components/ui/Button'
import { Card } from '../../../components/ui/Card'
import { Dialogo } from '../../../components/ui/Dialog'
import { PageHeader } from '../../../components/ui/PageHeader'
import { Tabla, type ColumnaTabla } from '../../../components/ui/Table'
import { etiquetaDeEstadoDeVersion, etiquetaDeTipoDeMargen, puedeAnularse } from '../../../domain/precios/presentacion'
import { porcentajeDesdeFraccion } from '../../../domain/precios/reglaSchema'
import { SiTienePermiso } from '../../../features/identidad/SiTienePermiso'
import { usePermisos } from '../../../features/identidad/usePermisos'
import type { PrecioDeVersion, Version } from '../../../features/precios/api'
import { ErrorDePrecios, PermisoRequeridoPreciosError } from '../../../features/precios/errores'
import { useAnularVersion, usePreciosDeVersion } from '../../../features/precios/hooks'
import { useCargaCompleta } from '../../../features/precios/useCargaCompleta'
import { useOperationIdDeEnvio } from '../../../features/precios/useOperationIdDeEnvio'
import { formatearFechaHora } from '../../../lib/fecha'
import { formatearCosto, formatearImporte, parsearImporteDesdeApi } from '../../../lib/money'
import { AVISO_SIN_CONEXION, describirError, estaSinConexion } from './errores'
import { PreciosSinPermiso } from './PreciosSinPermiso'
import { PresentacionesDePrecio } from './PresentacionesDePrecio'

const TITULO = 'Versión de lista'
const ENLACE = 'text-sm text-primary/70 hover:text-primary hover:underline'
const SIN_DATO = '—'

function momento(valor: string | null): string {
  return valor ? formatearFechaHora(valor) : SIN_DATO
}

/**
 * Versión publicada, programada, histórica o anulada de `/admin/precios/:listaId/versiones/:versionId`
 * (change 13, tarea 13.3; PRC-03, PRC-04, PRC-05, INV-11). Es de SOLO LECTURA: ningún control edita
 * los precios de una versión publicada. "Anular" solo con `PUBLICAR_LISTAS` y solo si el estado
 * derivado es `PROGRAMADA`. Un borrador se edita en su propia pantalla.
 */
export function VersionScreen() {
  const { listaId, versionId } = useParams<{ listaId: string; versionId: string }>()
  return (
    <SiTienePermiso permiso={['GESTIONAR_LISTAS', 'PUBLICAR_LISTAS']} fallback={<PreciosSinPermiso titulo={TITULO} />}>
      <Version listaId={listaId as string} versionId={versionId as string} />
    </SiTienePermiso>
  )
}

function Version({ listaId, versionId }: { listaId: string; versionId: string }) {
  const consulta = usePreciosDeVersion(listaId, versionId)
  useCargaCompleta(consulta)

  if (consulta.isPending) {
    return (
      <main>
        <p>Cargando…</p>
      </main>
    )
  }
  if (consulta.isError) {
    if (consulta.error instanceof PermisoRequeridoPreciosError) return <PreciosSinPermiso titulo={TITULO} />
    const noExiste = consulta.error instanceof ErrorDePrecios && consulta.error.estado === 404
    return (
      <main className="flex flex-col gap-4">
        <PageHeader titulo={TITULO} acciones={<VolverALista listaId={listaId} />} />
        <Alert>{noExiste ? 'No se encontró la versión.' : 'No se pudo obtener la versión.'}</Alert>
      </main>
    )
  }

  const version = consulta.data.pages[0]?.version
  if (version === undefined) return null
  const precios = consulta.data.pages.flatMap((pagina) => pagina.precios)

  return (
    <main className="flex flex-col gap-4">
      <PageHeader
        titulo={`Versión ${version.numero}`}
        acciones={
          <>
            {puedeAnularse(version.estado, version.estado_derivado) && (
              <SiTienePermiso permiso="PUBLICAR_LISTAS">
                <AnularVersion listaId={listaId} version={version} />
              </SiTienePermiso>
            )}
            <VolverALista listaId={listaId} />
          </>
        }
      />
      <DatosDeLaVersion version={version} />
      {version.estado === 'BORRADOR' ? (
        <p className="text-sm text-primary/70">
          Esta versión es el borrador de la lista y se edita en su propia pantalla.{' '}
          <Link to={`/admin/precios/${listaId}/borrador`} className={ENLACE}>
            Abrir el borrador
          </Link>
        </p>
      ) : (
        <PreciosDeLaVersion precios={precios} />
      )}
    </main>
  )
}

function VolverALista({ listaId }: { listaId: string }) {
  return (
    <Link to={`/admin/precios/${listaId}`} className={ENLACE}>
      Volver a la lista
    </Link>
  )
}

function DatosDeLaVersion({ version }: { version: Version }) {
  return (
    <Card>
      <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
        <dt className="text-primary/70">Estado</dt>
        <dd>
          <Badge variante={version.estado === 'ANULADA' ? 'negativo' : 'neutral'}>
            {etiquetaDeEstadoDeVersion(version.estado, version.estado_derivado)}
          </Badge>
        </dd>
        <dt className="text-primary/70">Vigencia desde</dt>
        <dd>{momento(version.vigencia_desde)}</dd>
        <dt className="text-primary/70">Vigencia hasta</dt>
        <dd>{momento(version.vigencia_hasta)}</dd>
      </dl>
      <div className="mt-3 flex flex-col gap-1 text-sm text-primary/80">
        <p>
          Generada el {momento(version.generado_en)} por {version.creado_por_nombre ?? version.creado_por_id}.
        </p>
        {version.publicado_por_id && (
          <p>
            Publicada por {version.publicado_por_nombre ?? version.publicado_por_id} el {momento(version.publicado_en)}.
          </p>
        )}
        {version.anulado_por_id && (
          <p>
            Anulada por {version.anulado_por_nombre ?? version.anulado_por_id} el {momento(version.anulado_en)}.
          </p>
        )}
      </div>
    </Card>
  )
}

function PreciosDeLaVersion({ precios }: { precios: PrecioDeVersion[] }) {
  const permisos = usePermisos()
  const verCostos = permisos.tiene('VER_COSTOS')

  const columnas: ColumnaTabla<PrecioDeVersion>[] = [
    {
      clave: 'producto',
      encabezado: 'Producto',
      render: (p) => (
        <div className="flex flex-col gap-1">
          <span className="font-medium text-primary">{p.producto_nombre ?? p.producto_id}</span>
          <PresentacionesDePrecio
            precioReferencia={p.precio_final}
            unidadesReferencia={p.unidades_referencia}
            presentaciones={p.presentaciones}
          />
        </div>
      ),
    },
    {
      clave: 'precio',
      encabezado: 'Precio',
      render: (p) => `$ ${formatearImporte(parsearImporteDesdeApi(p.precio_final))}`,
    },
    { clave: 'unidades', encabezado: 'Unidades de referencia', render: (p) => p.unidades_referencia },
    { clave: 'manual', encabezado: 'Origen', render: (p) => (p.manual ? 'Manual' : 'Calculado') },
    ...(verCostos
      ? [
          {
            clave: 'costo',
            encabezado: 'Costo de referencia',
            render: (p: PrecioDeVersion) =>
              p.costo_referencia === null ? SIN_DATO : `$ ${formatearCosto(parsearImporteDesdeApi(p.costo_referencia))}`,
          },
          {
            clave: 'regla',
            encabezado: 'Regla',
            render: (p: PrecioDeVersion) =>
              p.tipo_margen && p.valor_margen
                ? `${etiquetaDeTipoDeMargen(p.tipo_margen)} ${porcentajeDesdeFraccion(p.valor_margen)}%`
                : SIN_DATO,
          },
        ]
      : []),
  ]

  return (
    <section className="flex flex-col gap-3" aria-labelledby="titulo-precios-version">
      <h2 id="titulo-precios-version" className="text-base font-semibold text-primary">
        Precios
      </h2>
      {precios.length === 0 ? (
        <p className="text-sm text-primary/70">La versión no tiene precios.</p>
      ) : (
        <Card className="overflow-x-auto">
          <Tabla filas={precios} columnas={columnas} obtenerClave={(p) => p.producto_id} etiqueta="Precios de la versión" />
        </Card>
      )}
    </section>
  )
}

/** Anula una versión programada (PRC-05): sus precios no se borran ni cambian. */
function AnularVersion({ listaId, version }: { listaId: string; version: Version }) {
  const navigate = useNavigate()
  const anular = useAnularVersion()
  const [abierto, setAbierto] = useState(false)
  const [aviso, setAviso] = useState<string | null>(null)
  const operationId = useOperationIdDeEnvio({ accion: 'LISTA_ANULAR_VERSION', listaId, versionId: version.id })

  const cerrar = () => {
    setAbierto(false)
    setAviso(null)
  }

  const confirmar = async () => {
    setAviso(null)
    if (estaSinConexion()) {
      setAviso(AVISO_SIN_CONEXION)
      return
    }
    try {
      await anular.mutateAsync({ listaId, versionId: version.id, operationId: operationId.obtener() })
      operationId.completar()
      cerrar()
      navigate(`/admin/precios/${listaId}`)
    } catch (error) {
      setAviso(describirError(error).mensaje)
    }
  }

  return (
    <>
      <Boton variante="peligro" onClick={() => setAbierto(true)}>
        Anular versión
      </Boton>
      <Dialogo abierto={abierto} titulo={`Anular la versión ${version.numero}`} onCerrar={cerrar}>
        <div className="flex flex-col gap-3 text-sm text-primary">
          <p>
            La versión está programada y todavía no rige. Al anularla sigue en el historial y sus precios no se borran
            ni cambian; la lista deja de contar con ella.
          </p>
          {aviso && <Alert>{aviso}</Alert>}
          <div className="flex gap-2">
            <Boton variante="peligro" disabled={anular.isPending} onClick={() => void confirmar()}>
              Confirmar anulación
            </Boton>
            <Boton variante="secundario" onClick={cerrar}>
              Cancelar
            </Boton>
          </div>
        </div>
      </Dialogo>
    </>
  )
}

export default VersionScreen
