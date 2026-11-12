/**
 * Paginación de las listas de los reportes (change 26, D14; spec `reportes/area-de-reportes`). Lógica pura, sin
 * React: la pantalla solo dibuja lo que esta función dice. El orden, los totales y la cantidad de páginas los
 * manda el servidor; acá no se reordena ni se calcula nada de las filas.
 */

/** Dónde está una página dentro de su lista, tal como viene en el sobre del servidor. */
export interface UbicacionDePagina {
  pagina: number
  paginas: number
}

export interface Navegacion {
  /** No se muestra con una sola página o sin filas. */
  visible: boolean
  anteriorHabilitado: boolean
  siguienteHabilitado: boolean
  /** «Página {n} de {m}» (texto aprobado el 2026-11-07). */
  texto: string
}

export function navegacionDe({ pagina, paginas }: UbicacionDePagina): Navegacion {
  return {
    visible: paginas > 1,
    anteriorHabilitado: pagina > 1,
    siguienteHabilitado: pagina < paginas,
    texto: `Página ${String(pagina)} de ${String(paginas)}`,
  }
}

/** La página de cada lista paginada del reporte de ventas; cada una se mueve por su lado. */
export interface PaginasDeVentas {
  porDia: number
  porProducto: number
  anuladas: number
}

export const PRIMERAS_PAGINAS_DE_VENTAS: PaginasDeVentas = { porDia: 1, porProducto: 1, anuladas: 1 }

/** Cambia la página de una lista sin mover las otras. */
export function irALaPagina<T extends Record<keyof T, number>>(paginas: T, lista: keyof T, pagina: number): T {
  return { ...paginas, [lista]: pagina }
}

/** Cambiar el período, el vendedor u otro filtro vuelve todas las listas a la página 1. */
export function volverALaPrimera<T extends Record<keyof T, number>>(paginas: T): T {
  const primeras = { ...paginas }
  for (const lista of Object.keys(primeras) as (keyof T)[]) primeras[lista] = 1 as T[keyof T]
  return primeras
}
