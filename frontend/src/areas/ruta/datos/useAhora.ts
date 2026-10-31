import { useEffect, useState } from 'react'

/**
 * El momento actual, renovado cada tanto: una pantalla abierta toma la versión de precios que
 * entra en vigencia sin recargar (PRC-20; `design.md` D6). El reloj es el del teléfono.
 */
export function useAhora(intervaloMs = 60_000): Date {
  const [ahora, setAhora] = useState(() => new Date())
  useEffect(() => {
    const temporizador = setInterval(() => setAhora(new Date()), intervaloMs)
    return () => clearInterval(temporizador)
  }, [intervaloMs])
  return ahora
}
