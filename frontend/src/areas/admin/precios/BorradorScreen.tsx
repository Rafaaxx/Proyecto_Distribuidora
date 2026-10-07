import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { Alert } from '../../../components/ui/Alert'
import { Badge } from '../../../components/ui/Badge'
import { Boton } from '../../../components/ui/Button'
import { Card } from '../../../components/ui/Card'
import { PageHeader } from '../../../components/ui/PageHeader'
import { Tabla, type ColumnaTabla } from '../../../components/ui/Table'
import { porcentajeDesdeFraccion } from '../../../domain/precios/reglaSchema'
import {
  avisosDeGeneracion,
  etiquetaDeCausaSinPrecio,
  etiquetaDeRelacion,
  etiquetaDeTipoDeMargen,
  etiquetasDeSenales,
  resumenDePublicacion,
} from '../../../domain/precios/presentacion'
import { SiTienePermiso } from '../../../features/identidad/SiTienePermiso'
import { usePermisos } from '../../../features/identidad/usePermisos'
import type { Generacion, PrecioDeVersion, ProductoSinPrecio } from '../../../features/precios/api'
import { ErrorDePrecios, PermisoRequeridoPreciosError } from '../../../features/precios/errores'
import { useBorrador, useFijarPrecioManual, useGenerarBorrador, useListaDetalle } from '../../../features/precios/hooks'
import { useCargaCompleta } from '../../../features/precios/useCargaCompleta'
import { useOperationIdDeEnvio } from '../../../features/precios/useOperationIdDeEnvio'
import { formatearFechaHora } from '../../../lib/fecha'
import { formatearCosto, formatearImporte, parsearImporteDesdeApi } from '../../../lib/money'
import { AVISO_SIN_CONEXION, describirError, estaSinConexion } from './errores'
import { PrecioManualDialogo, type ProductoAFijar } from './PrecioManualDialogo'
import { PreciosSinPermiso } from './PreciosSinPermiso'
import { PresentacionesDePrecio } from './PresentacionesDePrecio'
import { PublicarDialogo } from './PublicarDialogo'

const TITULO = 'Borrador de la lista'
const ENLACE = 'text-sm text-primary/70 hover:text-primary hover:underline'
const SIN_DATO = '—'

function importe(valor: string | null): string {
  return valor === null ? SIN_DATO : `$ ${formatearImporte(parsearImporteDesdeApi(valor))}`
}

function costo(valor: string | null): string {
  return valor === null ? SIN_DATO : `$ ${formatearCosto(parsearImporteDesdeApi(valor))}`
}

/**
 * Pantalla del borrador de una lista de `/admin/precios/:listaId/borrador` (change 13, tareas
 * 13.2 y 13.3; PRC-17, PRC-22, D4, D5, D7, D12). La ve quien tiene `GESTIONAR_LISTAS` o
 * `PUBLICAR_LISTAS`; "Regenerar" y la edición de precios, solo con `GESTIONAR_LISTAS`;
 * "Publicar", solo con `PUBLICAR_LISTAS`. Las columnas de costo solo con `VER_COSTOS`. Los
 * importes se muestran desde el string de la API, sin pasar por `number`.
 */
export function BorradorScreen() {
  const { listaId } = useParams<{ listaId: string }>()
  return (
    <SiTienePermiso permiso={['GESTIONAR_LISTAS', 'PUBLICAR_LISTAS']} fallback={<PreciosSinPermiso titulo={TITULO} />}>
      <Borrador listaId={listaId as string} />
    </SiTienePermiso>
  )
}

