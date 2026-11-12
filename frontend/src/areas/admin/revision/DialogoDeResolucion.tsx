import { useState, type ReactNode } from 'react'

import { Alert } from '../../../components/ui/Alert'
import { Ayuda } from '../../../components/ui/Ayuda'
import { Boton } from '../../../components/ui/Button'
import { Dialogo } from '../../../components/ui/Dialog'
import { comentarioDeResolucion } from '../../../domain/revision/resolucion'
import { useOperationIdPorContenido } from '../../../features/compras/useOperationIdPorContenido'
import { ErrorDeRevision, mensajeDeErrorDeRevision } from '../../../features/revision/errores'

export const CLASE_CONTROL = 'rounded-md border border-border px-2 py-1 text-sm'

export interface DialogoDeResolucionProps {
  titulo: string
  /** La confirmación en palabras: «¿Resolver 2 avisos con este comentario? No se puede deshacer.» */
  confirmacion: string
  /** Lo que identifica el contenido a enviar: mientras no cambia, el reintento reenvía el mismo `Operation-Id`. */
  contenido: unknown
  /** Campos propios del diálogo (el vínculo de un rechazo), entre la confirmación y el comentario. */
  children?: ReactNode
  onCerrar: () => void
  /** Envía la resolución con el comentario ya validado y el `Operation-Id`; rechaza con el error de la API. */
  enviar: (comentario: string, operationId: string) => Promise<unknown>
  /** El servidor dijo que lo elegido ya estaba resuelto: la pantalla vuelve a leer la lista. */
  onDesactualizado: () => void
  /** Códigos de error que significan «ya lo resolvió otra persona». */
  codigosDeDesactualizado: readonly string[]
}

/**
 * Diálogo de resolución con comentario y confirmación (change 25, tareas 13.2 y 14.1; D1, D7, D12; SYN-08,
 * INV-06). El comentario se valida antes de enviar (1 a 500 caracteres, `COMENTARIO_INVALIDO`); el reintento tras
 * un fallo reenvía el mismo `Operation-Id`. Sin lógica de negocio: las reglas viven en `domain/revision/`.
 */
export function DialogoDeResolucion({
  titulo,
  confirmacion,
  contenido,
  children,
  onCerrar,
  enviar,
  onDesactualizado,
  codigosDeDesactualizado,
}: DialogoDeResolucionProps) {
  const [comentario, setComentario] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [enviando, setEnviando] = useState(false)
  const operationId = useOperationIdPorContenido({ contenido, comentario: comentario.trim() })

  const resolver = async () => {
    const valido = comentarioDeResolucion(comentario)
    if (valido === null) {
      setError(mensajeDeErrorDeRevision(new ErrorDeRevision('COMENTARIO_INVALIDO', '')))
      return
    }
    setError(null)
    setEnviando(true)
    try {
      await enviar(valido, operationId)
      onCerrar()
    } catch (falla) {
      setError(mensajeDeErrorDeRevision(falla))
      if (falla instanceof ErrorDeRevision && codigosDeDesactualizado.includes(falla.codigo)) onDesactualizado()
    } finally {
      setEnviando(false)
    }
  }

  return (
    <Dialogo abierto titulo={titulo} onCerrar={onCerrar}>
      <div className="flex flex-col gap-3">
        <div className="flex items-start gap-1">
          <p className="text-sm text-primary">{confirmacion}</p>
          <Ayuda clave="revision.resolver" />
        </div>
        {children}
        <div className="flex flex-col gap-1">
          <label htmlFor="resolucion-comentario" className="text-sm font-medium text-primary">
            Comentario
          </label>
          <textarea
            id="resolucion-comentario"
            rows={3}
            className={CLASE_CONTROL}
            value={comentario}
            onChange={(evento) => setComentario(evento.target.value)}
          />
        </div>
        {error && <Alert>{error}</Alert>}
        <div className="flex gap-2">
          <Boton disabled={enviando} onClick={() => void resolver()}>
            Resolver
          </Boton>
          <Boton variante="secundario" onClick={onCerrar}>
            Cancelar
          </Boton>
        </div>
      </div>
    </Dialogo>
  )
}
