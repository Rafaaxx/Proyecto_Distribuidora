/**
 * Change 20b, tarea 10.2 (gobernanza CRÍTICA; spec `identidad/administracion-de-roles`;
 * `design.md` D10, D11, D16; ADR-028, ADR-053, INV-01, INV-06, SEG-06): crear, renombrar, dar de
 * baja y reactivar roles desde "Roles y permisos". El servidor valida igual.
 */

import { QueryClientProvider, type QueryClient } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }))
vi.mock('../../../../../src/lib/api/httpClient', () => ({ apiFetch: apiFetchMock }))

import RolesArea from '../../../../../src/areas/admin/roles/RolesArea'
import { clavesIdentidad } from '../../../../../src/features/identidad/claves'
import { enrutar, llamadas, type ReglaDeApi } from '../../../utils/enrutarApi'
import { queryClientConYo } from '../../../utils/permisosDePrueba'

const ADMINISTRADOR = '11111111-1111-4111-8111-111111111111'
const VENDEDOR = '33333333-3333-4333-8333-333333333333'
const REPARTIDOR = '55555555-5555-4555-8555-555555555555'
const VIEJO = '66666666-6666-4666-8666-666666666666'

interface RolDeApi {
  id: string
  nombre: string
  activo: boolean
  tope_descuento: string
  permisos: string[]
  usuarios_activos: number
  usuarios_con_tope_propio: number
  usuarios_con_tope_propio_activos: number
  usuarios_con_tope_propio_inactivos: number
}

function rolDeApi(id: string, nombre: string, permisos: string[], usuarios: number, activo = true): RolDeApi {
  return {
    id,
    nombre,
    activo,
    tope_descuento: '0.000000',
    permisos,
    usuarios_activos: usuarios,
    usuarios_con_tope_propio: 0,
    usuarios_con_tope_propio_activos: 0,
    usuarios_con_tope_propio_inactivos: 0,
  }
}

let roles: RolDeApi[]
let queryClient: QueryClient

const CATALOGO = [
  { codigo: 'ADMIN_USUARIOS', descripcion: 'Usuarios, roles y permisos', modulo: 'identidad' },
  { codigo: 'VENDER', descripcion: 'Confirmar ventas', modulo: 'ventas' },
  { codigo: 'REGISTRAR_COBRANZA', descripcion: 'Registrar cobranzas', modulo: 'cobranzas' },
]

function servidor(alEscribir: Partial<Record<'crear' | 'renombrar' | 'baja' | 'reactivar', ReglaDeApi['responder']>> = {}) {
  const idDe = (url: URL) => url.pathname.split('/')[3] as string
  const cuerpo = (init: RequestInit | undefined) => JSON.parse(String(init?.body ?? '{}')) as Record<string, unknown>
  enrutar(apiFetchMock, [
    { metodo: 'GET', ruta: '/yo', responder: () => ({ status: 200, cuerpo: queryClient.getQueryData(clavesIdentidad.yo()) }) },
    { metodo: 'GET', ruta: '/identidad/roles', responder: () => ({ status: 200, cuerpo: roles }) },
    { metodo: 'GET', ruta: '/identidad/permisos', responder: () => ({ status: 200, cuerpo: CATALOGO }) },
    {
      metodo: 'POST',
      ruta: '/identidad/roles',
      responder:
        alEscribir.crear ??
        ((_url, init) => {
          const datos = cuerpo(init)
          const nuevo = rolDeApi(REPARTIDOR, String(datos.nombre), datos.permisos as string[], 0)
          roles = [...roles, nuevo]
          return { status: 201, cuerpo: nuevo }
        }),
    },
    {
      metodo: 'PUT',
      ruta: /^\/identidad\/roles\/[^/]+\/nombre$/,
      responder:
        alEscribir.renombrar ??
        ((url, init) => {
          roles = roles.map((r) => (r.id === idDe(url) ? { ...r, nombre: String(cuerpo(init).nombre) } : r))
          return { status: 200, cuerpo: roles.find((r) => r.id === idDe(url)) }
        }),
    },
    {
      metodo: 'POST',
      ruta: /^\/identidad\/roles\/[^/]+\/baja$/,
      responder:
        alEscribir.baja ??
        ((url) => {
          roles = roles.map((r) => (r.id === idDe(url) ? { ...r, activo: false } : r))
          return { status: 200, cuerpo: roles.find((r) => r.id === idDe(url)) }
        }),
    },
    {
      metodo: 'POST',
      ruta: /^\/identidad\/roles\/[^/]+\/reactivacion$/,
      responder:
        alEscribir.reactivar ??
        ((url) => {
          roles = roles.map((r) => (r.id === idDe(url) ? { ...r, activo: true } : r))
          return { status: 200, cuerpo: roles.find((r) => r.id === idDe(url)) }
        }),
    },
  ])
}

