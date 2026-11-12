import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { Alert } from '../../../components/ui/Alert'
import { Badge } from '../../../components/ui/Badge'
import { Boton } from '../../../components/ui/Button'
import { Card } from '../../../components/ui/Card'
import { Dialogo } from '../../../components/ui/Dialog'
import { PageHeader } from '../../../components/ui/PageHeader'
import {
  AMBITO_DE_ANULACION_DE_PAGO,
  ETIQUETA_DE_ESTADO_DE_PAGO,
  esPagoDeCompraVigente,
  etiquetaDeOrigen,
  puedeAnularse,
  textoDeSaldoTrasAnular,
} from '../../../domain/pagos-proveedores/presentacion'
import { useMotivos } from '../../../features/compras/hooks'
import { useOperationIdPorContenido } from '../../../features/compras/useOperationIdPorContenido'
import { SiTienePermiso } from '../../../features/identidad/SiTienePermiso'
import type { PagoDetalle } from '../../../features/pagos-proveedores/api'
import { ErrorDePagos, PermisoRequeridoPagosError } from '../../../features/pagos-proveedores/errores'
import { useAnularPago, usePago, useSaldoDelProveedor } from '../../../features/pagos-proveedores/hooks'
import { formatearFechaDeNegocio, formatearFechaHora } from '../../../lib/fecha'
import { formatearImporte, parsearImporteDesdeApi } from '../../../lib/money'
import { PagosSinPermiso } from './PagosSinPermiso'

const CLASE_CONTROL = 'rounded-md border border-border px-2 py-1 text-sm'

/**
 * Detalle de un pago a proveedor y su anulación (change 12, tarea 9.2; spec
 * `administracion-de-pagos`, `anulacion-de-pagos`). Lo ve quien tiene `REGISTRAR_PAGO_PROVEEDOR`
 * o `ANULAR_PAGO_PROVEEDOR` (D7); "Anular" solo con `ANULAR_PAGO_PROVEEDOR`, sobre un pago
 * `CONFIRMADA` que no sea el de una compra vigente (D2). Esa regla es `puedeAnularse`, del
 * dominio.
 */
export function PagoDetalleScreen() {
  return (
    <SiTienePermiso permiso={['REGISTRAR_PAGO_PROVEEDOR', 'ANULAR_PAGO_PROVEEDOR']} fallback={<PagosSinPermiso titulo="Pago a proveedor" />}>
      <DetalleDePago />
    </SiTienePermiso>
  )
}

function DetalleDePago() {
  const { pagoId } = useParams<{ pagoId: string }>()
  const pago = usePago(pagoId)
  const [rechazo, setRechazo] = useState<string | null>(null)

  if (pago.isPending) return <main><p>Cargando…</p></main>
  if (pago.isError) {
    if (pago.error instanceof PermisoRequeridoPagosError) return <PagosSinPermiso titulo="Pago a proveedor" />
    return (
      <main className="flex flex-col gap-4">
        <PageHeader titulo="Pago a proveedor" />
        <Alert>
          {pago.error instanceof ErrorDePagos && pago.error.codigo === 'RECURSO_NO_ENCONTRADO'
            ? 'No se encontró el pago.'
            : 'No se pudo obtener el pago.'}
        </Alert>
      </main>
    )
  }

  const datos = pago.data
  const deCompraVigente = esPagoDeCompraVigente(datos)

  return (
    <main className="flex flex-col gap-4">
      <PageHeader
        titulo={`Pago del ${formatearFechaDeNegocio(datos.fecha)}`}
        acciones={
          puedeAnularse(datos) ? (
            <SiTienePermiso permiso="ANULAR_PAGO_PROVEEDOR">
              <AnularPago
                pago={datos}
                alYaAnulado={(mensaje) => {
                  setRechazo(mensaje)
                  void pago.refetch()
                }}
              />
            </SiTienePermiso>
          ) : undefined
        }
      />

      {rechazo && <Alert>{rechazo}</Alert>}

      <Card className="flex flex-col gap-1 text-sm text-primary">
        <p>
          Proveedor: {datos.proveedor_nombre} · Origen: {etiquetaDeOrigen(datos.origen)} ·{' '}
          <Badge variante={datos.estado === 'ANULADA' ? 'negativo' : 'positivo'}>{ETIQUETA_DE_ESTADO_DE_PAGO[datos.estado] ?? datos.estado}</Badge>
        </p>
        <p>
          Importe: <span data-testid="importe-del-pago">{formatearImporte(parsearImporteDesdeApi(datos.importe))}</span>
        </p>
        {datos.observacion && <p>Observación: {datos.observacion}</p>}
        {datos.compra_id && (
          <p>
            <Link to={`/admin/compras/${datos.compra_id}`} className="text-primary/70 hover:text-primary hover:underline">
              Ver la compra
            </Link>
          </p>
        )}
        {deCompraVigente && datos.estado === 'CONFIRMADA' && (
          <p className="text-primary/70">Este pago se anula anulando la compra de contado a la que pertenece.</p>
        )}
      </Card>

      <Card className="flex flex-col gap-1 text-sm text-primary">
        <h2 className="text-base font-semibold">Medios de pago</h2>
        {datos.medios.map((medio) => (
          <p key={`${medio.medio_pago_id}-${medio.referencia ?? ''}-${medio.importe}`} data-testid="medio-del-pago">
            <span>{medio.medio_nombre ?? medio.medio_pago_id}</span>: {formatearImporte(parsearImporteDesdeApi(medio.importe))}
            {medio.referencia ? ` (ref. ${medio.referencia})` : ''}
          </p>
        ))}
      </Card>

      {datos.anulacion && (
        <Card className="flex flex-col gap-1 text-sm text-primary" data-testid="anulacion-del-pago">
          <h2 className="text-base font-semibold">Anulación</h2>
          <p>Motivo: {datos.anulacion.motivo_nombre ?? datos.anulacion.motivo_id}</p>
          <p>Usuario: {datos.anulacion.anulado_por_nombre}</p>
          <p>Anulado el {formatearFechaHora(datos.anulacion.anulado_en)}</p>
        </Card>
      )}

      <Link to="/admin/pagos-proveedores" className="text-sm text-primary/70 hover:text-primary hover:underline">
        Volver al listado
      </Link>
    </main>
  )
}