function Borrador({ listaId }: { listaId: string }) {
  const borrador = useBorrador(listaId)
  const lista = useListaDetalle(listaId)
  useCargaCompleta(borrador)
  const [productoAFijar, setProductoAFijar] = useState<ProductoAFijar | null>(null)
  const [publicando, setPublicando] = useState(false)
  const [resultado, setResultado] = useState<Generacion | null>(null)
  const [aviso, setAviso] = useState<string | null>(null)

  const precios = borrador.data?.pages.flatMap((pagina) => pagina.precios) ?? []
  const nombreDeLista = lista.data?.nombre ?? ''

  if (borrador.isPending) {
    return (
      <main>
        <p>Cargando…</p>
      </main>
    )
  }

  if (borrador.isError) {
    if (borrador.error instanceof PermisoRequeridoPreciosError) return <PreciosSinPermiso titulo={TITULO} />
    if (borrador.error instanceof ErrorDePrecios && borrador.error.estado === 404) {
      return (
        <SinBorrador
          listaId={listaId}
          nombreDeLista={nombreDeLista}
          alGenerar={setResultado}
          aviso={aviso}
          setAviso={setAviso}
        />
      )
    }
    return (
      <main className="flex flex-col gap-4">
        <PageHeader titulo={TITULO} acciones={<VolverALista listaId={listaId} />} />
        <Alert>No se pudo obtener el borrador.</Alert>
      </main>
    )
  }

  const primera = borrador.data.pages[0]
  if (primera === undefined) return null
  const version = primera.version
  const sinPrecio = primera.productos_sin_precio

  return (
    <main className="flex flex-col gap-4">
      <PageHeader
        titulo={`Borrador n.º ${version.numero}${nombreDeLista ? ` de ${nombreDeLista}` : ''}`}
        acciones={
          <>
            <SiTienePermiso permiso="GESTIONAR_LISTAS">
              <BotonRegenerar listaId={listaId} alGenerar={setResultado} setAviso={setAviso} etiqueta="Regenerar" />
            </SiTienePermiso>
            <SiTienePermiso permiso="PUBLICAR_LISTAS">
              <Boton onClick={() => setPublicando(true)}>Publicar</Boton>
            </SiTienePermiso>
            <VolverALista listaId={listaId} />
          </>
        }
      />

      <Card className="flex flex-col gap-1 text-sm text-primary">
        <p>
          Generado el {version.generado_en ? formatearFechaHora(version.generado_en) : SIN_DATO}. Publicar no recalcula:
          si cambiaron costos, reglas o redondeos desde entonces, regenerá el borrador antes de publicar.
        </p>
      </Card>

      {aviso && <Alert>{aviso}</Alert>}
      {resultado && <ResultadoDeGeneracion resultado={resultado} />}

      <section className="flex flex-col gap-3" aria-labelledby="titulo-precios">
        <h2 id="titulo-precios" className="text-base font-semibold text-primary">
          Precios
        </h2>
        {precios.length === 0 ? (
          <p className="text-sm text-primary/70">El borrador todavía no tiene precios.</p>
        ) : (
          <TablaDePrecios
            listaId={listaId}
            versionId={version.id}
            precios={precios}
            alFijar={setProductoAFijar}
          />
        )}
      </section>

      <section className="flex flex-col gap-3" aria-labelledby="titulo-sin-precio">
        <h2 id="titulo-sin-precio" className="text-base font-semibold text-primary">
          Productos sin precio
        </h2>
        {sinPrecio.length === 0 ? (
          <p className="text-sm text-primary/70">Todos los productos activos tienen precio.</p>
        ) : (
          <TablaSinPrecio productos={sinPrecio} alFijar={setProductoAFijar} />
        )}
      </section>

      <PrecioManualDialogo
        listaId={listaId}
        versionId={version.id}
        producto={productoAFijar}
        onCerrar={() => setProductoAFijar(null)}
      />
      <PublicarDialogo
        listaId={listaId}
        versionId={version.id}
        cantidadDePrecios={precios.length}
        cantidadSinPrecio={sinPrecio.length}
        abierto={publicando}
        onCerrar={() => setPublicando(false)}
      />
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

function SinBorrador({
  listaId,
  nombreDeLista,
  alGenerar,
  aviso,
  setAviso,
}: {
  listaId: string
  nombreDeLista: string
  alGenerar: (resultado: Generacion) => void
  aviso: string | null
  setAviso: (aviso: string | null) => void
}) {
  return (
    <main className="flex flex-col gap-4">
      <PageHeader titulo={nombreDeLista ? `Borrador de ${nombreDeLista}` : TITULO} acciones={<VolverALista listaId={listaId} />} />
      <p className="text-sm text-primary/70">La lista no tiene borrador.</p>
      {aviso && <Alert>{aviso}</Alert>}
      <SiTienePermiso permiso="GESTIONAR_LISTAS">
        <div>
          <BotonRegenerar listaId={listaId} alGenerar={alGenerar} setAviso={setAviso} etiqueta="Generar borrador" />
        </div>
      </SiTienePermiso>
    </main>
  )
}

/**
 * Genera o regenera el borrador (D5). Sin conexión no se envía nada. El `Operation-Id` se
 * conserva tras un error de red y se renueva después de un envío completado (INV-06).
 */
function BotonRegenerar({
  listaId,
  alGenerar,
  setAviso,
  etiqueta,
}: {
  listaId: string
  alGenerar: (resultado: Generacion) => void
  setAviso: (aviso: string | null) => void
  etiqueta: string
}) {
  const generar = useGenerarBorrador()
  const operationId = useOperationIdDeEnvio({ accion: 'LISTA_GENERAR_BORRADOR', listaId })

  const regenerar = async () => {
    setAviso(null)
    if (estaSinConexion()) {
      setAviso(AVISO_SIN_CONEXION)
      return
    }
    try {
      const resultado = await generar.mutateAsync({ listaId, operationId: operationId.obtener() })
      operationId.completar()
      alGenerar(resultado)
    } catch (error) {
      setAviso(describirError(error).mensaje)
    }
  }

  return (
    <Boton disabled={generar.isPending} onClick={() => void regenerar()}>
      {etiqueta}
    </Boton>
  )
}

function ResultadoDeGeneracion({ resultado }: { resultado: Generacion }) {
  const avisos = avisosDeGeneracion(resultado)
  return (
    <Card className="flex flex-col gap-1 text-sm text-primary">
      <p>
        Borrador {resultado.regenerado ? 'regenerado' : 'generado'}:{' '}
        {resumenDePublicacion(resultado.cantidad_precios, resultado.productos_sin_precio.length)}.
      </p>
      {avisos.map((aviso) => (
        <p key={aviso}>{aviso}</p>
      ))}
    </Card>
  )
}

function TablaDePrecios({
  listaId,
  versionId,
  precios,
  alFijar,
}: {
  listaId: string
  versionId: string
  precios: PrecioDeVersion[]
  alFijar: (producto: ProductoAFijar) => void
}) {
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
    { clave: 'anterior', encabezado: 'Precio anterior', render: (p) => importe(p.precio_version_base) },
    { clave: 'nuevo', encabezado: 'Precio nuevo', render: (p) => importe(p.precio_final) },
    {
      clave: 'estado',
      encabezado: 'Estado',
      render: (p) => (
        <div className="flex flex-wrap gap-1">
          {p.relacion && <Badge>{etiquetaDeRelacion(p.relacion)}</Badge>}
          {p.manual && <Badge variante="positivo">Manual</Badge>}
        </div>
      ),
    },
    {
      clave: 'senales',
      encabezado: 'Señales',
      render: (p) => {
        const senales = etiquetasDeSenales(p.senales)
        return senales.length === 0 ? (
          SIN_DATO
        ) : (
          <ul className="flex flex-col gap-1">
            {senales.map((senal) => (
              <li key={senal}>
                <Badge variante="negativo">{senal}</Badge>
              </li>
            ))}
          </ul>
        )
      },
    },
    ...(verCostos
      ? [
          { clave: 'costo', encabezado: 'Costo de referencia', render: (p: PrecioDeVersion) => costo(p.costo_referencia) },
          {
            clave: 'regla',
            encabezado: 'Regla',
            render: (p: PrecioDeVersion) =>
              p.tipo_margen && p.valor_margen
                ? `${etiquetaDeTipoDeMargen(p.tipo_margen)} ${porcentajeDesdeFraccion(p.valor_margen)}%`
                : SIN_DATO,
          },
          { clave: 'calculado', encabezado: 'Precio calculado', render: (p: PrecioDeVersion) => costo(p.precio_calculado) },
        ]
      : []),
    {
      clave: 'acciones',
      encabezado: 'Acciones',
      render: (p) => (
        <SiTienePermiso permiso="GESTIONAR_LISTAS">
          <div className="flex flex-wrap gap-2">
            <Boton
              variante="secundario"
              onClick={() => alFijar({ productoId: p.producto_id, nombre: p.producto_nombre ?? p.producto_id })}
            >
              {p.manual ? 'Cambiar precio' : 'Fijar precio'}
            </Boton>
            {p.manual && <BotonQuitarManual listaId={listaId} versionId={versionId} productoId={p.producto_id} />}
          </div>
        </SiTienePermiso>
      ),
    },
  ]

  return (
    <Card className="overflow-x-auto">
      <Tabla filas={precios} columnas={columnas} obtenerClave={(p) => p.producto_id} etiqueta="Precios del borrador" />
    </Card>
  )
}

/** Quita la marca manual: el precio vuelve a calcularse (D7). */
function BotonQuitarManual({
  listaId,
  versionId,
  productoId,
}: {
  listaId: string
  versionId: string
  productoId: string
}) {
  const fijar = useFijarPrecioManual()
  const operationId = useOperationIdDeEnvio({ listaId, versionId, productoId, precio: null })
  const [aviso, setAviso] = useState<string | null>(null)

  const quitar = async () => {
    setAviso(null)
    if (estaSinConexion()) {
      setAviso(AVISO_SIN_CONEXION)
      return
    }
    try {
      await fijar.mutateAsync({ listaId, versionId, productoId, precio_final: null, operationId: operationId.obtener() })
      operationId.completar()
    } catch (error) {
      setAviso(describirError(error).mensaje)
    }
  }

  return (
    <>
      <Boton variante="secundario" disabled={fijar.isPending} onClick={() => void quitar()}>
        Quitar precio manual
      </Boton>
      {aviso && <Alert>{aviso}</Alert>}
    </>
  )
}

function TablaSinPrecio({
  productos,
  alFijar,
}: {
  productos: ProductoSinPrecio[]
  alFijar: (producto: ProductoAFijar) => void
}) {
  const columnas: ColumnaTabla<ProductoSinPrecio>[] = [
    { clave: 'producto', encabezado: 'Producto', render: (p) => p.producto_nombre ?? p.producto_id },
    { clave: 'causa', encabezado: 'Causa', render: (p) => etiquetaDeCausaSinPrecio(p.causa) },
    {
      clave: 'acciones',
      encabezado: 'Acciones',
      render: (p) =>
        p.causa === 'SIN_PRESENTACION_DE_REFERENCIA' ? (
          <span className="text-sm text-primary/70">Asignale una presentación de referencia en el catálogo.</span>
        ) : (
          <SiTienePermiso permiso="GESTIONAR_LISTAS">
            <Boton
              variante="secundario"
              onClick={() => alFijar({ productoId: p.producto_id, nombre: p.producto_nombre ?? p.producto_id })}
            >
              Fijar precio
            </Boton>
          </SiTienePermiso>
        ),
    },
  ]
  return (
    <Card>
      <Tabla filas={productos} columnas={columnas} obtenerClave={(p) => p.producto_id} etiqueta="Productos sin precio" />
    </Card>
  )
}

export default BorradorScreen
