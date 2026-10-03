import { zodResolver } from '@hookform/resolvers/zod'
import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { Link, useParams } from 'react-router-dom'

import { Alert } from '../../../components/ui/Alert'
import { Boton } from '../../../components/ui/Button'
import { Card } from '../../../components/ui/Card'
import { Campo } from '../../../components/ui/Field'
import { PageHeader } from '../../../components/ui/PageHeader'
import { Tabla, type ColumnaTabla } from '../../../components/ui/Table'
import { aFiltros, esquemaPeriodo, type DatosPeriodo } from '../../../domain/cuentas-corrientes/periodoSchema'
import { formatearCantidad, referenciaDeRespuesta } from '../../../domain/stock/cantidades'
import { formatearCostoDeApi } from '../../../domain/stock/costos'
import { etiquetaDeTipoDeMovimiento } from '../../../domain/stock/ubicacionSchema'
import { SiTienePermiso } from '../../../features/identidad/SiTienePermiso'
import { usePermisos } from '../../../features/identidad/usePermisos'
import type { Kardex, LineaDeKardex } from '../../../features/stock/api'
import type { FiltrosKardex } from '../../../features/stock/claves'
import { PermisoRequeridoStockError, RecursoNoEncontradoStockError } from '../../../features/stock/errores'
import { useKardex } from '../../../features/stock/hooks'
import { formatearFechaHoraEnZona } from '../../../lib/fecha'

const SIN_PERMISO = 'No tenés permiso para ver el stock.'
const NO_EXISTE = 'El producto o la ubicación pedidos no existen.'
const MENSAJE_GENERICO = 'No se pudo obtener el kardex.'
const CLASE_ENLACE = 'text-sm text-primary/70 hover:text-primary hover:underline'

function KardexSinPermiso() {
  return (
    <main className="flex flex-col gap-4">
      <PageHeader titulo="Kardex" />
      <p className="text-sm text-primary/70">{SIN_PERMISO}</p>
    </main>
  )
}

function mensajeDeError(error: unknown): string {
  if (error instanceof RecursoNoEncontradoStockError) return NO_EXISTE
  if (error instanceof PermisoRequeridoStockError) return SIN_PERMISO
  return error instanceof Error && error.message ? error.message : MENSAJE_GENERICO
}

/**
 * Kardex de un producto en una ubicación (change 09, tarea 8.3; `design.md` D3,
 * D11, D15; STK-04). Ruta `/admin/stock/ubicaciones/:ubicacionId/kardex/:productoId`.
 * Movimientos en orden con el saldo acumulado que calcula el servidor sobre la
 * historia completa, filtro de período (fechas de negocio `aaaa-mm-dd` en la zona
 * de la organización, TR-04), saldo anterior y "cargar más" por cursor. Las
 * cantidades se muestran en unidades con la equivalencia en la presentación de referencia
 * que informa el propio kardex. El costo unitario solo con `VER_COSTOS`.
 */
export function KardexScreen() {
  const { ubicacionId, productoId } = useParams<{ ubicacionId: string; productoId: string }>()
  return (
    <SiTienePermiso permiso="TRANSFERIR_STOCK" fallback={<KardexSinPermiso />}>
      {ubicacionId && productoId ? <KardexDelProducto ubicacionId={ubicacionId} productoId={productoId} /> : null}
    </SiTienePermiso>
  )
}

