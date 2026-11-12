import { useEffect, useState } from 'react'

/**
 * Estado de la conexión del dispositivo (`navigator.onLine` y los eventos `online`/`offline`).
 * Es una señal del navegador, no una garantía de que el servidor responda: quien pide algo
 * igual debe manejar el corte de red.
 */
export function useConectado(): boolean {
  const [conectado, setConectado] = useState(() => navigator.onLine)

  useEffect(() => {
    const alCambiar = () => setConectado(navigator.onLine)
    window.addEventListener('online', alCambiar)
    window.addEventListener('offline', alCambiar)
    alCambiar()
    return () => {
      window.removeEventListener('online', alCambiar)
      window.removeEventListener('offline', alCambiar)
    }
  }, [])

  return conectado
}
