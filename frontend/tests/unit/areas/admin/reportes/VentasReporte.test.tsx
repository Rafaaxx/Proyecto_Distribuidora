import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }))
vi.mock('../../../../../src/lib/api/httpClient', () => ({ apiFetch: apiFetchMock }))

import { VentasReporte } from '../../../../../src/areas/admin/reportes/VentasReporte'
import { queryClientConYo, type RolDePrueba } from '../../../utils/permisosDePrueba'
import { reporteDeVentas, reporteVacio } from './reporteDePrueba'

/**
 * Change 26, tarea 10.2 (spec `reportes/ventas-por-periodo`, «La pestaña «Ventas»» y los escenarios de pantalla de
 * utilidad; D2, D3, D5, D11, D12; cita REP-02, REP-03, REP-04): el resumen, los tres desgloses, la nota de líneas
 * sin costo, las anuladas aparte y las columnas de costo y utilidad solo con `ve_utilidad`.
 */
function responder(cuerpo: unknown) {
  apiFetchMock.mockImplementation(() => Promise.resolve({ ok: true, status: 200, json: async () => cuerpo }))
}

function responderError(status: number, cuerpo: unknown) {
  apiFetchMock.mockImplementation(() => Promise.resolve({ ok: false, status, json: async () => cuerpo }))
}

