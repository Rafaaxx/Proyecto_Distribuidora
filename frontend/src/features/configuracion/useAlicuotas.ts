import { useInfiniteQuery } from '@tanstack/react-query'

import { listarAlicuotas } from './api'
import { clavesConfiguracion } from './claves'

/**
 * Listado paginado de alícuotas (tarea 10.7, `design.md` D12).
 * `useInfiniteQuery` porque la API pagina por cursor igual que los
 * listados de catálogo (`useListados.ts`); el selector del formulario
 * (`ProductoFormScreen.tsx`) recorre todas las páginas.
 */
export function useAlicuotas() {
  return useInfiniteQuery({
    queryKey: clavesConfiguracion.alicuotas(),
    queryFn: ({ pageParam }: { pageParam: string | undefined }) => listarAlicuotas(pageParam),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (ultimaPagina) => ultimaPagina.cursor_siguiente ?? undefined,
  })
}
