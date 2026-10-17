import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { Alert } from '../../../components/ui/Alert'
import { Ayuda } from '../../../components/ui/Ayuda'
import { Badge } from '../../../components/ui/Badge'
import { Boton } from '../../../components/ui/Button'
import { Card } from '../../../components/ui/Card'
import { Dialogo } from '../../../components/ui/Dialog'
import { PageHeader } from '../../../components/ui/PageHeader'
import {
  AMBITO_DE_ANULACION_DE_COBRANZA,
  ETIQUETA_DE_ESTADO_DE_COBRANZA,
  detalleDeObservacion,
  etiquetaDeObservacion,
  etiquetaDeOrigenDeCobranza,
  observacionesDeLinea,
  observacionesGenerales,
  puedeAnularse,
  textoDeSaldoTrasAnular,
  type ObservacionDeCobranza,
} from '../../../domain/cobranzas/presentacion'
import type { CobranzaDetalle } from '../../../features/cobranzas/api'
import { ErrorDeCobranzas, PermisoRequeridoCobranzasError } from '../../../features/cobranzas/errores'
import { useAnularCobranza, useCobranza, useSaldoDelCliente } from '../../../features/cobranzas/hooks'
import { useMotivos } from '../../../features/compras/hooks'
import { useOperationIdPorContenido } from '../../../features/compras/useOperationIdPorContenido'
import { SiTienePermiso } from '../../../features/identidad/SiTienePermiso'
import { formatearFechaHora } from '../../../lib/fecha'
import { formatearImporte, parsearImporteDesdeApi } from '../../../lib/money'
import { CobranzasSinPermiso } from './CobranzasSinPermiso'

const CLASE_CONTROL = 'rounded-md border border-border px-2 py-1 text-sm'
const TITULO = 'Cobranza'

/**
 * Detalle de una cobranza y su anulación (change 17, tareas 14.1 y 14.3; spec
 * `administracion-de-cobranzas`, `anulacion-de-cobranzas`). Lo ve quien tiene
 * `REGISTRAR_COBRANZA` o `ANULAR_COBRANZA` (D14); "Anular cobranza" solo con `ANULAR_COBRANZA`,
 * sobre una cobranza `CONFIRMADA` de origen `INDEPENDIENTE` (D7). Esa regla es `puedeAnularse`,
 * del dominio. Las observaciones de medio (`MEDIO_INACTIVO`, `REFERENCIA_FALTANTE`) se muestran
 * junto a su línea (D13).
 */
export function CobranzaDetalleScreen() {
  return (
    <SiTienePermiso permiso={['REGISTRAR_COBRANZA', 'ANULAR_COBRANZA']} fallback={<CobranzasSinPermiso titulo={TITULO} />}>
      <DetalleDeCobranza />
    </SiTienePermiso>
  )
}