function montar(rol: RolDePrueba = 'CON') {
  return render(
    <QueryClientProvider client={queryClientConYo(rol)}>
      <MemoryRouter>
        <VentasReporte />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

const llamadas = () => apiFetchMock.mock.calls.map(([ruta]) => String(ruta))

describe('VentasReporte: con utilidad y líneas sin costo (REP-02, REP-04)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
  })

  it('abre sin fechas, muestra el período del servidor y el resumen formateado desde los strings', async () => {
    responder(reporteDeVentas(true))
    montar()

    expect(await screen.findByText('Período: 01/11/2026 al 06/11/2026')).toBeInTheDocument()
    expect(llamadas()).toEqual(['/reportes/ventas'])
    const resumen = screen.getByRole('region', { name: 'Resumen del período' })
    expect(within(resumen).getByText('Neto').nextElementSibling).toHaveTextContent('1.500,00')
    expect(within(resumen).getByText('Cajas equivalentes').nextElementSibling).toHaveTextContent('2,50')
    expect(within(resumen).getByText('Unidades').nextElementSibling).toHaveTextContent('15')
    expect(within(resumen).getByText('Costo vendido').nextElementSibling).toHaveTextContent('850,00')
    expect(within(resumen).getByText('Utilidad').nextElementSibling).toHaveTextContent('350,00')
  })

  it('muestra los desgloses por día, por vendedor y por producto', async () => {
    responder(reporteDeVentas(true))
    montar()

    const porDia = await screen.findByRole('table', { name: 'Por día' })
    expect(within(porDia).getByText('02/11/2026')).toBeInTheDocument()
    expect(within(porDia).getByText('777,00')).toBeInTheDocument()
    const porVendedor = screen.getByRole('table', { name: 'Por vendedor' })
    expect(within(porVendedor).getByText('Vendedor Uno')).toBeInTheDocument()
    expect(within(porVendedor).getByText('1.200,00')).toBeInTheDocument()
    const porProducto = screen.getByRole('table', { name: 'Por producto' })
    expect(within(porProducto).getByText('VIN-001')).toBeInTheDocument()
    expect(within(porProducto).getByText('1.200,00')).toBeInTheDocument()
  })

  it('el producto muestra el detalle por presentación al desplegarlo (REP-03)', async () => {
    responder(reporteDeVentas(true))
    const usuario = userEvent.setup()
    montar()

    const porProducto = await screen.findByRole('table', { name: 'Por producto' })
    expect(within(porProducto).queryByText('Caja x6')).not.toBeInTheDocument()
    await usuario.click(within(porProducto).getByRole('button', { name: 'Vino Tinto' }))

    expect(within(porProducto).getByRole('button', { name: 'Vino Tinto' })).toHaveAttribute('aria-expanded', 'true')
    const presentaciones = within(screen.getByRole('table', { name: 'Vino Tinto' }))
    expect(presentaciones.getAllByRole('columnheader').map((c) => c.textContent)).toEqual([
      'Presentación',
      'Unidades por presentación',
      'Cantidad',
      'Unidades',
    ])
    const caja = presentaciones.getByRole('row', { name: /Caja x6/ })
    expect(within(caja).getAllByRole('cell').map((c) => c.textContent)).toEqual(['Caja x6', '6', '2', '12'])
    const botella = presentaciones.getByRole('row', { name: /Botella/ })
    expect(within(botella).getAllByRole('cell').map((c) => c.textContent)).toEqual(['Botella', '1', '3', '3'])

    await usuario.click(within(porProducto).getByRole('button', { name: 'Vino Tinto' }))
    expect(within(porProducto).queryByText('Caja x6')).not.toBeInTheDocument()
  })

  it('la nota de líneas sin costo aparece con su texto aprobado y el costo y la utilidad en cada desglose', async () => {
    responder(reporteDeVentas(true))
    montar()

    expect(
      await screen.findByText(
        'Líneas sin costo: 1, con un neto de 300,00. No entran en el costo vendido ni en la utilidad.',
      ),
    ).toBeInTheDocument()
    for (const nombre of ['Por día', 'Por vendedor']) {
      const tabla = screen.getByRole('table', { name: nombre })
      expect(within(tabla).getByRole('columnheader', { name: 'Costo vendido' })).toBeInTheDocument()
      expect(within(tabla).getByRole('columnheader', { name: 'Utilidad' })).toBeInTheDocument()
    }
  })

  it('el desglose por producto no trae costo ni utilidad (REP-06 es de la etapa 2)', async () => {
    responder(reporteDeVentas(true))
    montar()

    const porProducto = await screen.findByRole('table', { name: 'Por producto' })
    expect(within(porProducto).queryByRole('columnheader', { name: 'Costo vendido' })).not.toBeInTheDocument()
    expect(within(porProducto).queryByRole('columnheader', { name: 'Utilidad' })).not.toBeInTheDocument()
  })

  it('las anuladas van en su sección, aparte de los totales, con fecha en la zona de la organización (REP-02)', async () => {
    responder(reporteDeVentas(true))
    montar()

    expect(await screen.findByText('1 ventas anuladas por 500,00. No entran en los totales.')).toBeInTheDocument()
    const tabla = screen.getByRole('table', { name: 'Ventas anuladas del período' })
    const fila = within(tabla).getByRole('row', { name: /V-0007/ })
    expect(within(fila).getAllByRole('cell').map((c) => c.textContent)).toEqual([
      'V-0007',
      '30/10/2026',
      'Almacén Norte',
      'Vendedor Uno',
      '500,00',
      '02/11/2026',
      'Error de carga',
      'Sí',
    ])
    expect(screen.queryByText('Sin ventas anuladas en el período.')).not.toBeInTheDocument()
  })

  it('una anulada que no devolvió el dinero dice «No»', async () => {
    const base = reporteDeVentas(true)
    const anulada = base.anuladas.ventas.filas[0]
    if (!anulada) throw new Error('el reporte de prueba trae una anulada')
    responder({ ...base, anuladas: { ...base.anuladas, ventas: { ...base.anuladas.ventas, filas: [{ ...anulada, devuelve_dinero: false }] } } })
    montar()

    const tabla = await screen.findByRole('table', { name: 'Ventas anuladas del período' })
    const celdas = within(within(tabla).getByRole('row', { name: /V-0007/ })).getAllByRole('cell')
    expect(celdas[celdas.length - 1]).toHaveTextContent('No')
  })
})

describe('VentasReporte: sin VER_UTILIDAD (REP-04)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
  })

  it('no muestra columnas, tarjetas ni nota de costo y utilidad', async () => {
    responder(reporteDeVentas(false))
    montar('SUP')

    await screen.findByRole('table', { name: 'Por día' })
    expect(screen.queryByText('Costo vendido')).not.toBeInTheDocument()
    expect(screen.queryByText('Utilidad')).not.toBeInTheDocument()
    expect(screen.queryByText(/Líneas sin costo/)).not.toBeInTheDocument()
    expect(within(screen.getByRole('table', { name: 'Por día' })).getByText('777,00')).toBeInTheDocument()
  })
})

describe('VentasReporte: período vacío (REP-01)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
  })

  it('muestra los dos textos de vacío y ninguna nota de líneas sin costo', async () => {
    responder(reporteVacio())
    montar()

    expect(await screen.findByText('Sin ventas en el período.')).toBeInTheDocument()
    expect(screen.getByText('Sin ventas anuladas en el período.')).toBeInTheDocument()
    expect(screen.queryByRole('table', { name: 'Por día' })).not.toBeInTheDocument()
    expect(screen.queryByText(/Líneas sin costo/)).not.toBeInTheDocument()
  })
})

