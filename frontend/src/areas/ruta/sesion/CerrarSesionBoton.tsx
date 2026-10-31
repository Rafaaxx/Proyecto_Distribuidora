import { useState } from 'react'

import { Alert } from '../../../components/ui/Alert'
import { Boton } from '../../../components/ui/Button'
import { Dialogo } from '../../../components/ui/Dialog'
import { useConectado } from '../../../lib/conexion'
import { cerrarSesionDelDispositivo } from '../../../sync/cierreDeSesion'

/**
 * "Cerrar sesión" de `/ruta` (change 21, D16): requiere conexión, pide confirmación y explica
 * qué se borra. Las operaciones pendientes no se pierden.
 */
export interface CerrarSesionBotonProps {
  onCerrada: () => void
}

export function CerrarSesionBoton({ onCerrada }: CerrarSesionBotonProps) {
  const conectado = useConectado()
  const [confirmando, setConfirmando] = useState(false)
  const [cerrando, setCerrando] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const confirmar = async () => {
    setCerrando(true)
    setError(null)
    const resultado = await cerrarSesionDelDispositivo()
    setCerrando(false)
    if (resultado === 'cerrada') {
      setConfirmando(false)
      onCerrada()
    } else if (resultado === 'sin_conexion') {
      setError('No se pudo cerrar la sesión: requiere conexión. Probá de nuevo cuando tengas señal.')
    } else {
      setError('No se pudo cerrar la sesión. Probá de nuevo en unos minutos.')
    }
  }

  return (
    <div className="flex flex-col gap-1">
      <Boton variante="secundario" disabled={!conectado} onClick={() => setConfirmando(true)}>
        Cerrar sesión
      </Boton>
      {!conectado && <p className="text-sm text-primary">Cerrar sesión requiere conexión.</p>}

      <Dialogo abierto={confirmando} titulo="Cerrar sesión" onCerrar={() => setConfirmando(false)}>
        <p className="mb-3 text-sm">
          Se borran tu sesión, tu PIN y los datos descargados de este teléfono. Lo que tengas
          pendiente de enviar no se pierde.
        </p>
        {error && <Alert className="mb-3">{error}</Alert>}
        <div className="flex justify-end gap-2">
          <Boton variante="secundario" onClick={() => setConfirmando(false)}>
            Cancelar
          </Boton>
          <Boton variante="peligro" disabled={cerrando} onClick={() => void confirmar()}>
            Confirmar
          </Boton>
        </div>
      </Dialogo>
    </div>
  )
}
