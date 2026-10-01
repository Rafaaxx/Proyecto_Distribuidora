import { Link, useParams } from 'react-router-dom'

import { Alert } from '../../../components/ui/Alert'
import { Boton } from '../../../components/ui/Button'
import { Card } from '../../../components/ui/Card'
import { PageHeader } from '../../../components/ui/PageHeader'
import { Tabla, type ColumnaTabla } from '../../../components/ui/Table'
import { formatearCantidad } from '../../../domain/stock/cantidades'
import { formatearCostoDeApi } from '../../../domain/stock/costos'
import { SiTienePermiso } from '../../../features/identidad/SiTienePermiso'
import { usePermisos } from '../../../features/identidad/usePermisos'
import type { LineaDeStock } from '../../../features/stock/api'
import { PermisoRequeridoStockError, RecursoNoEncontradoStockError } from '../../../features/stock/errores'
import { useSaldos } from '../../../features/stock/hooks'

const SIN_PERMISO = 'No tenés permiso para ver el stock.'
const NO_EXISTE = 'La ubicación pedida no existe.'
const MENSAJE_GENERICO = 'No se pudo obtener el stock.'
const CLASE_ENLACE = 'text-sm text-primary/70 hover:text-primary hover:underline'

function StockSinPermiso() {
  return (
    <main className="flex flex-col gap-4">
      <PageHeader titulo="Stock por ubicación" />
      <p className="text-sm text-primary/70">{SIN_PERMISO}</p>
    </main>
  )
}

/**
 * Stock de una ubicación (change 09, tarea 8.3; `design.md` D3, D11, D15; spec
 * `administracion-de-stock`; STK-01, CAT-08). Ruta
 * `/admin/stock/ubicaciones/:ubicacionId/stock`. Lo ve quien tiene
 * `TRANSFERIR_STOCK`: sin él no se monta y no se pide nada. Las cantidades se
 * muestran en cajas + unidades con la presentación de referencia del producto
 * (`lib`/`domain`, aritmética entera) y el costo promedio solo con `VER_COSTOS`
 * (de `['yo']`): quien no lo tiene no ve la columna aunque la respuesta trajera
 * el dato (el servidor además lo omite).
 */
export function StockPorUbicacionScreen() {
  const { ubicacionId } = useParams<{ ubicacionId: string }>()
  return (
    <SiTienePermiso permiso="TRANSFERIR_STOCK" fallback={<StockSinPermiso />}>
      {ubicacionId ? <StockDeLaUbicacion ubicacionId={ubicacionId} /> : null}
    </SiTienePermiso>
  )
}

function mensajeDeError(error: unknown): string {
  if (error instanceof RecursoNoEncontradoStockError) return NO_EXISTE
  if (error instanceof PermisoRequeridoStockError) return SIN_PERMISO
  return error instanceof Error && error.message ? error.message : MENSAJE_GENERICO
}

function StockDeLaUbicacion({ ubicacionId }: { ubicacionId: string }) {
  const saldos = useSaldos(ubicacionId)
  const permisos = usePermisos()
  const verCostos = permisos.tiene('VER_COSTOS')
  const filas = saldos.data?.pages.flatMap((pagina) => pagina.items) ?? []

  const columnas: ColumnaTabla<LineaDeStock>[] = [
    { clave: 'codigo', encabezado: 'Código', render: (l) => l.producto_codigo },
    { clave: 'producto', encabezado: 'Producto', render: (l) => l.producto_nombre },
    {
      clave: 'cantidad',
      encabezado: 'Cantidad',
      render: (l) => formatearCantidad(l.cantidad_base, l.unidades_referencia),
    },
    ...(verCostos
      ? [
          {
            clave: 'costo',
            encabezado: 'Costo promedio',
            render: (l: LineaDeStock) => formatearCostoDeApi(l.costo_promedio),
          },
        ]
      : []),
    {
      clave: 'acciones',
      encabezado: 'Acciones',
      render: (l) => (
        <Link to={`/admin/stock/ubicaciones/${ubicacionId}/kardex/${l.producto_id}`} className={CLASE_ENLACE}>
          Ver kardex
        </Link>
      ),
    },
  ]

  return (
    <main className="flex flex-col gap-4">
      <PageHeader
        titulo="Stock por ubicación"
        acciones={
          <>
            <SiTienePermiso permiso="IMPORTAR_DATOS">
              <Link to={`/admin/stock/ubicaciones/${ubicacionId}/stock-inicial`} className={CLASE_ENLACE}>
                Cargar stock inicial
              </Link>
            </SiTienePermiso>
            <Link to="/admin/stock" className={CLASE_ENLACE}>
              Volver a las ubicaciones
            </Link>
          </>
        }
      />

      {saldos.isPending && <p>Cargando…</p>}
      {saldos.isError && <Alert>{mensajeDeError(saldos.error)}</Alert>}
      {saldos.isSuccess && filas.length === 0 && (
        <p className="text-sm text-primary/70">No hay stock en esta ubicación.</p>
      )}
      {filas.length > 0 && (
        <Card>
          <Tabla filas={filas} columnas={columnas} obtenerClave={(l) => l.producto_id} />
        </Card>
      )}
      {saldos.isFetchNextPageError && <Alert>{mensajeDeError(saldos.error)}</Alert>}
      {saldos.hasNextPage && (
        <div>
          <Boton
            type="button"
            variante="secundario"
            disabled={saldos.isFetchingNextPage}
            onClick={() => void saldos.fetchNextPage()}
          >
            Cargar más
          </Boton>
        </div>
      )}
    </main>
  )
}

export default StockPorUbicacionScreen
