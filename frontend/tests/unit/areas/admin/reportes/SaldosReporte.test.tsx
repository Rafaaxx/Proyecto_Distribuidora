import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }))
vi.mock('../../../../../src/lib/api/httpClient', () => ({ apiFetch: apiFetchMock }))

import { ReportesArea } from '../../../../../src/areas/admin/reportes/ReportesArea'
import {
  SaldosDeClientesReporte,
  SaldosDeProveedoresReporte,
} from '../../../../../src/areas/admin/reportes/SaldosReporte'
import { enrutar, llamadas, type ReglaDeApi } from '../../../utils/enrutarApi'
import { queryClientConYo, type RolDePrueba } from '../../../utils/permisosDePrueba'
import { reporteDeVentas, sobreDePrueba } from './reporteDePrueba'
import { reporteDeSaldosDeClientes, reporteDeSaldosDeProveedores } from './otrosReportesDePrueba'

/**
 * Change 26, tarea 12.1 (spec `reportes/saldos-de-cuentas`, «Las pestañas de saldos», sus tres escenarios; D8 = B,
 * D11, D12; cita CC-04, ADR-033, SEG-06): filtros, totales, «a favor» en los negativos, «Ver estado de cuenta»
 * solo con `GESTIONAR_CLIENTES` / `GESTIONAR_PROVEEDORES`, y la pestaña de proveedores solo con la regla compuesta.
 */
function reglas(clientes: unknown = reporteDeSaldosDeClientes(), proveedores: unknown = reporteDeSaldosDeProveedores()): ReglaDeApi[] {
  return [
    { ruta: '/reportes/saldos/clientes', responder: () => ({ status: 200, cuerpo: clientes }) },
    { ruta: '/reportes/saldos/proveedores', responder: () => ({ status: 200, cuerpo: proveedores }) },
  ]
}

