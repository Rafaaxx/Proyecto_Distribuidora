import { useState } from 'react'

import { Alert } from '../../../components/ui/Alert'
import { Badge } from '../../../components/ui/Badge'
import { Boton } from '../../../components/ui/Button'
import { Dialogo } from '../../../components/ui/Dialog'
import {
  AMBITO_DE_LIBERACION,
  esquemaLiberacion,
  etiquetaDeEstadoDeJornada,
  textoDeToma,
} from '../../../domain/stock/jornadas'
import { useOperationIdPorContenido } from '../../../features/compras/useOperationIdPorContenido'
import type { TomaDeUbicacion } from '../../../features/stock/api'
import { mensajeDeErrorDeStock } from '../../../features/stock/errores'
import { useMotivosDeStock } from '../../../features/stock/hooks'
import { AVISO_REQUIERE_CONEXION, CLASE_CONTROL } from './piezasDeOperacion'

/** Piezas compartidas por las pantallas de jornadas y la marca de toma (change 15, grupo 14). */

const CODIGO_DE_ESTADO_INVALIDO = 'JORNADA_ESTADO_INVALIDO'

/** Insignia del estado de una jornada: las que siguen en curso en positivo, las terminadas en neutro. */
export function InsigniaDeEstadoDeJornada({ estado }: { estado: string }) {
  const enCurso = estado === 'ABIERTA' || estado === 'EN_RENDICION'
  return <Badge variante={enCurso ? 'positivo' : 'neutral'}>{etiquetaDeEstadoDeJornada(estado)}</Badge>
}

/** "Tomada por Juan desde 10/04/2026 08:00" (STK-09); sin jornada no muestra nada. */
export function MarcaDeToma({ toma }: { toma: TomaDeUbicacion | null | undefined }) {
  if (!toma) return null
  return (
    <Badge variante="negativo" data-testid="marca-de-toma">
      {textoDeToma(toma)}
    </Badge>
  )
}

export interface ConfirmarTransicionDialogoProps {
  abierto: boolean
  titulo: string
  texto: string
  /** Identifica la jornada y la acción: con otra acción el `operation_id` es otro. */
  id: string
  accion: string
  onCerrar: () => void
  /** Envía la transición; el diálogo muestra el rechazo y se cierra si se acepta. */
  onConfirmar: (operationId: string) => Promise<unknown>
  /** El servidor dijo que la jornada ya no está en ese estado: el detalle se vuelve a leer. */
  onEstadoInvalido: () => void
}

/** Confirmación de "Rendir" y "Cerrar": aviso de conexión sin cola y mismo `operation_id` al reintentar. */
export function ConfirmarTransicionDialogo({ abierto, titulo, ...resto }: ConfirmarTransicionDialogoProps) {
  return (
    <Dialogo abierto={abierto} titulo={titulo} onCerrar={resto.onCerrar}>
      <FormularioDeConfirmacion {...resto} />
    </Dialogo>
  )
}

function FormularioDeConfirmacion({
  texto,
  id,
  accion,
  onCerrar,
  onConfirmar,
  onEstadoInvalido,
}: Omit<ConfirmarTransicionDialogoProps, 'abierto' | 'titulo'>) {
  const [error, setError] = useState<string | null>(null)
  const [enviando, setEnviando] = useState(false)
  const operationId = useOperationIdPorContenido({ id, accion })

  const confirmar = async () => {
    setError(null)
    setEnviando(true)
    try {
      await onConfirmar(operationId)
      onCerrar()
    } catch (falla) {
      setError(mensajeDeErrorDeStock(falla, 'jornada'))
      if (esDeEstadoInvalido(falla)) onEstadoInvalido()
    } finally {
      setEnviando(false)
    }
  }

  return (
    <div className="flex flex-col gap-3">
      <p className="text-sm text-primary">{texto}</p>
      <p className="text-sm text-primary/70">{AVISO_REQUIERE_CONEXION}</p>
      {error && <Alert>{error}</Alert>}
      <div className="flex gap-2">
        <Boton disabled={enviando} onClick={() => void confirmar()}>
          Confirmar
        </Boton>
        <Boton variante="secundario" onClick={onCerrar}>
          Cancelar
        </Boton>
      </div>
    </div>
  )
}

function esDeEstadoInvalido(falla: unknown): boolean {
  return typeof falla === 'object' && falla !== null && (falla as { codigo?: unknown }).codigo === CODIGO_DE_ESTADO_INVALIDO
}

export interface LiberarJornadaDialogoProps {
  abierto: boolean
  id: string
  onCerrar: () => void
  onConfirmar: (motivoId: string, observacion: string | undefined, operationId: string) => Promise<unknown>
  onEstadoInvalido: () => void
}

/** "Liberar": motivo obligatorio del ámbito `LIBERACION_JORNADA` y observación opcional (RUT-09, D13). */
export function LiberarJornadaDialogo({ abierto, ...resto }: LiberarJornadaDialogoProps) {
  return (
    <Dialogo abierto={abierto} titulo="Liberar jornada" onCerrar={resto.onCerrar}>
      <FormularioDeLiberacion {...resto} />
    </Dialogo>
  )
}

function FormularioDeLiberacion({
  id,
  onCerrar,
  onConfirmar,
  onEstadoInvalido,
}: Omit<LiberarJornadaDialogoProps, 'abierto'>) {
  const [motivoId, setMotivoId] = useState('')
  const [observacion, setObservacion] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [enviando, setEnviando] = useState(false)
  const motivos = useMotivosDeStock(AMBITO_DE_LIBERACION)
  const operationId = useOperationIdPorContenido({ id, motivoId, observacion })

  const confirmar = async () => {
    const validado = esquemaLiberacion.safeParse({ motivo_id: motivoId, observacion })
    if (!validado.success) {
      setError(validado.error.issues[0]?.message ?? 'Revisá los datos de la liberación.')
      return
    }
    setError(null)
    setEnviando(true)
    try {
      const texto = validado.data.observacion.trim()
      await onConfirmar(validado.data.motivo_id, texto === '' ? undefined : texto, operationId)
      onCerrar()
    } catch (falla) {
      setError(mensajeDeErrorDeStock(falla, 'jornada'))
      if (esDeEstadoInvalido(falla)) onEstadoInvalido()
    } finally {
      setEnviando(false)
    }
  }

  return (
    <div className="flex flex-col gap-3">
      <p className="text-sm text-primary/70">{AVISO_REQUIERE_CONEXION}</p>
      {error && <Alert>{error}</Alert>}
      <div className="flex flex-col gap-1">
        <label htmlFor="liberacion-motivo" className="text-sm font-medium text-primary">
          Motivo
        </label>
        <select
          id="liberacion-motivo"
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
      <div className="flex flex-col gap-1">
        <label htmlFor="liberacion-observacion" className="text-sm font-medium text-primary">
          Observación
        </label>
        <textarea
          id="liberacion-observacion"
          rows={3}
          className={CLASE_CONTROL}
          value={observacion}
          onChange={(evento) => setObservacion(evento.target.value)}
        />
      </div>
      <div className="flex gap-2">
        <Boton variante="peligro" disabled={enviando} onClick={() => void confirmar()}>
          Confirmar liberación
        </Boton>
        <Boton variante="secundario" onClick={onCerrar}>
          Cancelar
        </Boton>
      </div>
    </div>
  )
}
