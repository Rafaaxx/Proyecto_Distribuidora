import { useEffect } from 'react'

const SUFIJO = 'Distribuidora'

/**
 * Pone el título de la pestaña como «{titulo} · Distribuidora» mientras la pantalla está montada y
 * restaura el que había al desmontarse o al cambiar de título. Con `null` no toca nada: lo usa un
 * layout que no reconoce la sección activa para dejar que la pantalla hija fije el suyo.
 */
export function useTituloDePagina(titulo: string | null): void {
  useEffect(() => {
    if (titulo === null) return undefined
    const anterior = document.title
    document.title = `${titulo} · ${SUFIJO}`
    return () => {
      document.title = anterior
    }
  }, [titulo])
}