function montar(rol: RolDePrueba, pantalla: 'clientes' | 'proveedores') {
  return render(
    <QueryClientProvider client={queryClientConYo(rol)}>
      <MemoryRouter>
        {pantalla === 'clientes' ? <SaldosDeClientesReporte /> : <SaldosDeProveedoresReporte />}
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('SaldosDeClientesReporte (CC-04)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
  })

  it('muestra los totales, la tabla y el saldo negativo con la marca «a favor»', async () => {
    enrutar(apiFetchMock, reglas())
    montar('GES', 'clientes')

    const tabla = await screen.findByRole('table', { name: 'Saldos de clientes' })
    expect(within(tabla).getAllByRole('columnheader').map((c) => c.textContent)).toEqual([
      'Código',
      'Razón social',
      'Vendedor',
      'Estado',
      'Límite',
      'Saldo',
      'Disponible',
      '',
    ])
    expect(screen.getByText('Total adeudado').nextElementSibling).toHaveTextContent('1.000,00')
    expect(screen.getByText('Total a favor').nextElementSibling).toHaveTextContent('200,00')
    expect(screen.getByText('Total a favor').nextElementSibling).not.toHaveTextContent('-')
    const deudor = within(tabla).getByRole('row', { name: /CLI-001/ })
    expect(deudor).toHaveTextContent('Almacén Norte SRL')
    expect(deudor).toHaveTextContent('Vendedor Uno')
    expect(deudor).toHaveTextContent('5.000,00')
    expect(deudor).toHaveTextContent('4.000,00')
    expect(deudor).not.toHaveTextContent('a favor')
    const aFavor = within(tabla).getByRole('row', { name: /CLI-002/ })
    expect(aFavor).toHaveTextContent('Kiosco Sur')
    expect(aFavor).toHaveTextContent('200,00 a favor')
    expect(aFavor).toHaveTextContent('Sin límite')
  })

  it('abre sin filtros (el servidor usa «Con saldo») y los manda al elegirlos', async () => {
    enrutar(apiFetchMock, reglas())
    const usuario = userEvent.setup()
    montar('GES', 'clientes')
    await screen.findByRole('table', { name: 'Saldos de clientes' })
    expect(llamadas(apiFetchMock, 'GET', '/reportes/saldos/clientes')[0]?.url.search).toBe('')
    expect(within(screen.getByLabelText('Saldo')).getAllByRole('option').map((o) => o.textContent)).toEqual([
      'Con saldo',
      'Deudores',
      'A favor',
      'Todos',
    ])

    await usuario.selectOptions(screen.getByLabelText('Saldo'), 'DEUDORES')
    await usuario.selectOptions(screen.getByLabelText('Estado'), 'ACTIVO')
    await usuario.selectOptions(screen.getByLabelText('Vendedor'), 'v1')
    await usuario.type(screen.getByLabelText('Buscar'), 'Alma')

    await waitFor(() => {
      const busquedas = llamadas(apiFetchMock, 'GET', '/reportes/saldos/clientes').map((l) => l.url.search)
      expect(busquedas).toContain('?saldo=DEUDORES&vendedor_id=v1&estado=ACTIVO&texto=Alma')
    })
  })

  it('el desplegable de vendedores trae todos los del servidor, aunque no estén en las filas de la página', async () => {
    enrutar(apiFetchMock, reglas())
    montar('GES', 'clientes')
    await screen.findByRole('table', { name: 'Saldos de clientes' })

    const opciones = within(screen.getByLabelText('Vendedor')).getAllByRole('option')

    expect(opciones.map((o) => o.textContent)).toEqual(['Todos', 'Vendedor Uno', 'Vendedor Dos'])
  })

  it('«Ver estado de cuenta» solo con GESTIONAR_CLIENTES, hacia la cuenta corriente del cliente', async () => {
    enrutar(apiFetchMock, reglas())
    montar('GES', 'clientes')

    const tabla = await screen.findByRole('table', { name: 'Saldos de clientes' })
    const enlaces = within(tabla).getAllByRole('link', { name: 'Ver estado de cuenta' })
    expect(enlaces).toHaveLength(2)
    expect(enlaces[0]).toHaveAttribute('href', '/admin/clientes/c1/cuenta-corriente')
  })

  it('Consulta/Dirección, sin GESTIONAR_CLIENTES, no ve el enlace', async () => {
    enrutar(apiFetchMock, reglas())
    montar('CON', 'clientes')

    await screen.findByRole('table', { name: 'Saldos de clientes' })
    expect(screen.queryByRole('link', { name: 'Ver estado de cuenta' })).not.toBeInTheDocument()
  })

  it('sin clientes muestra «Sin clientes para mostrar.»', async () => {
    enrutar(apiFetchMock, reglas(reporteDeSaldosDeClientes({ clientes: sobreDePrueba([]), total_adeudado: '0.00', total_a_favor: '0.00' })))
    montar('GES', 'clientes')

    expect(await screen.findByText('Sin clientes para mostrar.')).toBeInTheDocument()
    expect(screen.queryByRole('table', { name: 'Saldos de clientes' })).not.toBeInTheDocument()
  })

  it('ofrece la ayuda de los saldos', async () => {
    enrutar(apiFetchMock, reglas())
    montar('GES', 'clientes')

    expect(await screen.findByRole('button', { name: 'Ayuda: Saldos' })).toBeInTheDocument()
  })
})