describe('VentasReporte: filtros (D1, D11; TR-04)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
  })

  it('los campos «Desde» y «Hasta» arrancan con el período que devolvió el servidor', async () => {
    responder(reporteDeVentas(true))
    montar()

    await screen.findByText('Período: 01/11/2026 al 06/11/2026')
    await waitFor(() => expect(screen.getByLabelText('Desde')).toHaveValue('2026-11-01'))
    expect(screen.getByLabelText('Hasta')).toHaveValue('2026-11-06')
  })

  it('al elegir otras fechas vuelve a pedir el reporte con ellas', async () => {
    responder(reporteDeVentas(true))
    const usuario = userEvent.setup()
    montar()
    await screen.findByText('Período: 01/11/2026 al 06/11/2026')

    await usuario.clear(screen.getByLabelText('Desde'))
    await usuario.type(screen.getByLabelText('Desde'), '2026-10-01')
    await usuario.clear(screen.getByLabelText('Hasta'))
    await usuario.type(screen.getByLabelText('Hasta'), '2026-10-31')

    await waitFor(() => expect(llamadas()).toContain('/reportes/ventas?desde=2026-10-01&hasta=2026-10-31'))
  })

  it('«Desde» posterior a «Hasta» se rechaza en el formulario y no se pide (TR-04)', async () => {
    responder(reporteDeVentas(true))
    const usuario = userEvent.setup()
    montar()
    await screen.findByText('Período: 01/11/2026 al 06/11/2026')
    await waitFor(() => expect(screen.getByLabelText('Hasta')).toHaveValue('2026-11-06'))
    await usuario.clear(screen.getByLabelText('Desde'))
    // Vaciar «Desde» es un período válido (el servidor lo completa): se pide una vez más.
    await waitFor(() => expect(llamadas()).toContain('/reportes/ventas?hasta=2026-11-06'))
    const pedidosAntes = llamadas().length

    await usuario.type(screen.getByLabelText('Desde'), '2026-12-01')

    expect(await screen.findByText('"Desde" no puede ser posterior a "Hasta".')).toBeInTheDocument()
    expect(llamadas()).toHaveLength(pedidosAntes)
  })

  it('filtra por vendedor con las opciones del reporte y «Todos» lo quita', async () => {
    responder(reporteDeVentas(true))
    const usuario = userEvent.setup()
    montar()
    await screen.findByText('Período: 01/11/2026 al 06/11/2026')

    const selector = screen.getByLabelText('Vendedor')
    expect(within(selector).getAllByRole('option').map((o) => o.textContent)).toEqual([
      'Todos',
      'Vendedor Uno',
      'Vendedor Dos',
    ])
    await usuario.selectOptions(selector, 'v2')
    await waitFor(() => expect(llamadas()).toContain('/reportes/ventas?vendedor_id=v2'))

    await usuario.selectOptions(screen.getByLabelText('Vendedor'), '')
    await waitFor(() => expect(llamadas().filter((r) => r === '/reportes/ventas').length).toBeGreaterThan(1))
  })

  it('PERIODO_DEMASIADO_LARGO muestra su texto aprobado y conserva los filtros', async () => {
    responder(reporteDeVentas(true))
    const usuario = userEvent.setup()
    montar()
    await screen.findByText('Período: 01/11/2026 al 06/11/2026')

    responderError(422, { title: 'x', codigo: 'PERIODO_DEMASIADO_LARGO' })
    await usuario.clear(screen.getByLabelText('Desde'))
    await usuario.type(screen.getByLabelText('Desde'), '2024-01-01')

    expect(await screen.findByText('El período no puede superar los 366 días.')).toBeInTheDocument()
    expect(screen.getByLabelText('Desde')).toHaveValue('2024-01-01')
    expect(screen.getByLabelText('Hasta')).toHaveValue('2026-11-06')
  })

  it('un error cualquiera muestra el texto de error de carga', async () => {
    responderError(500, { title: 'boom' })
    montar()

    expect(await screen.findByText('No se pudo cargar el reporte. Probá de nuevo.')).toBeInTheDocument()
  })
})

/**
 * Change 26, tarea 13.1 (spec `sistema/ayuda-contextual`; D13; ADR-051): los «(?)» de «Ventas» donde dice D13;
 * `reportes.utilidad` solo se ve con `VER_UTILIDAD` (REP-04).
 */
