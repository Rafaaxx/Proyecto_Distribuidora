import { useState } from 'react'

import { Alert } from '../../../components/ui/Alert'
import { Badge } from '../../../components/ui/Badge'
import { Boton } from '../../../components/ui/Button'
import { Dialogo } from '../../../components/ui/Dialog'
import { PageHeader } from '../../../components/ui/PageHeader'
import { formatearCantidad, type ReferenciaDePresentacion } from '../../../domain/stock/cantidades'
import {
  ESTADO_ANULADA,
  esquemaAnulacion,
  etiquetaDeEstado,
  type SaldoDeLinea,
} from '../../../domain/stock/operaciones'
import { useOperationIdPorContenido } from '../../../features/compras/useOperationIdPorContenido'
import { ErrorDeStock, mensajeDeErrorDeStock } from '../../../features/stock/errores'
import { useMotivosDeStock, type AmbitoDeMotivoDeStock } from '../../../features/stock/hooks'

/** Piezas compartidas por las pantallas de transferencias y ajustes (change 14, grupo 13). */

const CODIGOS_DE_YA_ANULADA = ['TRANSFERENCIA_YA_ANULADA', 'AJUSTE_YA_ANULADO']

export const CLASE_CONTROL = 'rounded-md border border-border px-2 py-1 text-sm'
export const CLASE_ENLACE = 'text-sm text-primary/70 hover:text-primary hover:underline'
export const AVISO_REQUIERE_CONEXION =
  'Esta operación requiere conexión con el servidor y no se guarda para enviar después: si se corta la conexión, volvé a intentarlo.'

export function PantallaSinPermiso({ titulo, mensaje }: { titulo: string; mensaje: string }) {
  return (
    <main className="flex flex-col gap-4">
      <PageHeader titulo={titulo} />
      <p className="text-sm text-primary/70">{mensaje}</p>
    </main>
  )
}

/** Insignia de estado: Confirmada en positivo, Anulada en negativo. */
export function InsigniaDeEstado({ estado }: { estado: string }) {
  return <Badge variante={estado === ESTADO_ANULADA ? 'negativo' : 'positivo'}>{etiquetaDeEstado(estado)}</Badge>
}

/**
 * Saldo resultante de una línea en una ubicación, en cajas + unidades con signo (CAT-08). Un
 * resultado negativo se marca en rojo (D11): el servidor decide si lo admite (D1).
 */
export function SaldoResultante({
  ubicacion,
  saldo,
  referencia,
}: {
  ubicacion: string
  saldo: SaldoDeLinea
  referencia: ReferenciaDePresentacion | null
}) {
  const texto = `${ubicacion}: ${formatearCantidad(saldo.resultante, referencia)}`
  return (
    <div className="flex flex-col text-sm text-primary">
      <span className="text-xs text-primary/70">
        {`Saldo actual en ${ubicacion}: ${formatearCantidad(saldo.actual, referencia)}`}
      </span>
      <span data-negativo={saldo.negativo} className={saldo.negativo ? 'font-medium text-danger' : undefined}>
        {saldo.negativo ? `${texto} · stock negativo` : texto}
      </span>
    </div>
  )
}

export interface AnularOperacionDialogoProps {
  abierto: boolean
  titulo: string
  /** Identifica la operación: con otro `id` el `operation_id` es otro. */
  id: string
  ambito: AmbitoDeMotivoDeStock
  onCerrar: () => void
  /** Envía la anulación; el diálogo muestra el rechazo y se cierra si se acepta. */
  onConfirmar: (motivoId: string, operationId: string) => Promise<unknown>
  /** El servidor dijo que ya estaba anulada: el detalle se vuelve a leer. */
  onYaAnulada: () => void
}

/**
 * Diálogo de anulación de una transferencia o un ajuste (D5, D11): motivo obligatorio del
 * ámbito que corresponde, aviso de conexión sin cola, mismo `operation_id` en el reintento y
 * mensaje del servidor ante un rechazo. El formulario solo se monta con el diálogo abierto.
 */
export function AnularOperacionDialogo({ abierto, titulo, ...resto }: AnularOperacionDialogoProps) {
  return (
    <Dialogo abierto={abierto} titulo={titulo} onCerrar={resto.onCerrar}>
      <FormularioDeAnulacion {...resto} />
    </Dialogo>
  )
}

function FormularioDeAnulacion({
  id,
  ambito,
  onCerrar,
  onConfirmar,
  onYaAnulada,
}: Omit<AnularOperacionDialogoProps, 'abierto' | 'titulo'>) {
  const [motivoId, setMotivoId] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [enviando, setEnviando] = useState(false)
  const motivos = useMotivosDeStock(ambito)
  const operationId = useOperationIdPorContenido({ id, motivoId })

  const confirmar = async () => {
    const validado = esquemaAnulacion.safeParse({ motivoId })
    if (!validado.success) {
      setError(validado.error.issues[0]?.message ?? 'Elegí un motivo.')
      return
    }
    setError(null)
    setEnviando(true)
    try {
      await onConfirmar(validado.data.motivoId, operationId)
      onCerrar()
    } catch (falla) {
      setError(mensajeDeErrorDeStock(falla, 'anulacion'))
      if (falla instanceof ErrorDeStock && CODIGOS_DE_YA_ANULADA.includes(falla.codigo)) onYaAnulada()
    } finally {
      setEnviando(false)
    }
  }

  return (
    <div className="flex flex-col gap-3">
      <p className="text-sm text-primary/70">{AVISO_REQUIERE_CONEXION}</p>
      {error && <Alert>{error}</Alert>}
      <div className="flex flex-col gap-1">
        <label htmlFor="anulacion-motivo" className="text-sm font-medium text-primary">
          Motivo
        </label>
        <select
          id="anulacion-motivo"
          className={CLASE_CONTROL}
          value={motivoId}
          onChange={(evento) => setMotivoId(evento.target.value)}
        >
          <option value="">Elegí un motivo</option>
          {(motivos.data?.items ?? []).map((motivo) => (
            <option key={motivo.id} value={motivo.id}>
              {motivo.nombre}
            </option>
          ))}
        </select>
      </div>
      <div className="flex gap-2">
        <Boton variante="peligro" disabled={motivoId === '' || enviando} onClick={() => void confirmar()}>
          Confirmar anulación
        </Boton>
        <Boton variante="secundario" onClick={onCerrar}>
          Cancelar
        </Boton>
      </div>
    </div>
  )
}
