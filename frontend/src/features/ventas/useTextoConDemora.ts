import { useEffect, useState } from 'react'

/**
 * El valor de `texto` una vez que dejó de cambiar durante `demoraMs`: el buscador de productos
 * pide al servidor cuando el usuario termina de tipear, no con cada tecla (D19, 2026-10-20).
 */
export function useTextoConDemora(texto: string, demoraMs = 300): string {
  const [demorado, setDemorado] = useState(texto)
  useEffect(() => {
    const temporizador = setTimeout(() => setDemorado(texto), demoraMs)
    return () => clearTimeout(temporizador)
  }, [texto, demoraMs])
  return demorado
}
