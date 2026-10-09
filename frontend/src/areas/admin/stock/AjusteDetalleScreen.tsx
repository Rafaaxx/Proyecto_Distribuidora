import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { Alert } from '../../../components/ui/Alert'
import { Boton } from '../../../components/ui/Button'
import { Card } from '../../../components/ui/Card'
import { PageHeader } from '../../../components/ui/PageHeader'
import { Tabla, type ColumnaTabla } from '../../../components/ui/Table'
import { formatearCantidad, referenciaDeRespuesta } from '../../../domain/stock/cantidades'
import { formatearCostoDeApi } from '../../../domain/stock/costos'
import { AMBITO_DE_ANULACION_DE_AJUSTE, ESTADO_CONFIRMADA, puedeAnularAjuste } from '../../../domain/stock/operaciones'
import { SiTienePermiso } from '../../../features/identidad/SiTienePermiso'
import { usePermisos } from '../../../features/identidad/usePermisos'
import type { LineaDeAjuste } from '../../../features/stock/api'
import { RecursoNoEncontradoStockError } from '../../../features/stock/errores'
import { useAjuste, useAnularAjuste } from '../../../features/stock/hooks'
import { formatearFechaHora } from '../../../lib/fecha'
import { AnularOperacionDialogo, CLASE_ENLACE, InsigniaDeEstado, PantallaSinPermiso } from './piezasDeOperacion'

const TITULO = 'Ajuste de stock'

/**
 * Detalle de un ajuste y su anulación (change 14, tareas 13.2 y 13.3; spec `administracion-de-stock`;
 * TR-06, `design.md` D5, D7, D11). "Anular" solo en un ajuste `CONFIRMADA` y solo con
 * `AJUSTAR_STOCK`, propio o ajeno. El costo de cada línea se muestra solo con `VER_COSTOS` (el
 * servidor además lo omite, ADR-036); acá no se calcula ningún importe.
 */
export function AjusteDetalleScreen() {
  return (
    <SiTienePermiso
      permiso="AJUSTAR_STOCK"
      fallback={<PantallaSinPermiso titulo={TITULO} mensaje="No tenés permiso para ver los ajustes." />}
    >
      <Detalle />
    </SiTienePermiso>
  )
}

function Detalle() {
  const { ajusteId } = useParams<{ ajusteId: string }>()
  const ajuste = useAjuste(ajusteId)
  const anular = useAnularAjuste()
  const permisos = usePermisos()
  const verCostos = permisos.tiene('VER_COSTOS')
  const [abierto, setAbierto] = useState(false)

  if (ajuste.isPending) return <p>Cargando…</p>
  if (ajuste.isError) {
    return (
      <main className="flex flex-col gap-4">
        <PageHeader titulo={TITULO} />
        <Alert>
          {ajuste.error instanceof RecursoNoEncontradoStockError
            ? 'No se encontró el ajuste.'
            : 'No se pudo obtener el ajuste.'}
        </Alert>
      </main>
    )
  }

  const datos = ajuste.data
  const puedeAnular = datos.estado === ESTADO_CONFIRMADA && puedeAnularAjuste(permisos)

  const columnas: ColumnaTabla<LineaDeAjuste>[] = [
    { clave: 'codigo', encabezado: 'Código', render: (l) => l.producto_codigo ?? '' },
    { clave: 'producto', encabezado: 'Producto', render: (l) => l.producto_nombre ?? '' },
    {
      clave: 'cantidad',
      encabezado: 'Cantidad',
      render: (l) => formatearCantidad(l.cantidad_base, referenciaDeRespuesta(l.unidades_referencia, l.nombre_referencia)),
    },
    ...(verCostos
      ? [
          {
            clave: 'costo',
            encabezado: 'Costo unitario',
            render: (l: LineaDeAjuste) => formatearCostoDeApi(l.costo_unitario ?? null),
          },
        ]
      : []),
  ]

  return (
    <main className="flex flex-col gap-4">
      <PageHeader
        titulo={TITULO}
        acciones={
          <>
            {puedeAnular && (
              <Boton variante="peligro" onClick={() => setAbierto(true)}>
                Anular
              </Boton>
            )}
            <Link to="/admin/stock/ajustes" className={CLASE_ENLACE}>
              Volver al listado
            </Link>
          </>
        }
      />

      <Card className="flex flex-col gap-1 text-sm text-primary">
        <p className="flex items-center gap-2">
          Estado: <InsigniaDeEstado estado={datos.estado} />
        </p>
        <p>Ubicación: {datos.ubicacion_nombre}</p>
        <p>Motivo: {datos.motivo_nombre ?? datos.motivo_id}</p>
        <p>
          Registrado el {formatearFechaHora(datos.occurred_at)} por {datos.usuario_nombre ?? ''}
        </p>
        {datos.observacion && <p>Observación: {datos.observacion}</p>}
      </Card>

      <Card>
        <Tabla filas={datos.lineas} columnas={columnas} obtenerClave={(l) => l.producto_id} />
      </Card>

      {datos.anulacion && (
        <Card className="flex flex-col gap-1 text-sm text-primary" data-testid="anulacion">
          <h2 className="text-base font-semibold">Anulación</h2>
          <p>Motivo de la anulación: {datos.anulacion.motivo_nombre ?? datos.anulacion.motivo_id}</p>
          <p>Usuario: {datos.anulacion.anulado_por_nombre ?? ''}</p>
          <p>Anulado el {formatearFechaHora(datos.anulacion.anulado_en)}</p>
        </Card>
      )}

      <AnularOperacionDialogo
        abierto={abierto}
        titulo="Anular ajuste"
        id={datos.id}
        ambito={AMBITO_DE_ANULACION_DE_AJUSTE}
        onCerrar={() => setAbierto(false)}
        onConfirmar={(motivoId, operationId) => anular.mutateAsync({ id: datos.id, motivo_id: motivoId, operationId })}
        onYaAnulada={() => void ajuste.refetch()}
      />
    </main>
  )
}

export default AjusteDetalleScreen