function AnularPago({ pago, alYaAnulado }: { pago: PagoDetalle; alYaAnulado: (mensaje: string) => void }) {
  const [abierto, setAbierto] = useState(false)
  return (
    <>
      <Boton variante="peligro" onClick={() => setAbierto(true)}>
        Anular pago
      </Boton>
      <Dialogo abierto={abierto} titulo="Anular pago" onCerrar={() => setAbierto(false)}>
        <FormularioDeAnulacion pago={pago} alCerrar={() => setAbierto(false)} alYaAnulado={alYaAnulado} />
      </Dialogo>
    </>
  )
}

/** Solo se monta con el diálogo abierto: no pide motivos ni saldo hasta que el usuario elige anular. */
function FormularioDeAnulacion({
  pago,
  alCerrar,
  alYaAnulado,
}: {
  pago: PagoDetalle
  alCerrar: () => void
  alYaAnulado: (mensaje: string) => void
}) {
  const [motivoId, setMotivoId] = useState('')
  const [error, setError] = useState<string | null>(null)
  const motivos = useMotivos(AMBITO_DE_ANULACION_DE_PAGO)
  const saldo = useSaldoDelProveedor(pago.proveedor_id)
  const anular = useAnularPago()
  const operationId = useOperationIdPorContenido({ pagoId: pago.pago_id, motivo_id: motivoId })

  const confirmar = async () => {
    setError(null)
    try {
      await anular.mutateAsync({ pagoId: pago.pago_id, motivo_id: motivoId, operationId })
      alCerrar()
    } catch (e) {
      if (e instanceof ErrorDePagos && e.codigo === 'PAGO_YA_ANULADO') {
        alCerrar()
        alYaAnulado(e.message)
      } else {
        setError(e instanceof ErrorDePagos ? e.message : 'No se pudo anular el pago. Revisá la conexión y reintentá: se reenvía la misma operación.')
      }
    }
  }

  return (
    <div className="flex flex-col gap-3">
      {error && <Alert>{error}</Alert>}
      <div className="flex flex-col gap-1">
        <label htmlFor="anulacion-motivo" className="text-sm font-medium text-primary">
          Motivo
        </label>
        <select id="anulacion-motivo" className={CLASE_CONTROL} value={motivoId} onChange={(e) => setMotivoId(e.target.value)}>
          <option value="">Elegí un motivo</option>
          {(motivos.data?.items ?? []).map((m) => (
            <option key={m.id} value={m.id}>
              {m.nombre}
            </option>
          ))}
        </select>
      </div>
      {saldo.isSuccess && (
        <p className="text-sm text-primary" data-testid="saldo-tras-anular">
          Saldo después de anular: {textoDeSaldoTrasAnular(saldo.data, pago.importe)}
        </p>
      )}
      <div className="flex gap-2">
        <Boton variante="peligro" disabled={motivoId === '' || anular.isPending} onClick={() => void confirmar()}>
          Confirmar anulación
        </Boton>
        <Boton variante="secundario" onClick={alCerrar}>
          Cancelar
        </Boton>
      </div>
    </div>
  )
}

export default PagoDetalleScreen
