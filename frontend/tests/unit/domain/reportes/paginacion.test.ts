import { describe, expect, it } from 'vitest'

import {
  irALaPagina,
  navegacionDe,
  PRIMERAS_PAGINAS_DE_VENTAS,
  volverALaPrimera,
} from '../../../../src/domain/reportes/paginacion'

/**
 * Change 26, tarea 21.6 (D12, D14; spec `reportes/area-de-reportes`, «La navegación entre páginas en `/admin`»):
 * lo que la pantalla muestra de la paginación sale del sobre del servidor, en una función pura.
 */
describe('navegacionDe', () => {
  it('en la primera página de varias: Anterior deshabilitado y Siguiente habilitado', () => {
    expect(navegacionDe({ pagina: 1, paginas: 3 })).toEqual({
      visible: true,
      anteriorHabilitado: false,
      siguienteHabilitado: true,
      texto: 'Página 1 de 3',
    })
  })

  it('en una página intermedia: los dos habilitados', () => {
    expect(navegacionDe({ pagina: 2, paginas: 3 })).toEqual({
      visible: true,
      anteriorHabilitado: true,
      siguienteHabilitado: true,
      texto: 'Página 2 de 3',
    })
  })

  it('en la última: Siguiente deshabilitado y Anterior habilitado', () => {
    expect(navegacionDe({ pagina: 3, paginas: 3 })).toEqual({
      visible: true,
      anteriorHabilitado: true,
      siguienteHabilitado: false,
      texto: 'Página 3 de 3',
    })
  })

  it('con una sola página o sin filas no se muestra', () => {
    expect(navegacionDe({ pagina: 1, paginas: 1 }).visible).toBe(false)
    expect(navegacionDe({ pagina: 1, paginas: 0 }).visible).toBe(false)
  })

  it('una página posterior a la última no deja avanzar y deja volver', () => {
    const fuera = navegacionDe({ pagina: 5, paginas: 3 })
    expect(fuera.siguienteHabilitado).toBe(false)
    expect(fuera.anteriorHabilitado).toBe(true)
  })
})

describe('el estado de páginas de la pestaña de ventas', () => {
  it('arranca con todas las listas en la página 1', () => {
    expect(PRIMERAS_PAGINAS_DE_VENTAS).toEqual({ porDia: 1, porProducto: 1, anuladas: 1 })
  })

  it('cambiar de página en una lista no mueve las otras', () => {
    const paginas = irALaPagina(PRIMERAS_PAGINAS_DE_VENTAS, 'porDia', 2)

    expect(paginas).toEqual({ porDia: 2, porProducto: 1, anuladas: 1 })
    expect(irALaPagina(paginas, 'anuladas', 4)).toEqual({ porDia: 2, porProducto: 1, anuladas: 4 })
  })

  it('cambiar un filtro vuelve todas las listas a la página 1', () => {
    expect(volverALaPrimera({ porDia: 2, porProducto: 3, anuladas: 4 })).toEqual({
      porDia: 1,
      porProducto: 1,
      anuladas: 1,
    })
    expect(volverALaPrimera({ pagina: 7 })).toEqual({ pagina: 1 })
  })

  it('no modifica el estado anterior', () => {
    const antes = { porDia: 2, porProducto: 1, anuladas: 1 }
    irALaPagina(antes, 'porDia', 3)
    volverALaPrimera(antes)

    expect(antes).toEqual({ porDia: 2, porProducto: 1, anuladas: 1 })
  })
})