function KardexDelProducto({ ubicacionId, productoId }: { ubicacionId: string; productoId: string }) {
  const [filtros, setFiltros] = useState<FiltrosKardex>({})
  const kardex = useKardex(productoId, ubicacionId, filtros)

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<DatosPeriodo>({
    resolver: zodResolver(esquemaPeriodo),
    defaultValues: { desde: '', hasta: '' },
  })

  const filtrar = handleSubmit((datos) => {
    setFiltros(aFiltros(datos))
  })
  const quitarFiltro = () => {
    reset({ desde: '', hasta: '' })
    setFiltros({})
  }
  const hayFiltro = filtros.desde !== undefined || filtros.hasta !== undefined
  const errorAlCargarMas = kardex.isFetchNextPageError ? mensajeDeError(kardex.error) : null

  return (
    <main className="flex flex-col gap-4">
      <PageHeader
        titulo="Kardex"
        acciones={
          <Link to={`/admin/stock/ubicaciones/${ubicacionId}/stock`} className={CLASE_ENLACE}>
            Volver al stock
          </Link>
        }
      />

      <Card>
        <form onSubmit={(evento) => void filtrar(evento)} noValidate className="flex flex-wrap items-start gap-3">
          <Campo id="desde" etiqueta="Desde" error={errors.desde?.message}>
            <input id="desde" type="date" className="rounded-md border border-border px-2 py-1 text-sm" {...register('desde')} />
          </Campo>
          <Campo id="hasta" etiqueta="Hasta" error={errors.hasta?.message}>
            <input id="hasta" type="date" className="rounded-md border border-border px-2 py-1 text-sm" {...register('hasta')} />
          </Campo>
          <div className="flex items-end gap-2 self-end">
            <Boton type="submit">Filtrar</Boton>
            {hayFiltro && (
              <Boton type="button" variante="secundario" onClick={quitarFiltro}>
                Quitar filtro
              </Boton>
            )}
          </div>
        </form>
      </Card>

      {kardex.isPending && <p>Cargando…</p>}
      {kardex.isError && <Alert>{mensajeDeError(kardex.error)}</Alert>}
      {kardex.isSuccess && (
        <ContenidoDelKardex
          paginas={kardex.data.pages}
          hayFiltro={hayFiltro}
          hayMas={kardex.hasNextPage}
          cargandoMas={kardex.isFetchingNextPage}
          errorAlCargarMas={errorAlCargarMas}
          onCargarMas={() => void kardex.fetchNextPage()}
        />
      )}
    </main>
  )
}

function ContenidoDelKardex({
  paginas,
  hayFiltro,
  hayMas,
  cargandoMas,
  errorAlCargarMas,
  onCargarMas,
}: {
  paginas: Kardex[]
  hayFiltro: boolean
  hayMas: boolean
  cargandoMas: boolean
  errorAlCargarMas: string | null
  onCargarMas: () => void
}) {
  const permisos = usePermisos()
  const verCostos = permisos.tiene('VER_COSTOS')
  const primera = paginas[0]
  if (!primera) return null
  const referencia = referenciaDeRespuesta(primera.unidades_referencia, primera.nombre_referencia)
  const zona = primera.zona_horaria
  const movimientos = paginas.flatMap((pagina) => pagina.items)

  const columnas: ColumnaTabla<LineaDeKardex>[] = [
    { clave: 'fecha', encabezado: 'Fecha', render: (m) => formatearFechaHoraEnZona(m.occurred_at, zona) },
    { clave: 'tipo', encabezado: 'Tipo', render: (m) => etiquetaDeTipoDeMovimiento(m.tipo) },
    { clave: 'cantidad', encabezado: 'Cantidad', render: (m) => formatearCantidad(m.cantidad_base, referencia) },
    ...(verCostos
      ? [
          {
            clave: 'costo',
            encabezado: 'Costo unitario',
            render: (m: LineaDeKardex) => formatearCostoDeApi(m.costo_unitario),
          },
        ]
      : []),
    {
      clave: 'saldo',
      encabezado: 'Saldo acumulado',
      render: (m) => formatearCantidad(m.saldo_acumulado, referencia),
    },
  ]

  return (
    <>
      <Card>
        <p className="text-sm font-medium text-primary">
          {primera.producto_codigo} · {primera.producto_nombre}
        </p>
        <p className="mt-1 text-sm text-primary">Saldo actual: {formatearCantidad(primera.saldo_actual, referencia)}</p>
        {hayFiltro && (
          <p className="mt-1 text-sm text-primary/70">
            Saldo anterior: {formatearCantidad(primera.saldo_anterior, referencia)}
          </p>
        )}
      </Card>

      {movimientos.length === 0 ? (
        <p className="text-sm text-primary/70">No hay movimientos en este período.</p>
      ) : (
        <Card>
          <Tabla filas={movimientos} columnas={columnas} obtenerClave={(m) => m.id} />
        </Card>
      )}

      {errorAlCargarMas && <Alert>{errorAlCargarMas}</Alert>}
      {hayMas && (
        <div>
          <Boton type="button" variante="secundario" disabled={cargandoMas} onClick={onCargarMas}>
            Cargar más
          </Boton>
        </div>
      )}
    </>
  )
}

export default KardexScreen