describe('SaldosDeProveedoresReporte (CC-04)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
  })

  it('muestra los proveedores, sus totales y el saldo a favor', async () => {
    enrutar(apiFetchMock, reglas())
    montar('GES', 'proveedores')

    const tabla = await screen.findByRole('table', { name: 'Saldos de proveedores' })
    expect(within(tabla).getAllByRole('columnheader').map((c) => c.textContent)).toEqual([
      'Proveedor',
      'Estado',
      'Saldo',
      '',
    ])
    expect(within(tabla).getByRole('row', { name: /Bodega Sur/ })).toHaveTextContent('5.000,00')
    expect(within(tabla).getByRole('row', { name: /Distribuidora Este/ })).toHaveTextContent('80,00 a favor')
    expect(screen.getByText('Total adeudado').nextElementSibling).toHaveTextContent('5.000,00')
    expect(screen.getByText('Total a favor').nextElementSibling).toHaveTextContent('80,00')
    expect(screen.queryByLabelText('Vendedor')).not.toBeInTheDocument()
  })

  it('«Ver estado de cuenta» solo con GESTIONAR_PROVEEDORES', async () => {
    enrutar(apiFetchMock, reglas())
    montar('GES', 'proveedores')
    const tabla = await screen.findByRole('table', { name: 'Saldos de proveedores' })
    expect(within(tabla).getAllByRole('link', { name: 'Ver estado de cuenta' })[0]).toHaveAttribute(
      'href',
      '/admin/proveedores/pr1/cuenta-corriente',
    )
  })

  it('Consulta/Dirección ve los saldos pero no el enlace', async () => {
    enrutar(apiFetchMock, reglas())
    montar('CON', 'proveedores')

    await screen.findByRole('table', { name: 'Saldos de proveedores' })
    expect(screen.queryByRole('link', { name: 'Ver estado de cuenta' })).not.toBeInTheDocument()
  })

  it('manda saldo, estado y búsqueda (sin vendedor) y avisa si no hay proveedores', async () => {
    enrutar(apiFetchMock, reglas(undefined, reporteDeSaldosDeProveedores({ proveedores: sobreDePrueba([]), total_adeudado: '0.00', total_a_favor: '0.00' })))
    const usuario = userEvent.setup()
    montar('GES', 'proveedores')
    expect(await screen.findByText('Sin proveedores para mostrar.')).toBeInTheDocument()

    await usuario.selectOptions(screen.getByLabelText('Saldo'), 'A_FAVOR')
    await usuario.selectOptions(screen.getByLabelText('Estado'), 'INACTIVO')

    await waitFor(() => {
      const busquedas = llamadas(apiFetchMock, 'GET', '/reportes/saldos/proveedores').map((l) => l.url.search)
      expect(busquedas).toContain('?saldo=A_FAVOR&estado=INACTIVO')
    })
  })
})

describe('ReportesArea: la pestaña de saldos de proveedores según la regla compuesta (D8 = B, SEG-06)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
  })

  function montarArea(rol: RolDePrueba, ruta: string) {
    enrutar(apiFetchMock, [
      ...reglas(),
      { ruta: '/reportes/ventas', responder: () => ({ status: 200, cuerpo: reporteDeVentas(false) }) },
    ])
    return render(
      <QueryClientProvider client={queryClientConYo(rol)}>
        <MemoryRouter initialEntries={[ruta]}>
          <Routes>
            <Route path="/admin/reportes/*" element={<ReportesArea />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    )
  }

  it('Consulta/Dirección abre «Saldos de proveedores» y se pide el reporte', async () => {
    montarArea('CON', '/admin/reportes/saldos-proveedores')

    expect(await screen.findByRole('table', { name: 'Saldos de proveedores' })).toBeInTheDocument()
    expect(llamadas(apiFetchMock, 'GET', '/reportes/saldos/proveedores')).toHaveLength(1)
  })

  it('el Supervisor, que entra por la URL, no ve la pestaña ni se pide el reporte de proveedores', async () => {
    montarArea('SUP', '/admin/reportes/saldos-proveedores')

    expect(await screen.findByRole('heading', { name: 'Reportes' })).toBeInTheDocument()
    await waitFor(() => {
      expect(screen.queryByRole('link', { name: 'Saldos de proveedores' })).not.toBeInTheDocument()
    })
    expect(screen.queryByRole('table', { name: 'Saldos de proveedores' })).not.toBeInTheDocument()
    expect(llamadas(apiFetchMock, 'GET', '/reportes/saldos/proveedores')).toHaveLength(0)
  })

  it('«Saldos de clientes» abre desde la pestaña para el Supervisor', async () => {
    montarArea('SUP', '/admin/reportes/saldos-clientes')

    expect(await screen.findByRole('table', { name: 'Saldos de clientes' })).toBeInTheDocument()
    expect(llamadas(apiFetchMock, 'GET', '/reportes/saldos/proveedores')).toHaveLength(0)
  })
})

/**
 * Change 26, tarea 21.8 (spec `reportes/area-de-reportes`, «La navegación entre páginas en `/admin`»; D14): los
 * saldos van en páginas, con «Total adeudado» y «Total a favor» de todo lo filtrado.
 */
