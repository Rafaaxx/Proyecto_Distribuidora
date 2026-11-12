import { useState } from 'react'

import { Alert } from '../../../components/ui/Alert'
import { Boton } from '../../../components/ui/Button'
import { Dialogo } from '../../../components/ui/Dialog'
import { useOperationIdDeEnvio } from '../../../features/precios/useOperationIdDeEnvio'
import { AVISO_SIN_CONEXION, estaSinConexion } from './erroresDeCatalogos'

interface CambioDeEstadoDeCatalogoDialogoProps {
  /** Id de lo que cambia de estado: ata el `Operation-Id` a esta operación. */
  id: string
  titulo: string
  /** Explicación de lo que pasa al confirmar. */
  mensaje: string
  /** `true` reactiva; `false` da de baja. */
  reactivar: boolean
  /** Envía el cambio con el `Operation-Id` recibido; rechaza con el error de la mutación. */
  onConfirmar: (operationId: string) => Promise<unknown>
  /** Traduce el rechazo a palabras simples. */
  describirError: (error: unknown) => string
  onCerrar: () => void
}

/**
 * Confirmación de la baja o la reactivación de un motivo o una alícuota (change 20c, D4, D8;
 * CAT-05). Nada se envía antes de confirmar; el servidor decide los rechazos (`ULTIMO_MOTIVO_ACTIVO`,
 * `ALICUOTA_EN_USO`, `ULTIMA_ALICUOTA_ACTIVA`). Mismo `Operation-Id` al reintentar (INV-06).
 */
export function CambioDeEstadoDeCatalogoDialogo({
  id,
  titulo,
  mensaje,
  reactivar,
  onConfirmar,
  describirError,
  onCerrar,
}: CambioDeEstadoDeCatalogoDialogoProps) {
  const [error, setError] = useState<string | null>(null)
  const [enCurso, setEnCurso] = useState(false)
  const operationId = useOperationIdDeEnvio({ id, activo: reactivar })

  const confirmar = async () => {
    if (estaSinConexion()) {
      setError(AVISO_SIN_CONEXION)
      return
    }
    setEnCurso(true)
    try {
      await onConfirmar(operationId.obtener())
      operationId.completar()
      onCerrar()
    } catch (falla) {
      setError(describirError(falla))
      setEnCurso(false)
    }
  }

  return (
    <Dialogo abierto titulo={titulo} onCerrar={onCerrar}>
      <div className="flex flex-col gap-4">
        <p className="text-sm text-primary">{mensaje}</p>
        {error && <Alert>{error}</Alert>}
        <div className="flex gap-2">
          <Boton type="button" disabled={enCurso} onClick={() => void confirmar()}>
            {reactivar ? 'Confirmar reactivación' : 'Confirmar baja'}
          </Boton>
          <Boton variante="secundario" onClick={onCerrar}>
            Cancelar
          </Boton>
        </div>
      </div>
    </Dialogo>
  )
}