describe('VentasReporte: ayudas (D13)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
  })

  it('con utilidad ofrece las cinco ayudas: período, cajas equivalentes, utilidad, líneas sin costo y anuladas', async () => {
    responder(reporteDeVentas(true))
    montar('CON')

    await screen.findByRole('table', { name: 'Por día' })
    for (const titulo of ['Período', 'Cajas equivalentes', 'Utilidad', 'Líneas sin costo', 'Ventas anuladas']) {
      expect(screen.getByRole('button', { name: `Ayuda: ${titulo}` })).toBeInTheDocument()
    }
  })

  it('sin VER_UTILIDAD no hay ayuda de utilidad ni de líneas sin costo', async () => {
    responder(reporteDeVentas(false))
    montar('SUP')

    await screen.findByRole('table', { name: 'Por día' })
    expect(screen.getByRole('button', { name: 'Ayuda: Cajas equivalentes' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Ayuda: Ventas anuladas' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Ayuda: Utilidad' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Ayuda: Líneas sin costo' })).not.toBeInTheDocument()
  })

  it('la ayuda de las anuladas explica que no suman en el período en que se hicieron, sin ejemplo', async () => {
    responder(reporteDeVentas(true))
    const usuario = userEvent.setup()
    montar('CON')

    await usuario.click(await screen.findByRole('button', { name: 'Ayuda: Ventas anuladas' }))

    expect(
      screen.getByText(/no suma en los totales del período en que se hizo, aunque se haya anulado después/),
    ).toBeInTheDocument()
  })
})

/**
 * Change 26, tarea 21.8 (spec `reportes/area-de-reportes`, «La navegación entre páginas en `/admin`»; D14): tres
 * listas paginadas, cada una por su lado, con los totales y el orden del servidor.
 */
function paginaPedida(url: string, nombre: string): number {
  const valor = new URL(url, 'http://x').searchParams.get(nombre)
  return valor === null ? 1 : Number(valor)
}

/** Un servidor que responde la página pedida de cada lista, con 3 páginas en las tres. */
function responderPaginado() {
  apiFetchMock.mockImplementation((url: string) => {
    const base = reporteDeVentas(true)
    const dia = paginaPedida(url, 'pagina_por_dia')
    const producto = paginaPedida(url, 'pagina_por_producto')
    const anuladas = paginaPedida(url, 'pagina_anuladas')
    const cuerpo = {
      ...base,
      por_dia: { ...base.por_dia, pagina: dia, paginas: 3, total_filas: 120 },
      por_producto: { ...base.por_producto, pagina: producto, paginas: 3, total_filas: 120 },
      anuladas: { ...base.anuladas, ventas: { ...base.anuladas.ventas, pagina: anuladas, paginas: 3, total_filas: 120 } },
    }
    return Promise.resolve({ ok: true, status: 200, json: async () => cuerpo })
  })
}

describe('VentasReporte: paginación (D14)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
  })

  it('«Por día», «Por producto» y las anuladas muestran su navegación; «Por vendedor» no', async () => {
    responderPaginado()
    montar()

    await screen.findByRole('table', { name: 'Por día' })
    for (const lista of ['Por día', 'Por producto', 'Ventas anuladas del período']) {
      const nav = screen.getByRole('navigation', { name: `Paginación de ${lista}` })
      expect(within(nav).getByText('Página 1 de 3')).toBeInTheDocument()
      expect(within(nav).getByRole('button', { name: 'Anterior' })).toBeDisabled()
    }
    expect(screen.getAllByRole('navigation')).toHaveLength(3)
  })

  it('«Siguiente» en «Por día» pide solo la página 2 de esa lista y deja las otras en la 1', async () => {
    responderPaginado()
    const usuario = userEvent.setup()
    montar()
    await screen.findByRole('table', { name: 'Por día' })

    await usuario.click(within(screen.getByRole('navigation', { name: 'Paginación de Por día' })).getByRole('button', { name: 'Siguiente' }))

    await waitFor(() => expect(llamadas()).toContain('/reportes/ventas?pagina_por_dia=2'))
    expect(
      await within(screen.getByRole('navigation', { name: 'Paginación de Por día' })).findByText('Página 2 de 3'),
    ).toBeInTheDocument()
    expect(
      within(screen.getByRole('navigation', { name: 'Paginación de Por producto' })).getByText('Página 1 de 3'),
    ).toBeInTheDocument()
    expect(
      within(screen.getByRole('navigation', { name: 'Paginación de Ventas anuladas del período' })).getByText('Página 1 de 3'),
    ).toBeInTheDocument()
  })

  it('cada lista pide su propio parámetro y los pide a la vez si ya se movieron', async () => {
    responderPaginado()
    const usuario = userEvent.setup()
    montar()
    await screen.findByRole('table', { name: 'Por día' })

    await usuario.click(within(screen.getByRole('navigation', { name: 'Paginación de Por producto' })).getByRole('button', { name: 'Siguiente' }))
    await waitFor(() => expect(llamadas()).toContain('/reportes/ventas?pagina_por_producto=2'))
    await usuario.click(
      within(screen.getByRole('navigation', { name: 'Paginación de Ventas anuladas del período' })).getByRole('button', {
        name: 'Siguiente',
      }),
    )

    await waitFor(() => expect(llamadas()).toContain('/reportes/ventas?pagina_por_producto=2&pagina_anuladas=2'))
  })

  it('los totales no cambian al pasar de página y el orden es el del servidor', async () => {
    responderPaginado()
    const usuario = userEvent.setup()
    montar()
    const porDia = await screen.findByRole('table', { name: 'Por día' })
    // El servidor manda el 03/11 antes que el 02/11 y la pantalla no lo reordena.
    expect(within(porDia).getAllByRole('row').slice(1).map((f) => within(f).getAllByRole('cell')[0]?.textContent)).toEqual([
      '03/11/2026',
      '02/11/2026',
    ])
    const resumenAntes = screen.getByRole('region', { name: 'Resumen del período' }).textContent
    const anuladasAntes = screen.getByText('1 ventas anuladas por 500,00. No entran en los totales.')

    await usuario.click(within(screen.getByRole('navigation', { name: 'Paginación de Por día' })).getByRole('button', { name: 'Siguiente' }))
    await waitFor(() => expect(llamadas()).toContain('/reportes/ventas?pagina_por_dia=2'))

    expect(screen.getByRole('region', { name: 'Resumen del período' }).textContent).toBe(resumenAntes)
    expect(anuladasAntes).toBeInTheDocument()
  })

  it('cambiar el vendedor vuelve todas las listas a la página 1', async () => {
    responderPaginado()
    const usuario = userEvent.setup()
    montar()
    await screen.findByRole('table', { name: 'Por día' })
    await usuario.click(within(screen.getByRole('navigation', { name: 'Paginación de Por día' })).getByRole('button', { name: 'Siguiente' }))
    await usuario.click(within(screen.getByRole('navigation', { name: 'Paginación de Por producto' })).getByRole('button', { name: 'Siguiente' }))
    await waitFor(() => expect(llamadas()).toContain('/reportes/ventas?pagina_por_dia=2&pagina_por_producto=2'))

    await usuario.selectOptions(screen.getByLabelText('Vendedor'), 'v2')

    await waitFor(() => expect(llamadas()).toContain('/reportes/ventas?vendedor_id=v2'))
  })

  it('cambiar el período vuelve todas las listas a la página 1', async () => {
    responderPaginado()
    const usuario = userEvent.setup()
    montar()
    await screen.findByRole('table', { name: 'Por día' })
    await usuario.click(within(screen.getByRole('navigation', { name: 'Paginación de Por día' })).getByRole('button', { name: 'Siguiente' }))
    await waitFor(() => expect(llamadas()).toContain('/reportes/ventas?pagina_por_dia=2'))
    await waitFor(() => expect(screen.getByLabelText('Hasta')).toHaveValue('2026-11-06'))

    await usuario.clear(screen.getByLabelText('Desde'))
    await usuario.type(screen.getByLabelText('Desde'), '2026-10-01')
    await usuario.clear(screen.getByLabelText('Hasta'))
    await usuario.type(screen.getByLabelText('Hasta'), '2026-10-31')

    await waitFor(() => expect(llamadas()).toContain('/reportes/ventas?desde=2026-10-01&hasta=2026-10-31'))
  })

  it('con una sola página no hay navegación (Una sola página)', async () => {
    responder(reporteDeVentas(true))
    montar()

    await screen.findByRole('table', { name: 'Por día' })
    expect(screen.queryByRole('navigation')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Siguiente' })).not.toBeInTheDocument()
  })
})