function reglasPaginadas(): ReglaDeApi[] {
  const paginar = (cuerpo: Record<string, unknown>, lista: 'clientes' | 'proveedores', pagina: number) => ({
    ...cuerpo,
    [lista]: { ...(cuerpo[lista] as object), pagina, paginas: 3, total_filas: 120 },
  })
  return [
    {
      ruta: '/reportes/saldos/clientes',
      responder: (url) => ({
        status: 200,
        cuerpo: paginar(reporteDeSaldosDeClientes() as unknown as Record<string, unknown>, 'clientes', Number(url.searchParams.get('pagina') ?? '1')),
      }),
    },
    {
      ruta: '/reportes/saldos/proveedores',
      responder: (url) => ({
        status: 200,
        cuerpo: paginar(reporteDeSaldosDeProveedores() as unknown as Record<string, unknown>, 'proveedores', Number(url.searchParams.get('pagina') ?? '1')),
      }),
    },
  ]
}

const buscar = (lista: 'clientes' | 'proveedores') =>
  llamadas(apiFetchMock, 'GET', `/reportes/saldos/${lista}`).map((l) => l.url.search)

describe('Saldos: paginación (D14)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
  })

  it('«Saldos de clientes» pagina con «Siguiente» y los totales no cambian', async () => {
    enrutar(apiFetchMock, reglasPaginadas())
    const usuario = userEvent.setup()
    montar('GES', 'clientes')
    await screen.findByRole('table', { name: 'Saldos de clientes' })
    const nav = () => screen.getByRole('navigation', { name: 'Paginación de Saldos de clientes' })
    expect(within(nav()).getByText('Página 1 de 3')).toBeInTheDocument()
    expect(screen.getByText('Total adeudado').nextElementSibling).toHaveTextContent('1.000,00')

    await usuario.click(within(nav()).getByRole('button', { name: 'Siguiente' }))

    await waitFor(() => expect(buscar('clientes')).toContain('?pagina=2'))
    expect(await within(nav()).findByText('Página 2 de 3')).toBeInTheDocument()
    expect(screen.getByText('Total adeudado').nextElementSibling).toHaveTextContent('1.000,00')
    expect(screen.getByText('Total a favor').nextElementSibling).toHaveTextContent('200,00')
  })

  it('cambiar el saldo o buscar vuelve a la página 1', async () => {
    enrutar(apiFetchMock, reglasPaginadas())
    const usuario = userEvent.setup()
    montar('GES', 'clientes')
    await screen.findByRole('table', { name: 'Saldos de clientes' })
    await usuario.click(within(screen.getByRole('navigation', { name: 'Paginación de Saldos de clientes' })).getByRole('button', { name: 'Siguiente' }))
    await waitFor(() => expect(buscar('clientes')).toContain('?pagina=2'))

    await usuario.selectOptions(screen.getByLabelText('Saldo'), 'DEUDORES')
    await waitFor(() => expect(buscar('clientes')).toContain('?saldo=DEUDORES'))
    await usuario.click(within(screen.getByRole('navigation', { name: 'Paginación de Saldos de clientes' })).getByRole('button', { name: 'Siguiente' }))
    await waitFor(() => expect(buscar('clientes')).toContain('?saldo=DEUDORES&pagina=2'))
    await usuario.type(screen.getByLabelText('Buscar'), 'Alma')

    await waitFor(() => expect(buscar('clientes')).toContain('?saldo=DEUDORES&texto=Alma'))
  })

  it('«Saldos de proveedores» pagina con su propio parámetro', async () => {
    enrutar(apiFetchMock, reglasPaginadas())
    const usuario = userEvent.setup()
    montar('GES', 'proveedores')
    await screen.findByRole('table', { name: 'Saldos de proveedores' })
    const nav = () => screen.getByRole('navigation', { name: 'Paginación de Saldos de proveedores' })

    await usuario.click(within(nav()).getByRole('button', { name: 'Siguiente' }))

    await waitFor(() => expect(buscar('proveedores')).toContain('?pagina=2'))
    expect(await within(nav()).findByText('Página 2 de 3')).toBeInTheDocument()
  })

  it('con una sola página no hay navegación', async () => {
    enrutar(apiFetchMock, reglas())
    montar('GES', 'clientes')

    await screen.findByRole('table', { name: 'Saldos de clientes' })
    expect(screen.queryByRole('navigation')).not.toBeInTheDocument()
  })
})