function montar() {
  queryClient = queryClientConYo('ADM', { rol: { id: ADMINISTRADOR, nombre: 'Administrador' } })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/admin/roles']}>
        <Routes>
          <Route path="/admin/roles/*" element={<RolesArea />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

const filaDe = (nombre: string) => screen.getByText(nombre).closest('tr') as HTMLElement
const operationId = (envio: { init: RequestInit }) => new Headers(envio.init.headers).get('Operation-Id')
const cuerpoDe = (envio: { init: RequestInit }) => JSON.parse(String(envio.init.body)) as Record<string, unknown>

describe('Roles y permisos: crear, renombrar, dar de baja y reactivar (tarea 10.2)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
    Object.defineProperty(window.navigator, 'onLine', { value: true, configurable: true })
    roles = [
      rolDeApi(ADMINISTRADOR, 'Administrador', ['ADMIN_USUARIOS', 'VENDER', 'REGISTRAR_COBRANZA'], 1),
      rolDeApi(VENDEDOR, 'Vendedor/Repartidor', ['VENDER', 'REGISTRAR_COBRANZA'], 3),
      rolDeApi(VIEJO, 'Rol viejo', ['VENDER'], 0, false),
    ]
  })
  afterEach(() => {
    vi.clearAllMocks()
  })

  describe('estado de cada rol (D11)', () => {
    it('marca "De baja" al rol inactivo y ofrece reactivarlo, no darlo de baja', async () => {
      servidor()
      montar()

      await screen.findByText('Rol viejo')
      expect(within(filaDe('Rol viejo')).getByText('De baja')).toBeInTheDocument()
      expect(within(filaDe('Rol viejo')).getByRole('button', { name: 'Reactivar Rol viejo' })).toBeInTheDocument()
      expect(within(filaDe('Rol viejo')).queryByRole('button', { name: /dar de baja/i })).not.toBeInTheDocument()
      expect(within(filaDe('Vendedor/Repartidor')).getByText('Activo')).toBeInTheDocument()
      expect(within(filaDe('Vendedor/Repartidor')).getByRole('button', { name: 'Dar de baja Vendedor/Repartidor' })).toBeInTheDocument()
    })
  })

  describe('"Nuevo rol" (D10)', () => {
    it('crea un rol copiando los permisos de otro y manda la lista al comando', async () => {
      const usuario = userEvent.setup()
      servidor()
      montar()

      await usuario.click(await screen.findByRole('button', { name: 'Nuevo rol' }))
      const dialogo = await screen.findByRole('dialog', { name: 'Nuevo rol' })
      await usuario.type(within(dialogo).getByLabelText('Nombre del rol'), '  Repartidor ')
      await usuario.selectOptions(within(dialogo).getByLabelText('Copiar permisos de'), VENDEDOR)
      await usuario.click(within(dialogo).getByRole('button', { name: 'Crear rol' }))

      await waitFor(() => expect(llamadas(apiFetchMock, 'POST', '/identidad/roles')).toHaveLength(1))
      const envio = llamadas(apiFetchMock, 'POST', '/identidad/roles')[0]!
      expect(cuerpoDe(envio)).toEqual({ nombre: 'Repartidor', permisos: ['REGISTRAR_COBRANZA', 'VENDER'] })
      expect(operationId(envio)).toBeTruthy()
      expect(await screen.findByText('Repartidor')).toBeInTheDocument()
    })

    it('sin copiar nada crea el rol sin permisos', async () => {
      const usuario = userEvent.setup()
      servidor()
      montar()

      await usuario.click(await screen.findByRole('button', { name: 'Nuevo rol' }))
      const dialogo = await screen.findByRole('dialog', { name: 'Nuevo rol' })
      await usuario.type(within(dialogo).getByLabelText('Nombre del rol'), 'Vacío')
      await usuario.click(within(dialogo).getByRole('button', { name: 'Crear rol' }))

      await waitFor(() => expect(llamadas(apiFetchMock, 'POST', '/identidad/roles')).toHaveLength(1))
      expect(cuerpoDe(llamadas(apiFetchMock, 'POST', '/identidad/roles')[0]!)).toEqual({ nombre: 'Vacío', permisos: [] })
    })

    it('el selector "Copiar permisos de" ofrece solo roles activos', async () => {
      const usuario = userEvent.setup()
      servidor()
      montar()

      await usuario.click(await screen.findByRole('button', { name: 'Nuevo rol' }))
      const selector = within(await screen.findByRole('dialog', { name: 'Nuevo rol' })).getByLabelText('Copiar permisos de')

      expect(within(selector).getByRole('option', { name: 'Vendedor/Repartidor' })).toBeInTheDocument()
      expect(within(selector).queryByRole('option', { name: 'Rol viejo' })).not.toBeInTheDocument()
    })

    it('con el nombre vacío no envía nada y lo dice', async () => {
      const usuario = userEvent.setup()
      servidor()
      montar()

      await usuario.click(await screen.findByRole('button', { name: 'Nuevo rol' }))
      await usuario.click(within(await screen.findByRole('dialog', { name: 'Nuevo rol' })).getByRole('button', { name: 'Crear rol' }))

      expect(await screen.findByText(/escribí el nombre del rol/i)).toBeInTheDocument()
      expect(llamadas(apiFetchMock, 'POST', '/identidad/roles')).toHaveLength(0)
    })

    it('explica el nombre duplicado y, al corregir el nombre, envía otra operación (otro Operation-Id)', async () => {
      const usuario = userEvent.setup()
      let primera = true
      servidor({
        crear: () => {
          if (primera) {
            primera = false
            return { status: 409, cuerpo: { title: 'dup', codigo: 'IDENTIDAD_NOMBRE_DE_ROL_DUPLICADO' } }
          }
          return { status: 201, cuerpo: rolDeApi(REPARTIDOR, 'Otro', [], 0) }
        },
      })
      montar()

      await usuario.click(await screen.findByRole('button', { name: 'Nuevo rol' }))
      const dialogo = await screen.findByRole('dialog', { name: 'Nuevo rol' })
      await usuario.type(within(dialogo).getByLabelText('Nombre del rol'), 'Vendedor/Repartidor')
      await usuario.click(within(dialogo).getByRole('button', { name: 'Crear rol' }))
      expect(await within(dialogo).findByText(/ya existe un rol con ese nombre, aunque esté dado de baja/i)).toBeInTheDocument()

      await usuario.clear(within(dialogo).getByLabelText('Nombre del rol'))
      await usuario.type(within(dialogo).getByLabelText('Nombre del rol'), 'Otro')
      await usuario.click(within(dialogo).getByRole('button', { name: 'Crear rol' }))

      await waitFor(() => expect(llamadas(apiFetchMock, 'POST', '/identidad/roles')).toHaveLength(2))
      const [uno, dos] = llamadas(apiFetchMock, 'POST', '/identidad/roles')
      expect(operationId(uno!)).not.toBe(operationId(dos!))
    })
  })

  describe('"Renombrar" (D10)', () => {
    it('cambia el nombre con el nombre recortado', async () => {
      const usuario = userEvent.setup()
      servidor()
      montar()

      await usuario.click(await screen.findByRole('button', { name: 'Renombrar Vendedor/Repartidor' }))
      const dialogo = await screen.findByRole('dialog', { name: /renombrar vendedor\/repartidor/i })
      const campo = within(dialogo).getByLabelText('Nombre del rol')
      expect(campo).toHaveValue('Vendedor/Repartidor')
      await usuario.clear(campo)
      await usuario.type(campo, ' Repartidor ')
      await usuario.click(within(dialogo).getByRole('button', { name: 'Guardar nombre' }))

      await waitFor(() => expect(llamadas(apiFetchMock, 'PUT', `/identidad/roles/${VENDEDOR}/nombre`)).toHaveLength(1))
      expect(cuerpoDe(llamadas(apiFetchMock, 'PUT', `/identidad/roles/${VENDEDOR}/nombre`)[0]!)).toEqual({ nombre: 'Repartidor' })
    })

    it('un nombre repetido se explica y no cierra el diálogo', async () => {
      const usuario = userEvent.setup()
      servidor({ renombrar: () => ({ status: 409, cuerpo: { title: 'dup', codigo: 'IDENTIDAD_NOMBRE_DE_ROL_DUPLICADO' } }) })
      montar()

      await usuario.click(await screen.findByRole('button', { name: 'Renombrar Vendedor/Repartidor' }))
      const dialogo = await screen.findByRole('dialog', { name: /renombrar/i })
      await usuario.type(within(dialogo).getByLabelText('Nombre del rol'), 'X')
      await usuario.click(within(dialogo).getByRole('button', { name: 'Guardar nombre' }))

      expect(await within(dialogo).findByText(/ya existe un rol con ese nombre/i)).toBeInTheDocument()
      expect(screen.getByRole('dialog', { name: /renombrar/i })).toBeInTheDocument()
    })
  })

  describe('"Dar de baja" (D11, ADR-028, ADR-053)', () => {
    it('un rol vacío se da de baja con confirmación y pasa a "De baja"', async () => {
      const usuario = userEvent.setup()
      roles = [...roles, rolDeApi(REPARTIDOR, 'Repartidor', [], 0)]
      servidor()
      montar()

      await usuario.click(await screen.findByRole('button', { name: 'Dar de baja Repartidor' }))
      const dialogo = await screen.findByRole('dialog', { name: /confirmar baja del rol repartidor/i })
      expect(llamadas(apiFetchMock, 'POST', `/identidad/roles/${REPARTIDOR}/baja`)).toHaveLength(0)
      await usuario.click(within(dialogo).getByRole('button', { name: 'Confirmar baja del rol' }))

      await waitFor(() => expect(llamadas(apiFetchMock, 'POST', `/identidad/roles/${REPARTIDOR}/baja`)).toHaveLength(1))
      expect(operationId(llamadas(apiFetchMock, 'POST', `/identidad/roles/${REPARTIDOR}/baja`)[0]!)).toBeTruthy()
      await waitFor(() => expect(within(filaDe('Repartidor')).getByText('De baja')).toBeInTheDocument())
    })

    it('un rol con usuarios activos se rechaza y la explicación dice cuántos son', async () => {
      const usuario = userEvent.setup()
      servidor({ baja: () => ({ status: 409, cuerpo: { title: 'x', codigo: 'IDENTIDAD_ROL_CON_USUARIOS_ACTIVOS' } }) })
      montar()

      await usuario.click(await screen.findByRole('button', { name: 'Dar de baja Vendedor/Repartidor' }))
      await usuario.click(await screen.findByRole('button', { name: 'Confirmar baja del rol' }))

      expect(await screen.findByText(/tiene 3 usuarios activos/i)).toBeInTheDocument()
      expect(within(filaDe('Vendedor/Repartidor')).getByText('Activo')).toBeInTheDocument()
    })

    it('la baja que dejaría la organización sin administrador se explica', async () => {
      const usuario = userEvent.setup()
      servidor({ baja: () => ({ status: 409, cuerpo: { title: 'x', codigo: 'IDENTIDAD_SIN_ADMINISTRADOR' } }) })
      montar()

      await usuario.click(await screen.findByRole('button', { name: 'Dar de baja Administrador' }))
      await usuario.click(await screen.findByRole('button', { name: 'Confirmar baja del rol' }))

      expect(await screen.findByText(/se quedaría sin nadie que administre usuarios y roles/i)).toBeInTheDocument()
    })

    it('tras un corte de red el reintento reenvía el mismo Operation-Id', async () => {
      const usuario = userEvent.setup()
      let cortar = true
      servidor({
        baja: (url) => {
          if (cortar) throw new TypeError('Failed to fetch')
          roles = roles.map((r) => (r.id === url.pathname.split('/')[3] ? { ...r, activo: false } : r))
          return { status: 200, cuerpo: roles[1] }
        },
      })
      montar()

      await usuario.click(await screen.findByRole('button', { name: 'Dar de baja Vendedor/Repartidor' }))
      await usuario.click(await screen.findByRole('button', { name: 'Confirmar baja del rol' }))
      expect(await screen.findByText(/se necesita conexión/i)).toBeInTheDocument()
      cortar = false
      await usuario.click(screen.getByRole('button', { name: 'Confirmar baja del rol' }))

      await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
      const envios = llamadas(apiFetchMock, 'POST', `/identidad/roles/${VENDEDOR}/baja`)
      expect(envios.length).toBeGreaterThanOrEqual(2)
      expect(new Set(envios.map(operationId)).size).toBe(1)
    })

    it('muestra la ayuda de la baja de roles', async () => {
      const usuario = userEvent.setup()
      servidor()
      montar()

      await usuario.click(await screen.findByRole('button', { name: 'Dar de baja Vendedor/Repartidor' }))
      const dialogo = await screen.findByRole('dialog', { name: /confirmar baja del rol/i })

      expect(within(dialogo).getByRole('button', { name: 'Ayuda: Dar de baja un rol' })).toBeInTheDocument()
    })
  })

  describe('"Reactivar" (D11)', () => {
    it('reactiva un rol de baja sin pedir confirmación y vuelve a estar activo', async () => {
      const usuario = userEvent.setup()
      servidor()
      montar()

      await usuario.click(await screen.findByRole('button', { name: 'Reactivar Rol viejo' }))

      await waitFor(() => expect(llamadas(apiFetchMock, 'POST', `/identidad/roles/${VIEJO}/reactivacion`)).toHaveLength(1))
      await waitFor(() => expect(within(filaDe('Rol viejo')).getByText('Activo')).toBeInTheDocument())
    })
  })
})
