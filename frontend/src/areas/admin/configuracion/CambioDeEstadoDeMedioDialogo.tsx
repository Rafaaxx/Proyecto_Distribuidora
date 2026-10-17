import { useState } from 'react'

import { Alert } from '../../../components/ui/Alert'
import { Boton } from '../../../components/ui/Button'
import { Dialogo } from '../../../components/ui/Dialog'
import type { MedioPagoAdmin } from '../../../features/configuracion/api'
import { useModificarMedioPago } from '../../../features/configuracion/useMediosPagoAdmin'
import { useOperationIdDeEnvio } from '../../../features/precios/useOperationIdDeEnvio'
import { AVISO_SIN_CONEXION, describirErrorDeMedio, estaSinConexion } from './erroresDeMedios'

interface CambioDeEstadoDeMedioDialogoProps {
  medio: MedioPagoAdmin
  /** `true` reactiva un medio de baja; `false` lo da de baja. */
  reactivar: boolean
  onCerrar: () => void
}

/**
 * Confirmación de la baja o la reactivación de un medio (change 17b, tarea 8.1; D4; CAT-05). Nada
 * se envía antes de confirmar. Es un reemplazo completo con `activo` distinto; el servidor rechaza
 * con `ULTIMO_MEDIO_ACTIVO` si no quedaría ninguno activo. Mismo `Operation-Id` al reintentar.
 */
export function CambioDeEstadoDeMedioDialogo({ medio, reactivar, onCerrar }: CambioDeEstadoDeMedioDialogoProps) {
  const modificar = useModificarMedioPago()
  const [error, setError] = useState<string | null>(null)
  const operationId = useOperationIdDeEnvio({ id: medio.id, activo: reactivar })
  const titulo = `${reactivar ? 'Reactivar' : 'Dar de baja'} ${medio.nombre}`

  const confirmar = async () => {
    if (estaSinConexion()) {
      setError(AVISO_SIN_CONEXION)
      return
    }
    try {
      await modificar.mutateAsync({
        medioPagoId: medio.id,
        nombre: medio.nombre,
        requiere_referencia: medio.requiere_referencia,
        activo: reactivar,
        operationId: operationId.obtener(),
      })
      operationId.completar()
      onCerrar()
    } catch (falla) {
      setError(describirErrorDeMedio(falla))
    }
  }

  return (
    <Dialogo abierto titulo={titulo} onCerrar={onCerrar}>
      <div className="flex flex-col gap-4">
        <p className="text-sm text-primary">
          {reactivar
            ? `«${medio.nombre}» vuelve a ofrecerse en los cobros y pagos nuevos.`
            : `«${medio.nombre}» deja de ofrecerse en los cobros y pagos nuevos. No se borra: los de antes lo siguen mostrando y lo podés reactivar cuando quieras.`}
        </p>
        {error && <Alert>{error}</Alert>}
        <div className="flex gap-2">
          <Boton type="button" disabled={modificar.isPending} onClick={() => void confirmar()}>
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
