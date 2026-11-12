import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }))
vi.mock('../../../../../src/lib/api/httpClient', () => ({ apiFetch: apiFetchMock }))

import { RendicionesReporte } from '../../../../../src/areas/admin/reportes/RendicionesReporte'
import { enrutar, llamadas, type ReglaDeApi } from '../../../utils/enrutarApi'
import { queryClientConYo, type RolDePrueba } from '../../../utils/permisosDePrueba'
import { detalleDeRendicion, reporteDeRendiciones } from './otrosReportesDePrueba'
import { sobreDePrueba } from './reporteDePrueba'

/**
 * Change 26, tarea 11.1 (spec `reportes/rendicion-por-vendedor`, «La pestaña «Rendiciones»», sus dos escenarios;
 * D7, D11, D12; cita RUT-07): la tabla por vendedor, la lista de jornadas con sus estados, «En curso», «Sin
 * conteo», «Ver detalle» con el resumen de la jornada y sin la columna de valor sin `VER_COSTOS`.
 */
function reglas(reporte: unknown, detalle?: { status: number; cuerpo: unknown }): ReglaDeApi[] {
  return [
    { ruta: '/reportes/rendiciones', responder: () => ({ status: 200, cuerpo: reporte }) },
    {
      ruta: /^\/reportes\/rendiciones\/[^/]+$/,
      responder: () => detalle ?? { status: 200, cuerpo: detalleDeRendicion(false) },
    },
    {
      ruta: '/catalogo/productos',
      responder: () => ({ status: 200, cuerpo: { items: [{ id: 'p1', codigo: 'V1', nombre: 'Vino A', activo: true }], cursor_siguiente: null } }),
    },
  ]
}

