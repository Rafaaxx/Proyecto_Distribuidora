import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { Alert } from '../../../components/ui/Alert'
import { Badge } from '../../../components/ui/Badge'
import { Boton } from '../../../components/ui/Button'
import { Card } from '../../../components/ui/Card'
import { Dialogo } from '../../../components/ui/Dialog'
import { PageHeader } from '../../../components/ui/PageHeader'
import { Tabla, type ColumnaTabla } from '../../../components/ui/Table'
import { avisoDeObservacion } from '../../../domain/compras/observaciones'
import { etiquetaIvaDescontado } from '../../../domain/proveedores/ivaDescontado'
import { formatearCantidad, referenciaDeRespuesta } from '../../../domain/stock/cantidades'
import type { CompraDetalle, CompraLinea } from '../../../features/compras/api'
import { ErrorDeCompras, PermisoRequeridoComprasError } from '../../../features/compras/errores'
import { useAnularCompra, useCompra, useMotivos } from '../../../features/compras/hooks'
import { useOperationIdPorContenido } from '../../../features/compras/useOperationIdPorContenido'
import { SiTienePermiso } from '../../../features/identidad/SiTienePermiso'
import { formatearFechaDeNegocio, formatearFechaHora } from '../../../lib/fecha'
import { formatearCosto, formatearImporte, parsearImporteDesdeApi } from '../../../lib/money'
import { ETIQUETA_DE_CONDICION, ETIQUETA_DE_ESTADO } from './etiquetas'

const SIN_PERMISO = 'No tenés permiso para ver las compras.'
const AMBITO_DE_ANULACION = 'ANULACION_COMPRA'
const CLASE_CONTROL = 'rounded-md border border-border px-2 py-1 text-sm'

function ComprasSinPermiso() {
  return (
    <main className="flex flex-col gap-4">
      <PageHeader titulo="Compra" />
      <p className="text-sm text-primary/70">{SIN_PERMISO}</p>
    </main>
  )
}

/**
 * Detalle de una compra y su anulación (change 11, tarea 12.3; spec
 * `administracion-de-compras`, `anulacion-de-compras`). Lo ve quien tiene
 * `REGISTRAR_COMPRA` o `ANULAR_COMPRA` (D14); "Anular" solo con `ANULAR_COMPRA` y sobre
 * una compra `CONFIRMADA`.
 */
export function CompraDetalleScreen() {
  return (
    <SiTienePermiso permiso={['REGISTRAR_COMPRA', 'ANULAR_COMPRA']} fallback={<ComprasSinPermiso />}>
      <DetalleDeCompra />
    </SiTienePermiso>
  )
}

