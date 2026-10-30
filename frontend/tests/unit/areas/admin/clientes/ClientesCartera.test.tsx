/**
 * Change 20b, tarea 10.3 (D13, D14, D15; spec `clientes/cartera-de-clientes`; `01` §19, CLI-03,
 * ADR-052, INV-01, INV-06, SEG-06): la cartera en las pantallas de clientes: columna y filtro de
 * vendedor, asignación múltiple, selector en la ficha y marca del vendedor de baja o sin permiso.
 * El servidor valida igual (`VENDEDOR_INVALIDO`).
 */

import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }))
vi.mock('../../../../../src/lib/api/httpClient', () => ({ apiFetch: apiFetchMock }))

import { ClienteFormScreen } from '../../../../../src/areas/admin/clientes/ClienteFormScreen'
import { ClientesListScreen } from '../../../../../src/areas/admin/clientes/ClientesListScreen'
import { enrutar, llamadas, type ReglaDeApi } from '../../../utils/enrutarApi'
import { queryClientConYo, type RolDePrueba } from '../../../utils/permisosDePrueba'

const ANA = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
const BETO = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb'

function cliente(id: string, nombre: string, extra: Record<string, unknown> = {}) {
  return {
    id,
    codigo: null,
    nombre,
    razon_social: null,
    documento_tipo: null,
    documento_numero: null,
    direccion: 'Calle 1',
    contacto: 'Rocío',
    telefono: null,
    email: null,
    lista_precio_id: null,
    vendedor_id: null,
    vendedor_nombre: null,
    vendedor_valido: null,
    limite_credito: null,
    politica_credito: null,
    tolerancia_offline_tipo: null,
    tolerancia_offline_valor: null,
    estado_facturacion_default: null,
    es_consumidor_final: false,
    estado: 'ACTIVO',
    creado_en: '2026-01-01T00:00:00Z',
    actualizado_en: '2026-01-01T00:00:00Z',
    ...extra,
  }
}

const KIOSCO = '11111111-1111-4111-8111-111111111111'
const ALMACEN = '22222222-2222-4222-8222-222222222222'
const BAR = '55555555-5555-4555-8555-555555555555'
const CONSUMIDOR = '66666666-6666-4666-8666-666666666666'

let clientes: ReturnType<typeof cliente>[]
let sinAccesoAUsuarios: boolean

const DORA = 'u-dora'
const USUARIOS = [
  { id: ANA, nombre: 'Ana' },
  { id: BETO, nombre: 'Beto' },
]

function servidor(alAsignar?: ReglaDeApi['responder']) {
  enrutar(apiFetchMock, [
    {
      metodo: 'GET',
      ruta: '/clientes',
      responder: (url) => {
        const vendedor = url.searchParams.get('vendedor_id')
        const sin = url.searchParams.get('sin_vendedor') === 'true'
        return {
          status: 200,
          cuerpo: {
            items: clientes.filter((c) => (!vendedor || c.vendedor_id === vendedor) && (!sin || c.vendedor_id === null)),
            cursor_siguiente: null,
          },
        }
      },
    },
    {
      // Change 20b, tarea 10.3: la lista sale de `GET /clientes/vendedores` (`GESTIONAR_CLIENTES`),
      // no de las lecturas de usuarios y roles (`ADMIN_USUARIOS`).
      metodo: 'GET',
      ruta: '/clientes/vendedores',
      responder: () =>
        sinAccesoAUsuarios
          ? { status: 403, cuerpo: { title: 'Sin permiso', codigo: 'PERMISO_REQUERIDO' } }
          : { status: 200, cuerpo: [{ id: ANA, nombre: 'Ana' }, { id: DORA, nombre: 'Dóra' }] },
    },
    {
      metodo: 'GET',
      ruta: /^\/clientes\/[^/]+$/,
      responder: (url) => {
        const encontrado = clientes.find((c) => c.id === url.pathname.split('/')[2])
        return encontrado ? { status: 200, cuerpo: encontrado } : { status: 404, cuerpo: { title: 'No existe', codigo: 'RECURSO_NO_ENCONTRADO' } }
      },
    },
    {
      metodo: 'POST',
      ruta: '/clientes/vendedor',
      responder:
        alAsignar ??
        ((_url, init) => {
          const datos = JSON.parse(String(init?.body)) as { cliente_ids: string[]; vendedor_id: string | null }
          const elegido = USUARIOS.find((u) => u.id === datos.vendedor_id)
          clientes = clientes.map((c) =>
            datos.cliente_ids.includes(c.id)
              ? { ...c, vendedor_id: datos.vendedor_id, vendedor_nombre: elegido?.nombre ?? null, vendedor_valido: datos.vendedor_id === null ? null : true }
              : c,
          )
          return { status: 200, cuerpo: { vendedor_id: datos.vendedor_id, cliente_ids: datos.cliente_ids, cambiados: datos.cliente_ids.length } }
        }),
    },
  ])
}

