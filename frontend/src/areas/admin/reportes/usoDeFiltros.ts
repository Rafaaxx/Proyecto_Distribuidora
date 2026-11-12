import { useEffect, useState } from 'react'

import { irALaPagina, volverALaPrimera } from '../../../domain/reportes/paginacion'

/** Hooks de las pantallas de reportes que filtran (change 26, D11). */

/**
 * Los vendedores que aparecieron en algún reporte: con un vendedor elegido el desglose trae solo a ése, y las
 * demás opciones tienen que seguir disponibles. Se actualiza al cambiar el reporte, durante el render.
 */
export function useVendedoresVistos<T>(
  datos: T | undefined,
  extraer: (datos: T) => readonly { id: string; nombre: string }[],
): ReadonlyMap<string, string> {
  const [vistos, setVistos] = useState<{ datos: T | undefined; vendedores: ReadonlyMap<string, string> }>({
    datos: undefined,
    vendedores: new Map(),
  })
  if (datos !== undefined && datos !== vistos.datos) {
    const nuevos = new Map(vistos.vendedores)
    for (const { id, nombre } of extraer(datos)) nuevos.set(id, nombre)
    setVistos({ datos, vendedores: nuevos })
    return nuevos
  }
  return vistos.vendedores
}

/**
 * La página de cada lista paginada de una pestaña (D14). `clave` resume los filtros: cuando cambia (período,
 * vendedor, estado, saldo o búsqueda) todas las listas vuelven a la página 1; cambiar de página en una lista no
 * mueve las otras. La reposición se hace durante el render, sin pedir una página vieja con filtros nuevos.
 */
export function usePaginas<T extends Record<keyof T, number>>(
  clave: string,
  primeras: T,
): readonly [T, (lista: keyof T, pagina: number) => void] {
  const [estado, setEstado] = useState({ clave, paginas: primeras })
  const cambiar = (lista: keyof T, pagina: number) =>
    setEstado((actual) => ({ ...actual, paginas: irALaPagina(actual.paginas, lista, pagina) }))
  if (estado.clave !== clave) {
    const reiniciado = { clave, paginas: volverALaPrimera(estado.paginas) }
    setEstado(reiniciado)
    return [reiniciado.paginas, cambiar]
  }
  return [estado.paginas, cambiar]
}

/** El valor de un campo de búsqueda, demorado para no pedir el reporte en cada tecla. */
export function useTextoConRetraso(texto: string, milisegundos = 300): string {
  const [demorado, setDemorado] = useState(texto)
  useEffect(() => {
    const temporizador = setTimeout(() => setDemorado(texto), milisegundos)
    return () => clearTimeout(temporizador)
  }, [texto, milisegundos])
  return demorado
}