function DetalleDeCobranza() {
  const { cobranzaId } = useParams<{ cobranzaId: string }>()
  const cobranza = useCobranza(cobranzaId)
  const [rechazo, setRechazo] = useState<string | null>(null)

  if (cobranza.isPending) {
    return (
      <main>
        <p>Cargando…</p>
      </main>
    )
  }
  if (cobranza.isError) {
    if (cobranza.error instanceof PermisoRequeridoCobranzasError) return <CobranzasSinPermiso titulo={TITULO} />
    return (
      <main className="flex flex-col gap-4">
        <PageHeader titulo={TITULO} />
        <Alert>
          {cobranza.error instanceof ErrorDeCobranzas && cobranza.error.codigo === 'RECURSO_NO_ENCONTRADO'
            ? 'No se encontró la cobranza.'
            : 'No se pudo obtener la cobranza.'}
        </Alert>
      </main>
    )
  }

  const datos = cobranza.data

  return (
    <main className="flex flex-col gap-4">
      <PageHeader
        titulo={`Cobranza del ${formatearFechaHora(datos.occurred_at)}`}
        acciones={
          puedeAnularse(datos) ? (
            <SiTienePermiso permiso="ANULAR_COBRANZA">
              <AnularCobranza
                cobranza={datos}
                alYaAnulada={(mensaje) => {
                  setRechazo(mensaje)
                  void cobranza.refetch()
                }}
              />
            </SiTienePermiso>
          ) : undefined
        }
      />

      {rechazo && <Alert>{rechazo}</Alert>}

      <Card className="flex flex-col gap-1 text-sm text-primary">
        <p>
          Cliente: {datos.cliente_nombre ?? datos.cliente_id} · Origen: {etiquetaDeOrigenDeCobranza(datos.origen)} ·{' '}
          <Badge variante={datos.estado === 'ANULADA' ? 'negativo' : 'positivo'}>
            {ETIQUETA_DE_ESTADO_DE_COBRANZA[datos.estado] ?? datos.estado}
          </Badge>
        </p>
        <p>
          Importe: <span data-testid="importe-de-la-cobranza">{formatearImporte(parsearImporteDesdeApi(datos.importe))}</span>
        </p>
        <p>Registrada por: {datos.usuario_nombre ?? datos.usuario_id}</p>
        <div className="flex items-center gap-1">
          {datos.jornada_id ? (
            <p>
              Jornada:{' '}
              <Link to={`/admin/cobranzas?jornada=${datos.jornada_id}`} className="text-primary/70 hover:text-primary hover:underline">
                Ver las cobranzas de esta jornada
              </Link>
            </p>
          ) : (
            <p>Jornada: sin jornada</p>
          )}
          <Ayuda clave="cobranzas.jornada" />
        </div>
        {datos.observacion && <p>Observación: {datos.observacion}</p>}
      </Card>

      <Card className="flex flex-col gap-2 text-sm text-primary">
        <h2 className="text-base font-semibold">Medios de pago</h2>
        {datos.medios.map((medio, indice) => (
          <div key={`${medio.medio_pago_id}-${String(indice)}`} data-testid="medio-de-la-cobranza" className="flex flex-col gap-1">
            <p>
              {medio.medio_nombre ?? medio.medio_pago_id}: {formatearImporte(parsearImporteDesdeApi(medio.importe))}
              {medio.referencia ? ` (ref. ${medio.referencia})` : ''}
            </p>
            {observacionesDeLinea(datos.observaciones, indice).map((observacion) => (
              <AvisoDeObservacion key={observacion.codigo} observacion={observacion} />
            ))}
          </div>
        ))}
      </Card>

      <Observaciones observaciones={observacionesGenerales(datos.observaciones)} hayObservaciones={datos.observaciones.length > 0} />

      {datos.anulacion && (
        <Card className="flex flex-col gap-1 text-sm text-primary" data-testid="anulacion-de-la-cobranza">
          <h2 className="text-base font-semibold">Anulación</h2>
          <p>Motivo: {datos.anulacion.motivo_nombre ?? datos.anulacion.motivo_id}</p>
          {datos.anulacion.observacion && <p>Observación: {datos.anulacion.observacion}</p>}
          <p>Usuario: {datos.anulacion.usuario_nombre ?? datos.anulacion.usuario_id}</p>
          <p>Anulada el {formatearFechaHora(datos.anulacion.anulada_en)}</p>
        </Card>
      )}

      <Link to="/admin/cobranzas" className="text-sm text-primary/70 hover:text-primary hover:underline">
        Volver al listado
      </Link>
    </main>
  )
}

function AvisoDeObservacion({ observacion }: { observacion: ObservacionDeCobranza }) {
  const detalle = detalleDeObservacion(observacion)
  return (
    <p className="flex flex-wrap items-center gap-2">
      <Badge variante="negativo">{etiquetaDeObservacion(observacion.codigo)}</Badge>
      {detalle && <span className="text-primary/70">{detalle}</span>}
    </p>
  )
}