function montarListado(rol: RolDePrueba = 'GES', ruta = '/admin/clientes') {
  return render(
    <QueryClientProvider client={queryClientConYo(rol, { permisos: ['GESTIONAR_CLIENTES'] } as never)}>
      <MemoryRouter initialEntries={[ruta]}>
        <Routes>
          <Route path="/admin/clientes" element={<ClientesListScreen />} />
          <Route path="/admin/clientes/:clienteId" element={<p>Ficha de cliente</p>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

function montarFicha(id: string) {
  return render(
    <QueryClientProvider client={queryClientConYo('GES', { permisos: ['GESTIONAR_CLIENTES'] } as never)}>
      <MemoryRouter initialEntries={[`/admin/clientes/${id}`]}>
        <Routes>
          <Route path="/admin/clientes/:clienteId" element={<ClienteFormScreen />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

const filaDe = (nombre: string) => screen.getByText(nombre).closest('tr') as HTMLElement
const cuerpoDe = (envio: { init: RequestInit }) => JSON.parse(String(envio.init.body)) as Record<string, unknown>
const operationId = (envio: { init: RequestInit }) => new Headers(envio.init.headers).get('Operation-Id')

describe('cartera en las pantallas de clientes (tarea 10.3)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
    Object.defineProperty(window.navigator, 'onLine', { value: true, configurable: true })
    sinAccesoAUsuarios = false
    clientes = [
      cliente(KIOSCO, 'Kiosco La Esquina', { vendedor_id: ANA, vendedor_nombre: 'Ana', vendedor_valido: true }),
      cliente(ALMACEN, 'Almacén Don Pepe'),
      cliente(BAR, 'Bar Central', { vendedor_id: BETO, vendedor_nombre: 'Beto', vendedor_valido: false }),
      cliente(CONSUMIDOR, 'Consumidor final', { es_consumidor_final: true }),
    ]
  })
  afterEach(() => {
    vi.clearAllMocks()
  })

  describe('listado: columna y filtro de vendedor', () => {
    it('muestra el vendedor de cada cliente, "Sin vendedor" y marca al de baja o sin permiso para reasignar', async () => {
      servidor()
      montarListado()

      await screen.findByText('Kiosco La Esquina')
      expect(within(filaDe('Kiosco La Esquina')).getByText('Ana')).toBeInTheDocument()
      expect(within(filaDe('Almacén Don Pepe')).getByText('Sin vendedor')).toBeInTheDocument()
      expect(within(filaDe('Bar Central')).getByText('Beto (de baja o sin permiso)')).toBeInTheDocument()
    })

    it('el filtro ofrece "Sin vendedor" y solo a los vendedores que pueden serlo', async () => {
      servidor()
      montarListado()

      const filtro = await screen.findByLabelText('Vendedor')
      await waitFor(() => expect(within(filtro).getByRole('option', { name: 'Ana' })).toBeInTheDocument())
      expect(within(filtro).getByRole('option', { name: 'Sin vendedor' })).toBeInTheDocument()
      expect(within(filtro).queryByRole('option', { name: 'Beto' })).not.toBeInTheDocument()
      expect(within(filtro).queryByRole('option', { name: 'Carla' })).not.toBeInTheDocument()
    })

    it('filtrar por un vendedor pide vendedor_id y "Sin vendedor" pide sin_vendedor', async () => {
      const usuario = userEvent.setup()
      servidor()
      montarListado()
      const filtro = await screen.findByLabelText('Vendedor')
      await waitFor(() => expect(within(filtro).getByRole('option', { name: 'Ana' })).toBeInTheDocument())

      await usuario.selectOptions(filtro, ANA)
      await waitFor(() => expect(llamadas(apiFetchMock, 'GET', '/clientes').some((c) => c.url.searchParams.get('vendedor_id') === ANA)).toBe(true))
      await waitFor(() => expect(screen.queryByText('Almacén Don Pepe')).not.toBeInTheDocument())

      await usuario.selectOptions(filtro, 'sin')
      await waitFor(() => expect(llamadas(apiFetchMock, 'GET', '/clientes').some((c) => c.url.searchParams.get('sin_vendedor') === 'true')).toBe(true))
      expect(await screen.findByText('Almacén Don Pepe')).toBeInTheDocument()
      expect(screen.queryByText('Kiosco La Esquina')).not.toBeInTheDocument()
    })

    it('entra con el filtro de la ficha del usuario (?vendedor_id=) ya aplicado, aunque ese vendedor ya no sea elegible', async () => {
      servidor()
      montarListado('GES', `/admin/clientes?vendedor_id=${BETO}`)

      expect(await screen.findByText('Bar Central')).toBeInTheDocument()
      expect(screen.queryByText('Kiosco La Esquina')).not.toBeInTheDocument()
      expect(llamadas(apiFetchMock, 'GET', '/clientes')[0]?.url.searchParams.get('vendedor_id')).toBe(BETO)
    })

    it('sin acceso a la lista de usuarios el filtro por vendedor sigue ofreciendo "Sin vendedor" y avisa', async () => {
      sinAccesoAUsuarios = true
      servidor()
      montarListado()

      const filtro = await screen.findByLabelText('Vendedor')
      expect(within(filtro).getByRole('option', { name: 'Sin vendedor' })).toBeInTheDocument()
      expect(await screen.findByText(/no podés ver la lista de vendedores/i)).toBeInTheDocument()
    })
  })

  describe('listado: "Asignar vendedor" a varios clientes (D15)', () => {
    async function marcar(usuario: ReturnType<typeof userEvent.setup>, ...nombres: string[]) {
      for (const nombre of nombres) await usuario.click(within(filaDe(nombre)).getByRole('checkbox'))
    }

    it('no se puede elegir al consumidor final: lo ven todos', async () => {
      servidor()
      montarListado()

      await screen.findByText('Kiosco La Esquina')
      const fila = screen.getByRole('link', { name: 'Consumidor final' }).closest('tr') as HTMLElement
      expect(within(fila).getByRole('checkbox')).toBeDisabled()
    })

    it('"Asignar vendedor" está deshabilitado sin clientes marcados y muestra cuántos se marcaron', async () => {
      const usuario = userEvent.setup()
      servidor()
      montarListado()

      await screen.findByText('Kiosco La Esquina')
      expect(screen.getByRole('button', { name: 'Asignar vendedor' })).toBeDisabled()
      await marcar(usuario, 'Kiosco La Esquina', 'Almacén Don Pepe')

      expect(screen.getByRole('button', { name: 'Asignar vendedor' })).toBeEnabled()
      expect(screen.getByText('2 clientes marcados')).toBeInTheDocument()
    })

    it('asigna al vendedor elegido a los clientes marcados con un solo comando y Operation-Id', async () => {
      const usuario = userEvent.setup()
      servidor()
      montarListado()

      await screen.findByText('Almacén Don Pepe')
      await marcar(usuario, 'Almacén Don Pepe', 'Bar Central')
      await usuario.click(screen.getByRole('button', { name: 'Asignar vendedor' }))
      const dialogo = await screen.findByRole('dialog', { name: /asignar vendedor/i })
      await waitFor(() => expect(within(dialogo).getByRole('option', { name: 'Ana' })).toBeInTheDocument())
      await usuario.click(await within(dialogo).findByRole('option', { name: 'Ana' }))
      await usuario.click(within(dialogo).getByRole('button', { name: 'Confirmar asignación' }))

      await waitFor(() => expect(llamadas(apiFetchMock, 'POST', '/clientes/vendedor')).toHaveLength(1))
      const envio = llamadas(apiFetchMock, 'POST', '/clientes/vendedor')[0]!
      expect(cuerpoDe(envio)).toEqual({ cliente_ids: [ALMACEN, BAR], vendedor_id: ANA })
      expect(operationId(envio)).toBeTruthy()
      await waitFor(() => expect(within(filaDe('Almacén Don Pepe')).getByText('Ana')).toBeInTheDocument())
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    })

    it('el buscador del diálogo filtra por nombre, ignora mayúsculas y conserva "Quitar vendedor"', async () => {
      const usuario = userEvent.setup()
      servidor()
      montarListado('GES')

      await screen.findByText('Kiosco La Esquina')
      await marcar(usuario, 'Kiosco La Esquina')
      await usuario.click(screen.getByRole('button', { name: 'Asignar vendedor' }))
      const dialogo = await screen.findByRole('dialog', { name: /asignar vendedor/i })
      await waitFor(() => expect(within(within(dialogo).getByLabelText('Vendedor')).getByRole('option', { name: 'Ana' })).toBeInTheDocument())

      await usuario.type(within(dialogo).getByLabelText('Buscar vendedor'), 'ANA')
      const selector = within(dialogo).getByLabelText('Vendedor')
      expect(within(selector).getByRole('option', { name: 'Ana' })).toBeInTheDocument()
      expect(within(selector).queryByRole('option', { name: 'Dóra' })).not.toBeInTheDocument()
      expect(within(selector).getByRole('option', { name: 'Quitar vendedor' })).toBeInTheDocument()
    })

    it('el diálogo muestra las coincidencias a la vista, deja "Quitar vendedor" y avisa si ninguna coincide', async () => {
      const usuario = userEvent.setup()
      servidor()
      montarListado('GES')

      await screen.findByText('Kiosco La Esquina')
      await marcar(usuario, 'Kiosco La Esquina')
      await usuario.click(screen.getByRole('button', { name: 'Asignar vendedor' }))
      const dialogo = await screen.findByRole('dialog', { name: /asignar vendedor/i })
      const lista = await within(dialogo).findByRole('listbox', { name: 'Vendedor' })
      await waitFor(() => expect(within(lista).getByRole('option', { name: 'Dóra' })).toBeInTheDocument())

      await usuario.type(within(dialogo).getByLabelText('Buscar vendedor'), 'zzz')
      expect(within(lista).getAllByRole('option').map((o) => o.textContent)).toEqual(['Quitar vendedor'])
      expect(within(dialogo).getByText('Ningún vendedor coincide con la búsqueda.')).toBeInTheDocument()
    })

    it('"Quitar vendedor" manda null', async () => {
      const usuario = userEvent.setup()
      servidor()
      montarListado()

      await screen.findByText('Kiosco La Esquina')
      await marcar(usuario, 'Kiosco La Esquina')
      await usuario.click(screen.getByRole('button', { name: 'Asignar vendedor' }))
      const dialogo = await screen.findByRole('dialog', { name: /asignar vendedor/i })
      await usuario.click(await within(dialogo).findByRole('option', { name: 'Quitar vendedor' }))
      await usuario.click(within(dialogo).getByRole('button', { name: 'Confirmar asignación' }))

      await waitFor(() => expect(llamadas(apiFetchMock, 'POST', '/clientes/vendedor')).toHaveLength(1))
      expect(cuerpoDe(llamadas(apiFetchMock, 'POST', '/clientes/vendedor')[0]!)).toEqual({ cliente_ids: [KIOSCO], vendedor_id: null })
    })

    it('explica VENDEDOR_INVALIDO y no cierra el diálogo ni cambia nada', async () => {
      const usuario = userEvent.setup()
      servidor(() => ({ status: 409, cuerpo: { title: 'x', codigo: 'VENDEDOR_INVALIDO' } }))
      montarListado()

      await screen.findByText('Almacén Don Pepe')
      await marcar(usuario, 'Almacén Don Pepe')
      await usuario.click(screen.getByRole('button', { name: 'Asignar vendedor' }))
      const dialogo = await screen.findByRole('dialog', { name: /asignar vendedor/i })
      await waitFor(() => expect(within(dialogo).getByRole('option', { name: 'Ana' })).toBeInTheDocument())
      await usuario.click(await within(dialogo).findByRole('option', { name: 'Ana' }))
      await usuario.click(within(dialogo).getByRole('button', { name: 'Confirmar asignación' }))

      expect(await within(dialogo).findByText(/no puede ser vendedor/i)).toBeInTheDocument()
      expect(within(filaDe('Almacén Don Pepe')).getByText('Sin vendedor')).toBeInTheDocument()
    })

    it('tras un corte de red el reintento reenvía el mismo Operation-Id', async () => {
      const usuario = userEvent.setup()
      let cortar = true
      servidor(() => {
        if (cortar) throw new TypeError('Failed to fetch')
        return { status: 200, cuerpo: { vendedor_id: ANA, cliente_ids: [ALMACEN], cambiados: 1 } }
      })
      montarListado()

      await screen.findByText('Almacén Don Pepe')
      await marcar(usuario, 'Almacén Don Pepe')
      await usuario.click(screen.getByRole('button', { name: 'Asignar vendedor' }))
      const dialogo = await screen.findByRole('dialog', { name: /asignar vendedor/i })
      await waitFor(() => expect(within(dialogo).getByRole('option', { name: 'Ana' })).toBeInTheDocument())
      await usuario.click(await within(dialogo).findByRole('option', { name: 'Ana' }))
      await usuario.click(within(dialogo).getByRole('button', { name: 'Confirmar asignación' }))
      expect(await within(dialogo).findByText(/se necesita conexión/i)).toBeInTheDocument()
      cortar = false
      await usuario.click(within(dialogo).getByRole('button', { name: 'Confirmar asignación' }))

      await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
      expect(new Set(llamadas(apiFetchMock, 'POST', '/clientes/vendedor').map(operationId)).size).toBe(1)
    })

    it('ofrece la ayuda del vendedor del cliente', async () => {
      servidor()
      montarListado()

      await screen.findByText('Kiosco La Esquina')
      expect(screen.getByRole('button', { name: 'Ayuda: Vendedor del cliente' })).toBeInTheDocument()
    })
  })

  describe('ficha del cliente: selector de vendedor (D15)', () => {
    it('muestra el vendedor actual y deja cambiarlo con su propio comando (CLIENTE_MODIFICAR no cambia)', async () => {
      const usuario = userEvent.setup()
      servidor()
      montarFicha(ALMACEN)

      const selector = await screen.findByLabelText('Vendedor')
      await waitFor(() => expect(within(selector).getByRole('option', { name: 'Ana' })).toBeInTheDocument())
      expect(within(selector).getByRole('option', { name: 'Sin vendedor' })).toHaveAttribute('aria-selected', 'true')
      await usuario.click(within(selector).getByRole('option', { name: 'Ana' }))
      await usuario.click(screen.getByRole('button', { name: 'Guardar vendedor' }))

      await waitFor(() => expect(llamadas(apiFetchMock, 'POST', '/clientes/vendedor')).toHaveLength(1))
      expect(cuerpoDe(llamadas(apiFetchMock, 'POST', '/clientes/vendedor')[0]!)).toEqual({ cliente_ids: [ALMACEN], vendedor_id: ANA })
      expect(llamadas(apiFetchMock, 'PUT', /^\/clientes\/[^/]+$/)).toHaveLength(0)
    })

    it('marca al vendedor dado de baja o sin permiso y lo conserva como opción actual', async () => {
      servidor()
      montarFicha(BAR)

      const selector = await screen.findByLabelText('Vendedor')
      expect(await screen.findByText(/dado de baja o sin permiso: reasignalo/i)).toBeInTheDocument()
      expect(within(selector).getByRole('option', { name: 'Beto (de baja o sin permiso)' })).toBeInTheDocument()
      expect(within(selector).getByRole('option', { name: 'Beto (de baja o sin permiso)' })).toHaveAttribute('aria-selected', 'true')
    })

    it('quitar el vendedor manda null', async () => {
      const usuario = userEvent.setup()
      servidor()
      montarFicha(KIOSCO)

      const selector = await screen.findByLabelText('Vendedor')
      await waitFor(() => expect(within(selector).getByRole('option', { name: 'Ana' })).toBeInTheDocument())
      await usuario.click(within(selector).getByRole('option', { name: 'Sin vendedor' }))
      await usuario.click(screen.getByRole('button', { name: 'Guardar vendedor' }))

      await waitFor(() => expect(llamadas(apiFetchMock, 'POST', '/clientes/vendedor')).toHaveLength(1))
      expect(cuerpoDe(llamadas(apiFetchMock, 'POST', '/clientes/vendedor')[0]!)).toEqual({ cliente_ids: [KIOSCO], vendedor_id: null })
    })

    it('el buscador filtra la lista por nombre sin importar mayúsculas y deja "Sin vendedor" y el actual', async () => {
      const usuario = userEvent.setup()
      servidor()
      montarFicha(KIOSCO)

      const selector = await screen.findByLabelText('Vendedor')
      await waitFor(() => expect(within(selector).getByRole('option', { name: 'Dóra' })).toBeInTheDocument())
      await usuario.type(screen.getByLabelText('Buscar vendedor'), 'DORA')

      expect(within(selector).getByRole('option', { name: 'Dóra' })).toBeInTheDocument()
      expect(within(selector).getByRole('option', { name: 'Sin vendedor' })).toBeInTheDocument()
      // Ana es la vendedora actual del cliente: no desaparece del selector.
      expect(within(selector).getByRole('option', { name: 'Ana' })).toBeInTheDocument()
      expect(within(selector).getByRole('option', { name: 'Ana' })).toHaveAttribute('aria-selected', 'true')

      await usuario.clear(screen.getByLabelText('Buscar vendedor'))
      await usuario.type(screen.getByLabelText('Buscar vendedor'), 'zzz')
      expect(within(selector).queryByRole('option', { name: 'Dóra' })).not.toBeInTheDocument()
      expect(screen.getByText(/ningún vendedor coincide/i)).toBeInTheDocument()
    })

    it('al escribir en el buscador las coincidencias quedan a la vista y se elige tocándolas, sin abrir nada', async () => {
      const usuario = userEvent.setup()
      servidor()
      montarFicha(ALMACEN)

      const selector = await screen.findByLabelText('Vendedor')
      expect(selector).toHaveAttribute('role', 'listbox')
      await waitFor(() => expect(within(selector).getByRole('option', { name: 'Dóra' })).toBeInTheDocument())
      await usuario.type(screen.getByLabelText('Buscar vendedor'), 'dor')

      expect(within(selector).getAllByRole('option').map((o) => o.textContent?.replace('✓', ''))).toEqual(['Sin vendedor', 'Dóra'])
      await usuario.click(within(selector).getByRole('option', { name: 'Dóra' }))
      expect(within(selector).getByRole('option', { name: 'Dóra' })).toHaveAttribute('aria-selected', 'true')
      expect(within(selector).getByRole('option', { name: 'Sin vendedor' })).toHaveAttribute('aria-selected', 'false')
    })

    it('se elige con el teclado: flechas para moverse y Enter para elegir', async () => {
      const usuario = userEvent.setup()
      servidor()
      montarFicha(ALMACEN)

      const selector = await screen.findByLabelText('Vendedor')
      await waitFor(() => expect(within(selector).getByRole('option', { name: 'Ana' })).toBeInTheDocument())
      within(selector).getByRole('option', { name: 'Sin vendedor' }).focus()
      await usuario.keyboard('{ArrowDown}{Enter}')

      const segunda = within(selector).getAllByRole('option')[1]!
      expect(segunda).toHaveAttribute('aria-selected', 'true')
    })

    it('el consumidor final no tiene selector: lo ven todos', async () => {
      servidor()
      montarFicha(CONSUMIDOR)

      expect(await screen.findByText(/el consumidor final no se asigna a ningún vendedor/i)).toBeInTheDocument()
      expect(screen.queryByRole('button', { name: 'Guardar vendedor' })).not.toBeInTheDocument()
    })
  })
})