function montar(rol: RolDePrueba = 'CON') {
  return render(
    <QueryClientProvider client={queryClientConYo(rol)}>
      <MemoryRouter>
        <RendicionesReporte />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

const filaDe = (tabla: HTMLElement, texto: string) => within(tabla).getByRole('row', { name: new RegExp(texto) })

describe('RendicionesReporte: por vendedor y jornadas (RUT-07)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
  })

  it('abre sin fechas, muestra el período del servidor y la tabla por vendedor con sus totales', async () => {
    enrutar(apiFetchMock, reglas(reporteDeRendiciones(true)))
    montar()

    expect(await screen.findByText('Período: 01/11/2026 al 06/11/2026')).toBeInTheDocument()
    expect(llamadas(apiFetchMock, 'GET', '/reportes/rendiciones')[0]?.url.search).toBe('')
    const tabla = screen.getByRole('table', { name: 'Por vendedor' })
    expect(within(tabla).getAllByRole('columnheader').map((c) => c.textContent)).toEqual([
      'Vendedor',
      'Jornadas',
      'Ventas',
      'Anuladas',
      'Cobrado',
      'Faltantes',
      'Sobrantes',
      'Valor de las diferencias',
    ])
    const uno = filaDe(tabla, 'Vendedor Uno')
    expect(uno).toHaveTextContent('1.500,00')
    expect(uno).toHaveTextContent('300,00')
    expect(uno).toHaveTextContent('1.200,00')
    expect(uno).toHaveTextContent('Efectivo: 900,00')
    expect(uno).toHaveTextContent('Transferencia: 300,00')
    expect(uno).toHaveTextContent('750,00')
    const dos = filaDe(tabla, 'Vendedor Dos')
    expect(within(dos).getAllByRole('cell')[1]).toHaveTextContent('2')
    expect(dos).toHaveTextContent('2.400,00')
  })

  it('la lista de jornadas muestra cada estado, las fechas de cada paso y «En curso» para la abierta', async () => {
    enrutar(apiFetchMock, reglas(reporteDeRendiciones(true)))
    montar()

    const tabla = await screen.findByRole('table', { name: 'Jornadas' })
    expect(within(tabla).getAllByRole('columnheader').map((c) => c.textContent)).toEqual([
      'Vendedor',
      'Jornada',
      'Ubicación',
      'Abierta',
      'Rendida',
      'Cerrada',
      'Liberada',
      'Ventas',
      'Anuladas',
      'Cobrado',
      'Después de la rendición',
      'Faltantes',
      'Sobrantes',
      'Valor de las diferencias',
      '',
    ])
    const cerrada = within(tabla).getAllByRole('row')[1] as HTMLElement
    expect(cerrada).toHaveTextContent('Cerrada')
    expect(cerrada).toHaveTextContent('02/11/2026')
    expect(cerrada).toHaveTextContent('03/11/2026')
    expect(cerrada).toHaveTextContent('Camión 1')
    const enCurso = within(tabla).getAllByRole('row')[2] as HTMLElement
    expect(enCurso).toHaveTextContent('En curso')
    expect(enCurso).not.toHaveTextContent('Abierta')
    const liberada = within(tabla).getAllByRole('row')[3] as HTMLElement
    expect(liberada).toHaveTextContent('Liberada')
    expect(liberada).toHaveTextContent('04/11/2026')
  })

  it('«Sin conteo» donde no hay rendición, y los faltantes y sobrantes donde sí', async () => {
    enrutar(apiFetchMock, reglas(reporteDeRendiciones(true)))
    montar()

    const filas = within(await screen.findByRole('table', { name: 'Jornadas' })).getAllByRole('row')
    expect(within(filas[1] as HTMLElement).queryByText('Sin conteo')).not.toBeInTheDocument()
    expect(within(filas[2] as HTMLElement).getAllByText('Sin conteo')).toHaveLength(2)
    expect(within(filas[3] as HTMLElement).getAllByText('Sin conteo')).toHaveLength(2)
    const celdas = within(filas[1] as HTMLElement).getAllByRole('cell')
    expect(celdas[11]).toHaveTextContent('2')
    expect(celdas[12]).toHaveTextContent('1')
  })

  it('lo registrado después de la rendición va en su columna, aparte de las ventas', async () => {
    enrutar(apiFetchMock, reglas(reporteDeRendiciones(true)))
    montar()

    const filas = within(await screen.findByRole('table', { name: 'Jornadas' })).getAllByRole('row')
    const celdas = within(filas[3] as HTMLElement).getAllByRole('cell')
    expect(celdas[7]).toHaveTextContent('2.000,00')
    expect(celdas[10]).toHaveTextContent('Ventas')
    expect(celdas[10]).toHaveTextContent('100,00')
    expect(within(filas[1] as HTMLElement).getAllByRole('cell')[10]?.textContent).toBe('')
  })

  it('sin VER_COSTOS no hay columna «Valor de las diferencias» en ninguna tabla', async () => {
    enrutar(apiFetchMock, reglas(reporteDeRendiciones(false)))
    montar('SUP')

    await screen.findByRole('table', { name: 'Jornadas' })
    expect(screen.queryByRole('columnheader', { name: 'Valor de las diferencias' })).not.toBeInTheDocument()
    expect(screen.queryByText('750,00')).not.toBeInTheDocument()
  })

  it('un período sin jornadas muestra «Sin jornadas en el período.»', async () => {
    enrutar(apiFetchMock, reglas(reporteDeRendiciones(true, { jornadas: sobreDePrueba([]), por_vendedor: [] })))
    montar()

    expect(await screen.findByText('Sin jornadas en el período.')).toBeInTheDocument()
    expect(screen.queryByRole('table', { name: 'Jornadas' })).not.toBeInTheDocument()
  })

  it('ofrece la ayuda de las rendiciones', async () => {
    enrutar(apiFetchMock, reglas(reporteDeRendiciones(true)))
    montar()

    expect(await screen.findByRole('button', { name: 'Ayuda: Rendiciones' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Ayuda: Período' })).toBeInTheDocument()
  })
})

describe('RendicionesReporte: filtros y detalle', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
  })

  it('el estado y el vendedor se mandan al servidor', async () => {
    enrutar(apiFetchMock, reglas(reporteDeRendiciones(true)))
    const usuario = userEvent.setup()
    montar()
    await screen.findByRole('table', { name: 'Jornadas' })

    await usuario.selectOptions(screen.getByLabelText('Estado'), 'CERRADA')
    await usuario.selectOptions(screen.getByLabelText('Vendedor'), 'v2')

    await waitFor(() => {
      const busquedas = llamadas(apiFetchMock, 'GET', '/reportes/rendiciones').map((l) => l.url.search)
      expect(busquedas).toContain('?vendedor_id=v2&estado=CERRADA')
    })
    expect(within(screen.getByLabelText('Estado')).getAllByRole('option').map((o) => o.textContent)).toEqual([
      'Todos',
      'En curso',
      'En rendición',
      'Cerrada',
      'Liberada',
    ])
  })

  it('«Ver detalle» abre el resumen de la jornada pedido al reporte, sin valores de costo (RUT-07)', async () => {
    enrutar(apiFetchMock, reglas(reporteDeRendiciones(false)))
    const usuario = userEvent.setup()
    montar('CON')

    const tabla = await screen.findByRole('table', { name: 'Jornadas' })
    await usuario.click(within(within(tabla).getAllByRole('row')[1] as HTMLElement).getByRole('button', { name: 'Ver detalle' }))

    expect(await screen.findByRole('heading', { name: 'Resumen de la jornada' })).toBeInTheDocument()
    expect(llamadas(apiFetchMock, 'GET', '/reportes/rendiciones/j1')).toHaveLength(1)
    expect(screen.getByRole('table', { name: 'Stock de la jornada' })).toBeInTheDocument()
    expect(screen.getByText('Ventas: 2 por 1.500,00')).toBeInTheDocument()
    expect(screen.queryByText('Valor de la diferencia', { exact: false })).not.toBeInTheDocument()
  })

  it('«Ver detalle» nombra los productos y muestra cajas con lo que trae el reporte, sin pedir el catálogo ni los saldos (RUT-07, D7)', async () => {
    enrutar(apiFetchMock, reglas(reporteDeRendiciones(false)))
    const usuario = userEvent.setup()
    montar('CON')

    const tabla = await screen.findByRole('table', { name: 'Jornadas' })
    await usuario.click(within(within(tabla).getAllByRole('row')[1] as HTMLElement).getByRole('button', { name: 'Ver detalle' }))

    const stock = await screen.findByRole('table', { name: 'Stock de la jornada' })
    expect(within(stock).getByText('Vino A')).toBeInTheDocument()
    expect(within(stock).getByText('20 unidades (3 Caja x6 + 2 un.)')).toBeInTheDocument()
    expect(llamadas(apiFetchMock, 'GET', '/catalogo/productos')).toHaveLength(0)
    expect(llamadas(apiFetchMock, 'GET', '/stock/saldos')).toHaveLength(0)
  })

  it('una jornada que no existe muestra «No se encontró la jornada.»', async () => {
    enrutar(
      apiFetchMock,
      reglas(reporteDeRendiciones(true), { status: 404, cuerpo: { title: 'No encontrado', codigo: 'RECURSO_NO_ENCONTRADO' } }),
    )
    const usuario = userEvent.setup()
    montar()

    const tabla = await screen.findByRole('table', { name: 'Jornadas' })
    await usuario.click(within(within(tabla).getAllByRole('row')[1] as HTMLElement).getByRole('button', { name: 'Ver detalle' }))

    expect(await screen.findByText('No se encontró la jornada.')).toBeInTheDocument()
  })

  it('un error del servidor se muestra con el texto de carga', async () => {
    enrutar(apiFetchMock, [
      { ruta: '/reportes/rendiciones', responder: () => ({ status: 500, cuerpo: { title: 'x', codigo: 'ERROR' } }) },
    ])
    montar()

    expect(await screen.findByText('No se pudo cargar el reporte. Probá de nuevo.')).toBeInTheDocument()
  })
})

