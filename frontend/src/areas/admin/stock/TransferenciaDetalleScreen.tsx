import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { Alert } from '../../../components/ui/Alert'
import { Boton } from '../../../components/ui/Button'
import { Card } from '../../../components/ui/Card'
import { PageHeader } from '../../../components/ui/PageHeader'
import { Tabla, type ColumnaTabla } from '../../../components/ui/Table'
import { formatearCantidad, referenciaDeRespuesta } from '../../../domain/stock/cantidades'
import {
  AMBITO_DE_ANULACION_DE_TRANSFERENCIA,
  ESTADO_CONFIRMADA,
  puedeAnularTransferencia,
} from '../../../domain/stock/operaciones'
import { SiTienePermiso } from '../../../features/identidad/SiTienePermiso'
import { usePermisos } from '../../../features/identidad/usePermisos'
import type { LineaDeTransferencia } from '../../../features/stock/api'
import { RecursoNoEncontradoStockError } from '../../../features/stock/errores'
import { useAnularTransferencia, useTransferencia } from '../../../features/stock/hooks'
import { formatearFechaHora } from '../../../lib/fecha'
import { AnularOperacionDialogo, CLASE_ENLACE, InsigniaDeEstado, PantallaSinPermiso } from './piezasDeOperacion'

const TITULO = 'Transferencia'

/**
 * Detalle de una transferencia y su anulación (change 14, tareas 13.1 y 13.3; spec
 * `administracion-de-stock`; TR-06, `design.md` D5, D5.4, D11). "Anular" solo en una `CONFIRMADA`
 * y solo a quien puede (`puedeAnularTransferencia`, del dominio). Una `ANULADA` muestra motivo,
 * usuario y momento de la anulación. Sin costos: una transferencia no los muestra (ADR-036).
 */
export function TransferenciaDetalleScreen() {
  return (
    <SiTienePermiso
      permiso="TRANSFERIR_STOCK"
      fallback={<PantallaSinPermiso titulo={TITULO} mensaje="No tenés permiso para ver las transferencias." />}
    >
      <Detalle />
    </SiTienePermiso>
  )
}

function Detalle() {
  const { transferenciaId } = useParams<{ transferenciaId: string }>()
  const transferencia = useTransferencia(transferenciaId)
  const anular = useAnularTransferencia()
  const permisos = usePermisos()
  const [abierto, setAbierto] = useState(false)

  if (transferencia.isPending) return <p>Cargando…</p>
  if (transferencia.isError) {
    return (
      <main className="flex flex-col gap-4">
        <PageHeader titulo={TITULO} />
        <Alert>
          {transferencia.error instanceof RecursoNoEncontradoStockError
            ? 'No se encontró la transferencia.'
            : 'No se pudo obtener la transferencia.'}
        </Alert>
      </main>
    )
  }

  const datos = transferencia.data
  const puedeAnular =
    datos.estado === ESTADO_CONFIRMADA &&
    puedeAnularTransferencia(datos.usuario_id, permisos.yo?.usuario.id ?? '', permisos)

  const columnas: ColumnaTabla<LineaDeTransferencia>[] = [
    { clave: 'codigo', encabezado: 'Código', render: (l) => l.producto_codigo ?? '' },
    { clave: 'producto', encabezado: 'Producto', render: (l) => l.producto_nombre ?? '' },
    {
      clave: 'cantidad',
      encabezado: 'Cantidad',
      render: (l) => formatearCantidad(l.cantidad_base, referenciaDeRespuesta(l.unidades_referencia, l.nombre_referencia)),
    },
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
            <Link to="/admin/stock/transferencias" className={CLASE_ENLACE}>
              Volver al listado
            </Link>
          </>
        }
      />

      <Card className="flex flex-col gap-1 text-sm text-primary">
        <p className="flex items-center gap-2">
          Estado: <InsigniaDeEstado estado={datos.estado} />
        </p>
        <p>{`${datos.ubicacion_origen_nombre} → ${datos.ubicacion_destino_nombre}`}</p>
        <p>
          Registrada el {formatearFechaHora(datos.occurred_at)} por {datos.usuario_nombre ?? ''}
        </p>
        {datos.observacion && <p>Observación: {datos.observacion}</p>}
      </Card>

      <Card>
        <Tabla filas={datos.lineas} columnas={columnas} obtenerClave={(l) => l.producto_id} />
      </Card>

      {datos.anulacion && (
        <Card className="flex flex-col gap-1 text-sm text-primary" data-testid="anulacion">
          <h2 className="text-base font-semibold">Anulación</h2>
          <p>Motivo: {datos.anulacion.motivo_nombre ?? datos.anulacion.motivo_id}</p>
          <p>Usuario: {datos.anulacion.anulada_por_nombre ?? ''}</p>
          <p>Anulada el {formatearFechaHora(datos.anulacion.anulada_en)}</p>
        </Card>
      )}

      <AnularOperacionDialogo
        abierto={abierto}
        titulo="Anular transferencia"
        id={datos.id}
        ambito={AMBITO_DE_ANULACION_DE_TRANSFERENCIA}
        onCerrar={() => setAbierto(false)}
        onConfirmar={(motivoId, operationId) =>
          anular.mutateAsync({ id: datos.id, motivo_id: motivoId, operationId })
        }
        onYaAnulada={() => void transferencia.refetch()}
      />
    </main>
  )
}

export default TransferenciaDetalleScreen
