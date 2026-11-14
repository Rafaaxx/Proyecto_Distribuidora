import { useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { cerrarSesionAdmin } from './cerrarSesion'

const RUTA_LOGIN = '/admin/login'
const MENSAJE_SIN_CONEXION = 'No se pudo cerrar la sesión: no hay conexión con el servidor. Probá de nuevo.'
const MENSAJE_ERROR = 'No se pudo cerrar la sesión. Probá de nuevo en unos minutos.'

/**
 * "Cerrar sesión" de `/admin`: revoca la sesión (`cerrarSesionAdmin`), lleva al login y vacía la
 * caché de TanStack Query para que no sobreviva ningún dato de la sesión anterior. Se navega
 * antes de vaciar la caché: así las pantallas que la observaban ya no están montadas.
 * `cerrando` evita que el cierre se dispare dos veces.
 */
export function useCerrarSesion() {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const [cerrando, setCerrando] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const cerrar = async () => {
    if (cerrando) return
    setCerrando(true)
    setError(null)
    const resultado = await cerrarSesionAdmin()
    if (resultado === 'cerrada') {
      navigate(RUTA_LOGIN, { replace: true })
      queryClient.clear()
      return
    }
    setError(resultado === 'sin_conexion' ? MENSAJE_SIN_CONEXION : MENSAJE_ERROR)
    setCerrando(false)
  }

  return { cerrar, cerrando, error }
}