/**
 * Change 26, tarea 21.8 (spec `reportes/area-de-reportes`, «La navegación entre páginas en `/admin`»; D14): la lista
 * de jornadas va en páginas; «Por vendedor» no, y sus totales no cambian al pasar de página.
 */
function responderPaginado() {
  enrutar(apiFetchMock, [
    {
      ruta: '/reportes/rendiciones',
      responder: (url) => {
        const base = reporteDeRendiciones(true)
        const pagina = Number(url.searchParams.get('pagina') ?? '1')
        return {
          status: 200,
          cuerpo: { ...base, jornadas: { ...base.jornadas, pagina, paginas: 3, total_filas: 120 } },
        }
      },
    },
  ])
}

describe('RendicionesReporte: paginación de las jornadas (D14)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
  })

  it('muestra la navegación debajo de «Jornadas» y no debajo de «Por vendedor»', async () => {
    responderPaginado()
    montar()

    await screen.findByRole('table', { name: 'Jornadas' })
    const nav = screen.getByRole('navigation', { name: 'Paginación de Jornadas' })
    expect(within(nav).getByText('Página 1 de 3')).toBeInTheDocument()
    expect(within(nav).getByRole('button', { name: 'Anterior' })).toBeDisabled()
    expect(screen.getAllByRole('navigation')).toHaveLength(1)
  })

  it('«Siguiente» pide la página 2 y «Por vendedor» conserva sus totales', async () => {
    responderPaginado()
    const usuario = userEvent.setup()
    montar()
    const porVendedor = await screen.findByRole('table', { name: 'Por vendedor' })
    const antes = porVendedor.textContent

    await usuario.click(within(screen.getByRole('navigation', { name: 'Paginación de Jornadas' })).getByRole('button', { name: 'Siguiente' }))

    await waitFor(() => expect(llamadas(apiFetchMock, 'GET', '/reportes/rendiciones').map((l) => l.url.search)).toContain('?pagina=2'))
    expect(
      await within(screen.getByRole('navigation', { name: 'Paginación de Jornadas' })).findByText('Página 2 de 3'),
    ).toBeInTheDocument()
    expect(screen.getByRole('table', { name: 'Por vendedor' }).textContent).toBe(antes)
  })

  it('cambiar el estado vuelve a la página 1', async () => {
    responderPaginado()
    const usuario = userEvent.setup()
    montar()
    await screen.findByRole('table', { name: 'Jornadas' })
    await usuario.click(within(screen.getByRole('navigation', { name: 'Paginación de Jornadas' })).getByRole('button', { name: 'Siguiente' }))
    await waitFor(() => expect(llamadas(apiFetchMock, 'GET', '/reportes/rendiciones').map((l) => l.url.search)).toContain('?pagina=2'))

    await usuario.selectOptions(screen.getByLabelText('Estado'), 'CERRADA')

    await waitFor(() => expect(llamadas(apiFetchMock, 'GET', '/reportes/rendiciones').map((l) => l.url.search)).toContain('?estado=CERRADA'))
  })

  it('con una sola página no hay navegación', async () => {
    enrutar(apiFetchMock, reglas(reporteDeRendiciones(true)))
    montar()

    await screen.findByRole('table', { name: 'Jornadas' })
    expect(screen.queryByRole('navigation')).not.toBeInTheDocument()
  })
})
