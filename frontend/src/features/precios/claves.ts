/**
 * Claves de consulta de TanStack Query para listas de precios (change 13, tarea 12.2).
 * Todo cuelga de `['precios', ...]`. Las de una lista cuelgan de `['precios', 'lista', id]`:
 * invalidar `borrador(id)` y `versiones(id)` (esta última arrastra los precios de cada
 * versión) es lo que hacen generar, fijar, publicar y anular. El listado y las opciones
 * tienen su propia raíz para que invalidarlos no toque las pantallas abiertas de una lista.
 */
export const clavesPrecios = {
  raiz: () => ['precios'] as const,
  listado: () => ['precios', 'listado'] as const,
  opciones: () => ['precios', 'opciones'] as const,
  predeterminada: () => ['precios', 'predeterminada'] as const,
  detalle: (listaId: string) => ['precios', 'lista', listaId] as const,
  reglas: (listaId: string) => ['precios', 'lista', listaId, 'reglas'] as const,
  borrador: (listaId: string) => ['precios', 'lista', listaId, 'borrador'] as const,
  versiones: (listaId: string) => ['precios', 'lista', listaId, 'versiones'] as const,
  preciosDeVersion: (listaId: string, versionId: string) =>
    ['precios', 'lista', listaId, 'versiones', versionId, 'precios'] as const,
}
