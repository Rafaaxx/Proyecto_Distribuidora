import { useEffect } from 'react'

interface ConsultaPaginada {
  hasNextPage: boolean
  isFetching: boolean
  fetchNextPage: () => Promise<unknown>
  data: { pages: readonly unknown[] } | undefined
}

/**
 * Sigue pidiendo páginas de una consulta paginada por cursor hasta tenerlas todas: los
 * selectores de alcance de las reglas necesitan la lista completa, no la primera página (mismo
 * criterio que `useProductosDelProveedor`).
 */
export function useCargaCompleta(consulta: ConsultaPaginada): void {
  const { hasNextPage, isFetching, fetchNextPage } = consulta
  // Páginas ya cargadas: entra en las dependencias para que el efecto vuelva a correr tras
  // cada página aunque `hasNextPage` e `isFetching` terminen en el mismo valor.
  const paginasCargadas = consulta.data?.pages.length ?? 0
  useEffect(() => {
    if (hasNextPage && !isFetching) void fetchNextPage()
  }, [hasNextPage, isFetching, fetchNextPage, paginasCargadas])
}