/** Observaciones de sincronización que no son de una línea; las de línea van junto a su medio. */
function Observaciones({
  observaciones,
  hayObservaciones,
}: {
  observaciones: ObservacionDeCobranza[]
  hayObservaciones: boolean
}) {
  if (!hayObservaciones) return null
  return (
    <Card className="flex flex-col gap-2 text-sm text-primary" data-testid="observaciones-de-sincronizacion">
      <div className="flex items-center gap-1">
        <h2 className="text-base font-semibold">Observaciones de sincronización</h2>
        <Ayuda clave="cobranzas.observaciones" />
      </div>
      {observaciones.length === 0 ? (
        <p className="text-primary/70">Los avisos de esta cobranza están junto a su medio de pago.</p>
      ) : (
        observaciones.map((observacion) => <AvisoDeObservacion key={observacion.codigo} observacion={observacion} />)
      )}
    </Card>
  )
}

function AnularCobranza({ cobranza, alYaAnulada }: { cobranza: CobranzaDetalle; alYaAnulada: (mensaje: string) => void }) {
  const [abierto, setAbierto] = useState(false)
  return (
    <>
      <span className="flex items-center gap-1">
        <Boton variante="peligro" onClick={() => setAbierto(true)}>
          Anular cobranza
        </Boton>
        <Ayuda clave="cobranzas.anulacion" />
      </span>
      <Dialogo abierto={abierto} titulo="Anular cobranza" onCerrar={() => setAbierto(false)}>
        <FormularioDeAnulacion cobranza={cobranza} alCerrar={() => setAbierto(false)} alYaAnulada={alYaAnulada} />
      </Dialogo>
    </>
  )
}

/** Solo se monta con el diálogo abierto: no pide motivos ni saldo hasta que el usuario elige anular. */
function FormularioDeAnulacion({
  cobranza,
  alCerrar,
  alYaAnulada,
}: {
  cobranza: CobranzaDetalle
  alCerrar: () => void
  alYaAnulada: (mensaje: string) => void
}) {
  const [motivoId, setMotivoId] = useState('')
  const [observacion, setObservacion] = useState('')
  const [error, setError] = useState<string | null>(null)
  const motivos = useMotivos(AMBITO_DE_ANULACION_DE_COBRANZA)
  const saldo = useSaldoDelCliente(cobranza.cliente_id)
  const anular = useAnularCobranza()
  const textoDeObservacion = observacion.trim() === '' ? null : observacion.trim()
  const operationId = useOperationIdPorContenido({ cobranzaId: cobranza.cobranza_id, motivo_id: motivoId, observacion: textoDeObservacion })

  const confirmar = async () => {
    setError(null)
    try {
      await anular.mutateAsync({ cobranzaId: cobranza.cobranza_id, motivo_id: motivoId, observacion: textoDeObservacion, operationId })
      alCerrar()
    } catch (e) {
      if (e instanceof ErrorDeCobranzas && e.codigo === 'COBRANZA_YA_ANULADA') {
        alCerrar()
        alYaAnulada(e.message)
      } else {
        setError(
          e instanceof ErrorDeCobranzas
            ? e.message
            : 'No se pudo anular la cobranza. Revisá la conexión y reintentá: se reenvía la misma operación.',
        )
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
      <div className="flex flex-col gap-1">
        <label htmlFor="anulacion-observacion" className="text-sm font-medium text-primary">
          Observación (opcional)
        </label>
        <input
          id="anulacion-observacion"
          className={CLASE_CONTROL}
          maxLength={500}
          value={observacion}
          onChange={(e) => setObservacion(e.target.value)}
        />
      </div>
      {saldo.isSuccess && (
        <p className="text-sm text-primary" data-testid="saldo-tras-anular">
          Saldo después de anular: {textoDeSaldoTrasAnular(saldo.data, cobranza.importe)}
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

export default CobranzaDetalleScreen