function DetalleDeCompra() {
  const { compraId } = useParams<{ compraId: string }>()
  const compra = useCompra(compraId)
  const [avisos, setAvisos] = useState<string[]>([])

  if (compra.isPending) return <main><p>Cargando…</p></main>
  if (compra.isError) {
    if (compra.error instanceof PermisoRequeridoComprasError) return <ComprasSinPermiso />
    return (
      <main className="flex flex-col gap-4">
        <PageHeader titulo="Compra" />
        <Alert>
          {compra.error instanceof ErrorDeCompras && compra.error.codigo === 'RECURSO_NO_ENCONTRADO'
            ? 'No se encontró la compra.'
            : 'No se pudo obtener la compra.'}
        </Alert>
      </main>
    )
  }

  const datos = compra.data
  const columnas: ColumnaTabla<CompraLinea>[] = [
    { clave: 'producto', encabezado: 'Producto', render: (l) => l.producto_nombre ?? l.producto_id },
    { clave: 'presentacion', encabezado: 'Presentación', render: (l) => l.presentacion_nombre ?? l.presentacion_id },
    { clave: 'cantidad', encabezado: 'Cantidad', render: (l) => formatearCantidad(l.cantidad_base, referenciaDeRespuesta(l.unidades_referencia, l.nombre_referencia)) },
    { clave: 'costo', encabezado: 'Costo base', render: (l) => formatearCosto(parsearImporteDesdeApi(l.costo_base)) },
    // 11b (CST-06, TR-06): la regla congelada en la línea, no la condición actual.
    { clave: 'iva', encabezado: 'IVA', render: (l) => etiquetaIvaDescontado(l) },
    { clave: 'neto', encabezado: 'Importe neto', render: (l) => formatearImporte(parsearImporteDesdeApi(l.importe_neto)) },
  ]

  return (
    <main className="flex flex-col gap-4">
      <PageHeader
        titulo={`Compra del ${formatearFechaDeNegocio(datos.fecha)}`}
        acciones={
          datos.estado === 'CONFIRMADA' ? (
            <SiTienePermiso permiso="ANULAR_COMPRA">
              <AnularCompra compra={datos} alAnular={setAvisos} />
            </SiTienePermiso>
          ) : undefined
        }
      />

      {avisos.map((codigo) => (
        <p key={codigo} role="status" className="rounded-md border border-border bg-surface-muted px-3 py-2 text-sm text-primary">
          {avisoDeObservacion(codigo)}
        </p>
      ))}

      <Card className="flex flex-col gap-1 text-sm text-primary">
        <p>
          Proveedor: {datos.proveedor_nombre} · Condición: {ETIQUETA_DE_CONDICION[datos.condicion] ?? datos.condicion} ·{' '}
          <Badge variante={datos.estado === 'ANULADA' ? 'negativo' : 'positivo'}>{ETIQUETA_DE_ESTADO[datos.estado] ?? datos.estado}</Badge>
        </p>
        {datos.numero_comprobante && <p>Comprobante: {datos.numero_comprobante}</p>}
        {datos.observacion && <p>Observación: {datos.observacion}</p>}
        <p>
          Total neto: {formatearImporte(parsearImporteDesdeApi(datos.total_neto))} · Total de factura:{' '}
          {formatearImporte(parsearImporteDesdeApi(datos.total_factura))}
        </p>
      </Card>

      <Card>
        <Tabla filas={datos.lineas} columnas={columnas} obtenerClave={(l) => String(l.orden)} etiqueta="Líneas de la compra" />
      </Card>

      {datos.pago && (
        <Card className="flex flex-col gap-1 text-sm text-primary">
          <h2 className="text-base font-semibold">Pago de contado</h2>
          {datos.pago.medios.map((medio) => (
            <p key={`${medio.medio_pago_id}-${medio.referencia ?? ''}-${medio.importe}`}>
              <span>{medio.medio_nombre ?? medio.medio_pago_id}</span>: {formatearImporte(parsearImporteDesdeApi(medio.importe))}
              {medio.referencia ? ` (ref. ${medio.referencia})` : ''}
            </p>
          ))}
          {datos.pago.estado !== 'CONFIRMADO' && <p className="text-primary/70">Pago {datos.pago.estado.toLowerCase()}.</p>}
        </Card>
      )}

      {datos.anulacion && (
        <Card className="flex flex-col gap-1 text-sm text-primary">
          <h2 className="text-base font-semibold">Anulación</h2>
          <p>Motivo: {datos.anulacion.motivo_nombre ?? datos.anulacion.motivo_id}</p>
          <p>Anulada el {formatearFechaHora(datos.anulacion.anulada_en)}</p>
        </Card>
      )}

      <Link to="/admin/compras" className="text-sm text-primary/70 hover:text-primary hover:underline">
        Volver al listado
      </Link>
    </main>
  )
}

function AnularCompra({ compra, alAnular }: { compra: CompraDetalle; alAnular: (observaciones: string[]) => void }) {
  const [abierto, setAbierto] = useState(false)
  const [motivoId, setMotivoId] = useState('')
  const [devuelve, setDevuelve] = useState<boolean | null>(null)
  const [error, setError] = useState<string | null>(null)
  const motivos = useMotivos(AMBITO_DE_ANULACION)
  const anular = useAnularCompra()
  const deContado = compra.condicion === 'CONTADO'
  const contenido = { compraId: compra.id, motivo_id: motivoId, devuelve_pago: deContado ? devuelve : undefined }
  const operationId = useOperationIdPorContenido(contenido)
  const listo = motivoId !== '' && (!deContado || devuelve !== null)

  const confirmar = async () => {
    setError(null)
    try {
      const resultado = await anular.mutateAsync({
        compraId: compra.id,
        motivo_id: motivoId,
        ...(deContado && devuelve !== null ? { devuelve_pago: devuelve } : {}),
        operationId,
      })
      alAnular(resultado.observaciones)
      setAbierto(false)
    } catch (e) {
      setError(e instanceof ErrorDeCompras ? e.message : 'No se pudo anular la compra. Podés reintentar: se reenvía la misma operación.')
    }
  }

  return (
    <>
      <Boton variante="peligro" onClick={() => setAbierto(true)}>
        Anular compra
      </Boton>
      <Dialogo abierto={abierto} titulo="Anular compra" onCerrar={() => setAbierto(false)}>
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
          {deContado && (
            <fieldset className="flex flex-col gap-1 text-sm text-primary">
              <legend className="font-medium">Pago al proveedor</legend>
              <label className="flex items-center gap-2">
                <input type="radio" name="devuelve" checked={devuelve === true} onChange={() => setDevuelve(true)} />
                El proveedor devuelve el dinero
              </label>
              <label className="flex items-center gap-2">
                <input type="radio" name="devuelve" checked={devuelve === false} onChange={() => setDevuelve(false)} />
                El proveedor no devuelve el dinero
              </label>
            </fieldset>
          )}
          <div className="flex gap-2">
            <Boton variante="peligro" disabled={!listo || anular.isPending} onClick={() => void confirmar()}>
              Confirmar anulación
            </Boton>
            <Boton variante="secundario" onClick={() => setAbierto(false)}>
              Cancelar
            </Boton>
          </div>
        </div>
      </Dialogo>
    </>
  )
}

export default CompraDetalleScreen
