/**
 * Change 20b, tarea 10.1 (gobernanza CRÍTICA; spec `identidad/administracion-de-usuarios`;
 * `design.md` D1 a D9, D12, D16; ADR-027, ADR-028, ADR-053, ADR-056, INV-01, INV-06, SEG-06):
 * área "Usuarios" de `/admin`. Solo con `ADMIN_USUARIOS`; el servidor valida igual.
 */

import { QueryClientProvider, type QueryClient } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }))
vi.mock('../../../../../src/lib/api/httpClient', () => ({ apiFetch: apiFetchMock }))

import UsuariosArea from '../../../../../src/areas/admin/usuarios/UsuariosArea'
import { clavesIdentidad } from '../../../../../src/features/identidad/claves'
import { seccionesPermitidas } from '../../../../../src/features/identidad/secciones'
import { enrutar, llamadas, type ReglaDeApi } from '../../../utils/enrutarApi'
import { PERMISOS_POR_ROL, queryClientConYo, type RolDePrueba } from '../../../utils/permisosDePrueba'

const ROL_ADMIN = '11111111-1111-4111-8111-111111111111'
const ROL_VENDEDOR = '33333333-3333-4333-8333-333333333333'
const ROL_VIEJO = '44444444-4444-4444-8444-444444444444'
const LAURA = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
const JUAN = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb'
const YO = 'cccccccc-cccc-4ccc-8ccc-cccccccccccc'
const CLAVE_A = 'clave-secreta-uno'
const CLAVE_B = 'clave-secreta-dos'

interface UsuarioDeApi {
  id: string
  usuario: string
  nombre: string
  email: string | null
  rol_id: string
  estado: string
  tiene_pin_autorizacion: boolean
  rol_nombre: string
  rol_activo: boolean
  tope_descuento_override: string | null
}

function usuario(id: string, nombreDeUsuario: string, nombre: string, rol: string, extra: Partial<UsuarioDeApi> = {}): UsuarioDeApi {
  const esAdmin = rol === ROL_ADMIN
  return {
    id,
    usuario: nombreDeUsuario,
    nombre,
    email: null,
    rol_id: rol,
    estado: 'ACTIVO',
    tiene_pin_autorizacion: false,
    rol_nombre: esAdmin ? 'Administrador' : rol === ROL_VIEJO ? 'Rol viejo' : 'Vendedor/Repartidor',
    rol_activo: rol !== ROL_VIEJO,
    tope_descuento_override: null,
    ...extra,
  }
}

const ROLES = [
  { id: ROL_ADMIN, nombre: 'Administrador', activo: true, tope_descuento: '1.000000', permisos: ['ADMIN_USUARIOS', 'DESCUENTO_MANUAL', 'VENDER'], usuarios_activos: 1, usuarios_con_tope_propio: 0, usuarios_con_tope_propio_activos: 0, usuarios_con_tope_propio_inactivos: 0 },
  { id: ROL_VENDEDOR, nombre: 'Vendedor/Repartidor', activo: true, tope_descuento: '0.050000', permisos: ['VENDER'], usuarios_activos: 2, usuarios_con_tope_propio: 1, usuarios_con_tope_propio_activos: 1, usuarios_con_tope_propio_inactivos: 0 },
  { id: ROL_VIEJO, nombre: 'Rol viejo', activo: false, tope_descuento: '0.000000', permisos: [], usuarios_activos: 0, usuarios_con_tope_propio: 0, usuarios_con_tope_propio_activos: 0, usuarios_con_tope_propio_inactivos: 0 },
]

let usuarios: UsuarioDeApi[]
let queryClient: QueryClient
let jornadasAbiertas: { ubicacion_nombre: string }[]
let clientesAsignados: number
let hayMasClientes: boolean

interface Opciones {
  alEscribir?: Record<string, ReglaDeApi['responder']>
}

function servidor(opciones: Opciones = {}) {
  const escribir = (clave: string, porDefecto: ReglaDeApi['responder']): ReglaDeApi['responder'] =>
    opciones.alEscribir?.[clave] ?? porDefecto
  const cambiado = (id: string) => {
    const u = usuarios.find((x) => x.id === id)
    return { id, usuario: u?.usuario, nombre: u?.nombre, email: u?.email, rol_id: u?.rol_id, estado: u?.estado, tope_descuento_override: u?.tope_descuento_override }
  }
  const idDe = (url: URL) => url.pathname.split('/')[3] as string
  const cuerpo = (init: RequestInit | undefined) => JSON.parse(String(init?.body ?? '{}')) as Record<string, unknown>
  enrutar(apiFetchMock, [
    { metodo: 'GET', ruta: '/yo', responder: () => ({ status: 200, cuerpo: queryClient.getQueryData(clavesIdentidad.yo()) }) },
    {
      metodo: 'GET',
      ruta: '/identidad/usuarios',
      responder: (url) => {
        const estado = url.searchParams.get('estado')
        const rol = url.searchParams.get('rol_id')
        const conTope = url.searchParams.get('con_tope_propio') === 'true'
        return {
          status: 200,
          cuerpo: usuarios.filter(
            (u) => (!estado || u.estado === estado) && (!rol || u.rol_id === rol) && (!conTope || u.tope_descuento_override !== null),
          ),
        }
      },
    },
    { metodo: 'GET', ruta: '/identidad/roles', responder: () => ({ status: 200, cuerpo: ROLES }) },
    {
      metodo: 'GET',
      ruta: /^\/identidad\/usuarios\/[^/]+$/,
      responder: (url) => {
        const encontrado = usuarios.find((u) => u.id === idDe(url))
        return encontrado ? { status: 200, cuerpo: encontrado } : { status: 404, cuerpo: { title: 'No existe', codigo: 'RECURSO_NO_ENCONTRADO' } }
      },
    },
    {
      metodo: 'GET',
      ruta: '/stock/jornadas',
      responder: (url) => ({
        status: 200,
        cuerpo: {
          items: url.searchParams.get('estado') === 'ABIERTA' ? jornadasAbiertas.map((j, i) => ({ id: `j${i}`, estado: 'ABIERTA', ...j })) : [],
          cursor_siguiente: null,
        },
      }),
    },
    {
      metodo: 'GET',
      ruta: '/clientes',
      responder: () => ({
        status: 200,
        cuerpo: {
          items: Array.from({ length: clientesAsignados }, (_, i) => ({ id: `c${i}`, nombre: `Cliente ${i}` })),
          cursor_siguiente: hayMasClientes ? 'mas' : null,
        },
      }),
    },
    {
      metodo: 'POST',
      ruta: '/identidad/usuarios',
      responder: escribir('alta', (_url, init) => {
        const datos = cuerpo(init)
        const nuevo = usuario('dddddddd-dddd-4ddd-8ddd-dddddddddddd', String(datos.usuario), String(datos.nombre), String(datos.rol_id))
        usuarios = [...usuarios, nuevo]
        return { status: 201, cuerpo: nuevo }
      }),
    },
    {
      metodo: 'PUT',
      ruta: /^\/identidad\/usuarios\/[^/]+$/,
      responder: escribir('modificar', (url, init) => {
        const datos = cuerpo(init)
        usuarios = usuarios.map((u) => (u.id === idDe(url) ? { ...u, nombre: String(datos.nombre), email: (datos.email as string | null) ?? null } : u))
        return { status: 200, cuerpo: cambiado(idDe(url)) }
      }),
    },
    {
      metodo: 'PUT',
      ruta: /^\/identidad\/usuarios\/[^/]+\/rol$/,
      responder: escribir('rol', (url, init) => {
        const rolId = String(cuerpo(init).rol_id)
        usuarios = usuarios.map((u) => (u.id === idDe(url) ? { ...u, rol_id: rolId, rol_nombre: 'Cambiado' } : u))
        return { status: 200, cuerpo: cambiado(idDe(url)) }
      }),
    },
    {
      metodo: 'PUT',
      ruta: /^\/identidad\/usuarios\/[^/]+\/tope-descuento$/,
      responder: escribir('tope', (url, init) => {
        const tope = cuerpo(init).tope_descuento as string | null
        usuarios = usuarios.map((u) => (u.id === idDe(url) ? { ...u, tope_descuento_override: tope } : u))
        return { status: 200, cuerpo: cambiado(idDe(url)) }
      }),
    },
    {
      metodo: 'POST',
      ruta: /^\/identidad\/usuarios\/[^/]+\/baja$/,
      responder: escribir('baja', (url) => {
        usuarios = usuarios.map((u) => (u.id === idDe(url) ? { ...u, estado: 'INACTIVO' } : u))
        return { status: 200, cuerpo: cambiado(idDe(url)) }
      }),
    },
    {
      metodo: 'POST',
      ruta: /^\/identidad\/usuarios\/[^/]+\/reactivacion$/,
      responder: escribir('reactivar', (url) => {
        usuarios = usuarios.map((u) => (u.id === idDe(url) ? { ...u, estado: 'ACTIVO' } : u))
        return { status: 200, cuerpo: cambiado(idDe(url)) }
      }),
    },
    { metodo: 'POST', ruta: /^\/identidad\/usuarios\/[^/]+\/contrasena$/, responder: escribir('contrasena', () => ({ status: 204, cuerpo: null })) },
    { metodo: 'POST', ruta: /^\/identidad\/usuarios\/[^/]+\/desbloqueo$/, responder: escribir('desbloqueo', () => ({ status: 204, cuerpo: null })) },
  ])
}

function montar(inicial: string, rol: RolDePrueba = 'ADM') {
  queryClient = queryClientConYo(rol, { usuario: { id: YO, nombre: 'Rafa' }, rol: { id: ROL_ADMIN, nombre: 'Administrador' } })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[inicial]}>
        <Routes>
          <Route path="/admin/usuarios/*" element={<UsuariosArea />} />
          <Route path="/admin/roles/pin" element={<p>Pantalla del PIN</p>} />
          <Route path="/admin/clientes" element={<p>Listado de clientes</p>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

const operationId = (envio: { init: RequestInit }) => new Headers(envio.init.headers).get('Operation-Id')
const cuerpoDe = (envio: { init: RequestInit }) => JSON.parse(String(envio.init.body)) as Record<string, unknown>

describe('área Usuarios (tarea 10.1)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
    window.localStorage.clear()
    window.sessionStorage.clear()
    Object.defineProperty(window.navigator, 'onLine', { value: true, configurable: true })
    usuarios = [
      usuario(LAURA, 'laura', 'Laura Gómez', ROL_ADMIN, { email: 'laura@ejemplo.com' }),
      usuario(JUAN, 'juan', 'Juan Pérez', ROL_VENDEDOR, { tope_descuento_override: '0.100000' }),
      usuario(YO, 'rafa', 'Rafa', ROL_ADMIN),
      usuario('eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee', 'beto', 'Beto Ruiz', ROL_VENDEDOR, { estado: 'INACTIVO' }),
    ]
    jornadasAbiertas = []
    clientesAsignados = 0
    hayMasClientes = false
  })
  afterEach(() => {
    vi.clearAllMocks()
  })

  describe('acceso (ADR-027, SEG-06)', () => {
    it('solo quien tiene ADMIN_USUARIOS ve la entrada "Usuarios" en el menú', () => {
      const conPermiso = seccionesPermitidas((p) => PERMISOS_POR_ROL.ADM.includes(p)).map((s) => s.etiqueta)
      const supervisor = seccionesPermitidas((p) => PERMISOS_POR_ROL.SUP.includes(p)).map((s) => s.etiqueta)

      expect(conPermiso).toContain('Usuarios')
      expect(supervisor).not.toContain('Usuarios')
    })

    it('sin ADMIN_USUARIOS la pantalla lo dice y no pide usuarios', async () => {
      servidor()
      montar('/admin/usuarios', 'SUP')

      expect(await screen.findByText(/no tenés permiso para administrar usuarios/i)).toBeInTheDocument()
      expect(llamadas(apiFetchMock, 'GET', '/identidad/usuarios')).toHaveLength(0)
    })
  })

  describe('listado', () => {
    it('muestra nombre, usuario, rol, estado y tope propio de cada usuario', async () => {
      servidor()
      montar('/admin/usuarios')

      const fila = (await screen.findByText('Juan Pérez')).closest('tr') as HTMLElement
      expect(within(fila).getByText('juan')).toBeInTheDocument()
      expect(within(fila).getByText('Vendedor/Repartidor')).toBeInTheDocument()
      expect(within(fila).getByText('Activo')).toBeInTheDocument()
      expect(within(fila).getByText('10 %')).toBeInTheDocument()
      const baja = screen.getByText('Beto Ruiz').closest('tr') as HTMLElement
      expect(within(baja).getByText('De baja')).toBeInTheDocument()
    })

    it('filtra por estado y por rol con los parámetros del servidor', async () => {
      const usuario_ = userEvent.setup()
      servidor()
      montar('/admin/usuarios')
      await screen.findByText('Juan Pérez')

      await usuario_.selectOptions(screen.getByLabelText('Estado'), 'ACTIVO')
      await waitFor(() => expect(llamadas(apiFetchMock, 'GET', '/identidad/usuarios').some((c) => c.url.searchParams.get('estado') === 'ACTIVO')).toBe(true))
      expect(screen.queryByText('Beto Ruiz')).not.toBeInTheDocument()

      await usuario_.selectOptions(screen.getByLabelText('Rol'), ROL_VENDEDOR)
      await waitFor(() => expect(screen.queryByText('Laura Gómez')).not.toBeInTheDocument())
      expect(screen.getByText('Juan Pérez')).toBeInTheDocument()
    })

    it('entra con el filtro de "Topes por rol": rol y tope propio ya aplicados', async () => {
      servidor()
      montar(`/admin/usuarios?rol_id=${ROL_VENDEDOR}&con_tope_propio=true`)

      expect(await screen.findByText('Juan Pérez')).toBeInTheDocument()
      expect(screen.queryByText('Laura Gómez')).not.toBeInTheDocument()
      const pedido = llamadas(apiFetchMock, 'GET', '/identidad/usuarios')[0]?.url.searchParams
      expect(pedido?.get('rol_id')).toBe(ROL_VENDEDOR)
      expect(pedido?.get('con_tope_propio')).toBe('true')
      expect(screen.getByLabelText('Solo con tope propio')).toBeChecked()
    })
  })

  describe('alta (D9, D8, ADR-056)', () => {
    async function completar(usuario_: ReturnType<typeof userEvent.setup>, claves: [string, string] = [CLAVE_A, CLAVE_A]) {
      await usuario_.type(await screen.findByLabelText('Nombre de usuario'), 'marta')
      await usuario_.type(screen.getByLabelText('Nombre'), 'Marta Díaz')
      await usuario_.selectOptions(screen.getByLabelText('Rol'), ROL_VENDEDOR)
      await usuario_.type(screen.getByLabelText('Contraseña'), claves[0])
      await usuario_.type(screen.getByLabelText('Repetí la contraseña'), claves[1])
    }

    it('el selector de rol ofrece solo roles activos', async () => {
      servidor()
      montar('/admin/usuarios/nuevo')

      const selector = await screen.findByLabelText('Rol')
      await waitFor(() => expect(within(selector).getByRole('option', { name: 'Vendedor/Repartidor' })).toBeInTheDocument())
      expect(within(selector).queryByRole('option', { name: 'Rol viejo' })).not.toBeInTheDocument()
    })

    it('con confirmación distinta no envía nada y lo dice junto al campo', async () => {
      const usuario_ = userEvent.setup()
      servidor()
      montar('/admin/usuarios/nuevo')

      await completar(usuario_, [CLAVE_A, CLAVE_B])
      await usuario_.click(screen.getByRole('button', { name: 'Crear usuario' }))

      expect(await screen.findByText(/las dos contraseñas tienen que ser iguales/i)).toBeInTheDocument()
      expect(llamadas(apiFetchMock, 'POST', '/identidad/usuarios')).toHaveLength(0)
    })

    it('con una contraseña corta no envía nada', async () => {
      const usuario_ = userEvent.setup()
      servidor()
      montar('/admin/usuarios/nuevo')

      await completar(usuario_, ['corta', 'corta'])
      await usuario_.click(screen.getByRole('button', { name: 'Crear usuario' }))

      expect(await screen.findByText(/al menos 8 caracteres/i)).toBeInTheDocument()
      expect(llamadas(apiFetchMock, 'POST', '/identidad/usuarios')).toHaveLength(0)
    })

    it('envía el alta con Operation-Id, sin confirmación, y limpia los campos de contraseña', async () => {
      const usuario_ = userEvent.setup()
      servidor()
      montar('/admin/usuarios/nuevo')

      await completar(usuario_)
      await usuario_.click(screen.getByRole('button', { name: 'Crear usuario' }))

      await waitFor(() => expect(llamadas(apiFetchMock, 'POST', '/identidad/usuarios')).toHaveLength(1))
      const envio = llamadas(apiFetchMock, 'POST', '/identidad/usuarios')[0]!
      expect(cuerpoDe(envio)).toEqual({ usuario: 'marta', nombre: 'Marta Díaz', email: null, rol_id: ROL_VENDEDOR, password: CLAVE_A })
      expect(operationId(envio)).toBeTruthy()
    })

    it('las contraseñas no quedan en el almacenamiento del navegador ni en la caché de consultas', async () => {
      const usuario_ = userEvent.setup()
      servidor()
      montar('/admin/usuarios/nuevo')

      await completar(usuario_)
      await usuario_.click(screen.getByRole('button', { name: 'Crear usuario' }))
      await waitFor(() => expect(llamadas(apiFetchMock, 'POST', '/identidad/usuarios')).toHaveLength(1))

      expect(JSON.stringify({ ...window.localStorage })).not.toContain(CLAVE_A)
      expect(JSON.stringify({ ...window.sessionStorage })).not.toContain(CLAVE_A)
      expect(JSON.stringify(queryClient.getQueryCache().getAll().map((q) => q.state.data))).not.toContain(CLAVE_A)
      expect(JSON.stringify(queryClient.getMutationCache().getAll().map((m) => m.state.variables))).not.toContain(CLAVE_A)
    })

    it('explica USUARIO_DUPLICADO y, corregido el dato, reintenta con el mismo Operation-Id', async () => {
      const usuario_ = userEvent.setup()
      let primera = true
      servidor({
        alEscribir: {
          alta: (_url, init) => {
            if (primera) {
              primera = false
              return { status: 409, cuerpo: { title: 'dup', codigo: 'IDENTIDAD_USUARIO_DUPLICADO' } }
            }
            return { status: 201, cuerpo: { id: 'x', usuario: 'marta2', nombre: 'Marta', email: null, rol_id: ROL_VENDEDOR, estado: 'ACTIVO', tiene_pin_autorizacion: false, init: String(init?.body).length } }
          },
        },
      })
      montar('/admin/usuarios/nuevo')

      await completar(usuario_)
      await usuario_.click(screen.getByRole('button', { name: 'Crear usuario' }))
      expect(await screen.findByText(/ya existe un usuario con ese nombre de usuario/i)).toBeInTheDocument()

      const campo = screen.getByLabelText('Nombre de usuario')
      await usuario_.clear(campo)
      await usuario_.type(campo, 'marta2')
      await usuario_.type(screen.getByLabelText('Contraseña'), CLAVE_A)
      await usuario_.type(screen.getByLabelText('Repetí la contraseña'), CLAVE_A)
      await usuario_.click(screen.getByRole('button', { name: 'Crear usuario' }))

      await waitFor(() => expect(llamadas(apiFetchMock, 'POST', '/identidad/usuarios')).toHaveLength(2))
      const [primero, segundo] = llamadas(apiFetchMock, 'POST', '/identidad/usuarios')
      expect(operationId(primero!)).toBe(operationId(segundo!))
    })
  })

  describe('ficha', () => {
    it('muestra los datos, el rol y el tope del rol', async () => {
      servidor()
      montar(`/admin/usuarios/${JUAN}`)

      expect(await screen.findByRole('heading', { name: 'Juan Pérez' })).toBeInTheDocument()
      expect(screen.getByText(/nombre de usuario: juan/i)).toBeInTheDocument()
      expect(screen.getByLabelText('Tope propio (%)')).toHaveValue('10')
      expect(screen.getByText(/tope del rol: 5 %/i)).toBeInTheDocument()
    })

    it('ofrece las cuatro ayudas aprobadas (baja, cambio de rol, tope propio y contraseña), sin ejemplos', async () => {
      servidor()
      montar(`/admin/usuarios/${JUAN}`)

      await screen.findByRole('heading', { name: 'Juan Pérez' })
      for (const titulo of ['Dar de baja a un usuario', 'Cambiar el rol de un usuario', 'Tope de descuento propio', 'Restablecer la contraseña']) {
        expect(screen.getByRole('button', { name: `Ayuda: ${titulo}` })).toBeInTheDocument()
      }
    })

    it('un usuario inexistente o de otra organización (404) se informa sin datos', async () => {
      servidor()
      montar('/admin/usuarios/ffffffff-ffff-4fff-8fff-ffffffffffff')

      expect(await screen.findByText(/no se encontró ese usuario/i)).toBeInTheDocument()
    })

    it('modifica nombre y email', async () => {
      const usuario_ = userEvent.setup()
      servidor()
      montar(`/admin/usuarios/${LAURA}`)

      const nombre = await screen.findByLabelText('Nombre')
      await usuario_.clear(nombre)
      await usuario_.type(nombre, ' Laura Gómez Díaz ')
      await usuario_.click(screen.getByRole('button', { name: 'Guardar datos' }))

      await waitFor(() => expect(llamadas(apiFetchMock, 'PUT', `/identidad/usuarios/${LAURA}`)).toHaveLength(1))
      expect(cuerpoDe(llamadas(apiFetchMock, 'PUT', `/identidad/usuarios/${LAURA}`)[0]!)).toEqual({ nombre: 'Laura Gómez Díaz', email: 'laura@ejemplo.com' })
    })

    it('cambia el rol con confirmación y el selector no ofrece roles de baja', async () => {
      const usuario_ = userEvent.setup()
      servidor()
      montar(`/admin/usuarios/${JUAN}`)

      const selector = await screen.findByLabelText('Rol')
      await waitFor(() => expect(within(selector).getByRole('option', { name: 'Administrador' })).toBeInTheDocument())
      expect(within(selector).queryByRole('option', { name: 'Rol viejo' })).not.toBeInTheDocument()
      await usuario_.selectOptions(selector, ROL_ADMIN)
      await usuario_.click(screen.getByRole('button', { name: 'Cambiar rol' }))

      expect(llamadas(apiFetchMock, 'PUT', `/identidad/usuarios/${JUAN}/rol`)).toHaveLength(0)
      const dialogo = await screen.findByRole('dialog', { name: /confirmar cambio de rol/i })
      await usuario_.click(within(dialogo).getByRole('button', { name: 'Confirmar cambio de rol' }))

      await waitFor(() => expect(llamadas(apiFetchMock, 'PUT', `/identidad/usuarios/${JUAN}/rol`)).toHaveLength(1))
      expect(cuerpoDe(llamadas(apiFetchMock, 'PUT', `/identidad/usuarios/${JUAN}/rol`)[0]!)).toEqual({ rol_id: ROL_ADMIN })
    })

    it('al cambiar el propio rol avisa y vuelve a pedir la sesión propia', async () => {
      const usuario_ = userEvent.setup()
      servidor()
      montar(`/admin/usuarios/${YO}`)

      const selector = await screen.findByLabelText('Rol')
      await waitFor(() => expect(within(selector).getByRole('option', { name: 'Vendedor/Repartidor' })).toBeInTheDocument())
      await usuario_.selectOptions(selector, ROL_VENDEDOR)
      await usuario_.click(screen.getByRole('button', { name: 'Cambiar rol' }))
      const dialogo = await screen.findByRole('dialog', { name: /confirmar cambio de rol/i })
      expect(within(dialogo).getByText(/vas a cambiar tu propio acceso/i)).toBeInTheDocument()
      const antes = llamadas(apiFetchMock, 'GET', '/yo').length
      await usuario_.click(within(dialogo).getByRole('button', { name: 'Confirmar cambio de rol' }))

      await waitFor(() => expect(llamadas(apiFetchMock, 'GET', '/yo').length).toBeGreaterThan(antes))
    })

    it('explica IDENTIDAD_SIN_ADMINISTRADOR si el cambio dejaría la organización sin administrador', async () => {
      const usuario_ = userEvent.setup()
      servidor({ alEscribir: { rol: () => ({ status: 409, cuerpo: { title: 'x', codigo: 'IDENTIDAD_SIN_ADMINISTRADOR' } }) } })
      montar(`/admin/usuarios/${YO}`)

      const selector = await screen.findByLabelText('Rol')
      await waitFor(() => expect(within(selector).getByRole('option', { name: 'Vendedor/Repartidor' })).toBeInTheDocument())
      await usuario_.selectOptions(selector, ROL_VENDEDOR)
      await usuario_.click(screen.getByRole('button', { name: 'Cambiar rol' }))
      await usuario_.click(await screen.findByRole('button', { name: 'Confirmar cambio de rol' }))

      expect(await screen.findByText(/se quedaría sin nadie que administre usuarios y roles/i)).toBeInTheDocument()
    })

    describe('tope propio (D12, DSC-06, INV-03)', () => {
      it('el porcentaje escrito viaja como fracción string', async () => {
        const usuario_ = userEvent.setup()
        servidor()
        montar(`/admin/usuarios/${LAURA}`)

        await usuario_.type(await screen.findByLabelText('Tope propio (%)'), '12,5')
        await usuario_.click(screen.getByRole('button', { name: 'Guardar tope' }))

        await waitFor(() => expect(llamadas(apiFetchMock, 'PUT', `/identidad/usuarios/${LAURA}/tope-descuento`)).toHaveLength(1))
        expect(cuerpoDe(llamadas(apiFetchMock, 'PUT', `/identidad/usuarios/${LAURA}/tope-descuento`)[0]!)).toEqual({ tope_descuento: '0.125000' })
      })

      it('vacío vuelve al tope del rol (null)', async () => {
        const usuario_ = userEvent.setup()
        servidor()
        montar(`/admin/usuarios/${JUAN}`)

        await usuario_.clear(await screen.findByLabelText('Tope propio (%)'))
        await usuario_.click(screen.getByRole('button', { name: 'Guardar tope' }))

        await waitFor(() => expect(llamadas(apiFetchMock, 'PUT', `/identidad/usuarios/${JUAN}/tope-descuento`)).toHaveLength(1))
        expect(cuerpoDe(llamadas(apiFetchMock, 'PUT', `/identidad/usuarios/${JUAN}/tope-descuento`)[0]!)).toEqual({ tope_descuento: null })
      })

      it('un porcentaje fuera de rango no se envía', async () => {
        const usuario_ = userEvent.setup()
        servidor()
        montar(`/admin/usuarios/${LAURA}`)

        await usuario_.type(await screen.findByLabelText('Tope propio (%)'), '150')
        await usuario_.click(screen.getByRole('button', { name: 'Guardar tope' }))

        expect(await screen.findByText(/porcentaje de 0 a 100/i)).toBeInTheDocument()
        expect(llamadas(apiFetchMock, 'PUT', `/identidad/usuarios/${LAURA}/tope-descuento`)).toHaveLength(0)
      })

      it('avisa que no tiene efecto si el rol no tiene descuento manual', async () => {
        servidor()
        montar(`/admin/usuarios/${JUAN}`)

        expect(await screen.findByText(/no tiene efecto mientras su rol no tenga el permiso de descuento manual/i)).toBeInTheDocument()
      })

      it('no avisa cuando el rol sí tiene descuento manual', async () => {
        servidor()
        montar(`/admin/usuarios/${LAURA}`)

        await screen.findByLabelText('Tope propio (%)')
        expect(screen.queryByText(/no tiene efecto mientras su rol/i)).not.toBeInTheDocument()
      })
    })

    describe('contraseña (D8, ADR-056)', () => {
      it('con confirmación distinta no envía nada', async () => {
        const usuario_ = userEvent.setup()
        servidor()
        montar(`/admin/usuarios/${JUAN}`)

        await usuario_.type(await screen.findByLabelText('Contraseña nueva'), CLAVE_A)
        await usuario_.type(screen.getByLabelText('Repetí la contraseña nueva'), CLAVE_B)
        await usuario_.click(screen.getByRole('button', { name: 'Restablecer contraseña' }))

        expect(await screen.findByText(/las dos contraseñas tienen que ser iguales/i)).toBeInTheDocument()
        expect(llamadas(apiFetchMock, 'POST', `/identidad/usuarios/${JUAN}/contrasena`)).toHaveLength(0)
      })

      it('envía solo la contraseña, avisa que se cerraron las sesiones y limpia los campos', async () => {
        const usuario_ = userEvent.setup()
        servidor()
        montar(`/admin/usuarios/${JUAN}`)

        await usuario_.type(await screen.findByLabelText('Contraseña nueva'), CLAVE_A)
        await usuario_.type(screen.getByLabelText('Repetí la contraseña nueva'), CLAVE_A)
        await usuario_.click(screen.getByRole('button', { name: 'Restablecer contraseña' }))

        await waitFor(() => expect(llamadas(apiFetchMock, 'POST', `/identidad/usuarios/${JUAN}/contrasena`)).toHaveLength(1))
        const envio = llamadas(apiFetchMock, 'POST', `/identidad/usuarios/${JUAN}/contrasena`)[0]!
        expect(cuerpoDe(envio)).toEqual({ contrasena: CLAVE_A })
        expect(operationId(envio)).toBeTruthy()
        expect(await screen.findByText(/sus sesiones abiertas se cerraron/i)).toBeInTheDocument()
        expect(screen.getByLabelText('Contraseña nueva')).toHaveValue('')
        expect(JSON.stringify({ ...window.localStorage })).not.toContain(CLAVE_A)
        expect(JSON.stringify(queryClient.getMutationCache().getAll().map((m) => m.state.variables))).not.toContain(CLAVE_A)
      })
    })

    it('desbloquea el inicio de sesión con el comando existente', async () => {
      const usuario_ = userEvent.setup()
      servidor()
      montar(`/admin/usuarios/${JUAN}`)

      await usuario_.click(await screen.findByRole('button', { name: 'Desbloquear inicio de sesión' }))

      await waitFor(() => expect(llamadas(apiFetchMock, 'POST', `/identidad/usuarios/${JUAN}/desbloqueo`)).toHaveLength(1))
    })

    it('enlaza a la pantalla del PIN de autorización', async () => {
      const usuario_ = userEvent.setup()
      servidor()
      montar(`/admin/usuarios/${JUAN}`)

      await usuario_.click(await screen.findByRole('link', { name: /pin de autorización/i }))

      expect(await screen.findByText('Pantalla del PIN')).toBeInTheDocument()
    })

    describe('clientes asignados (D6, D15)', () => {
      it('muestra la cantidad y enlaza al listado filtrado por el vendedor', async () => {
        clientesAsignados = 3
        servidor()
        montar(`/admin/usuarios/${JUAN}`)

        expect(await screen.findByText('3 clientes asignados')).toBeInTheDocument()
        const enlace = screen.getByRole('link', { name: /ver clientes asignados/i })
        expect(enlace).toHaveAttribute('href', `/admin/clientes?vendedor_id=${JUAN}`)
      })

      it('sin clientes asignados lo dice', async () => {
        servidor()
        montar(`/admin/usuarios/${JUAN}`)

        expect(await screen.findByText(/no tiene clientes asignados/i)).toBeInTheDocument()
        expect(screen.queryByRole('link', { name: /ver clientes asignados/i })).not.toBeInTheDocument()
      })
    })

    describe('baja y reactivación (D2, D5, D6)', () => {
      it('pide confirmación con los avisos de jornada abierta y clientes asignados antes de enviar', async () => {
        const usuario_ = userEvent.setup()
        jornadasAbiertas = [{ ubicacion_nombre: 'Camión 1' }]
        clientesAsignados = 12
        servidor()
        montar(`/admin/usuarios/${JUAN}`)

        await screen.findByText('12 clientes asignados')
        await usuario_.click(screen.getByRole('button', { name: 'Dar de baja' }))
        const dialogo = await screen.findByRole('dialog', { name: /confirmar baja de juan pérez/i })

        expect(within(dialogo).getByText(/jornada abierta en camión 1/i)).toBeInTheDocument()
        expect(within(dialogo).getByText(/12 clientes asignados/i)).toBeInTheDocument()
        expect(llamadas(apiFetchMock, 'POST', `/identidad/usuarios/${JUAN}/baja`)).toHaveLength(0)
      })

      it('confirma la baja con la observación y el usuario pasa a "De baja"', async () => {
        const usuario_ = userEvent.setup()
        servidor()
        montar(`/admin/usuarios/${JUAN}`)

        await usuario_.click(await screen.findByRole('button', { name: 'Dar de baja' }))
        const dialogo = await screen.findByRole('dialog', { name: /confirmar baja/i })
        await usuario_.type(within(dialogo).getByLabelText('Observación (opcional)'), 'Se fue de la empresa')
        await usuario_.click(within(dialogo).getByRole('button', { name: 'Confirmar baja' }))

        await waitFor(() => expect(llamadas(apiFetchMock, 'POST', `/identidad/usuarios/${JUAN}/baja`)).toHaveLength(1))
        expect(cuerpoDe(llamadas(apiFetchMock, 'POST', `/identidad/usuarios/${JUAN}/baja`)[0]!)).toEqual({ observacion: 'Se fue de la empresa' })
        expect(await screen.findByRole('button', { name: 'Reactivar' })).toBeInTheDocument()
      })

      it('la autobaja se rechaza con una explicación', async () => {
        const usuario_ = userEvent.setup()
        servidor({ alEscribir: { baja: () => ({ status: 409, cuerpo: { title: 'x', codigo: 'IDENTIDAD_AUTOBAJA' } }) } })
        montar(`/admin/usuarios/${YO}`)

        await usuario_.click(await screen.findByRole('button', { name: 'Dar de baja' }))
        await usuario_.click(await screen.findByRole('button', { name: 'Confirmar baja' }))

        expect(await screen.findByText(/no podés darte de baja a vos mismo/i)).toBeInTheDocument()
      })

      it('tras un corte de red el reintento reenvía el mismo Operation-Id', async () => {
        const usuario_ = userEvent.setup()
        let cortar = true
        servidor({
          alEscribir: {
            baja: (url) => {
              if (cortar) throw new TypeError('Failed to fetch')
              usuarios = usuarios.map((u) => (u.id === url.pathname.split('/')[3] ? { ...u, estado: 'INACTIVO' } : u))
              return { status: 200, cuerpo: { id: JUAN } }
            },
          },
        })
        montar(`/admin/usuarios/${JUAN}`)

        await usuario_.click(await screen.findByRole('button', { name: 'Dar de baja' }))
        await usuario_.click(await screen.findByRole('button', { name: 'Confirmar baja' }))
        expect(await screen.findByText(/se necesita conexión/i)).toBeInTheDocument()
        cortar = false
        await usuario_.click(screen.getByRole('button', { name: 'Confirmar baja' }))

        await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
        const envios = llamadas(apiFetchMock, 'POST', `/identidad/usuarios/${JUAN}/baja`)
        expect(envios.length).toBeGreaterThanOrEqual(2)
        expect(new Set(envios.map(operationId)).size).toBe(1)
      })

      it('reactiva con el aviso de que hay que redefinir el PIN', async () => {
        const usuario_ = userEvent.setup()
        servidor()
        montar('/admin/usuarios/eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee')

        await usuario_.click(await screen.findByRole('button', { name: 'Reactivar' }))
        const dialogo = await screen.findByRole('dialog', { name: /confirmar reactivación/i })
        expect(within(dialogo).getByText(/tiene que volver a definir su pin de autorización/i)).toBeInTheDocument()
        await usuario_.click(within(dialogo).getByRole('button', { name: 'Confirmar reactivación' }))

        await waitFor(() =>
          expect(llamadas(apiFetchMock, 'POST', '/identidad/usuarios/eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee/reactivacion')).toHaveLength(1),
        )
      })

      it('avisa al reactivar a un usuario cuyo rol está de baja', async () => {
        const usuario_ = userEvent.setup()
        usuarios = [...usuarios, usuario('99999999-9999-4999-8999-999999999999', 'viejo', 'Viejo', ROL_VIEJO, { estado: 'INACTIVO' })]
        servidor()
        montar('/admin/usuarios/99999999-9999-4999-8999-999999999999')

        await usuario_.click(await screen.findByRole('button', { name: 'Reactivar' }))

        expect(await screen.findByText(/su rol está dado de baja: no va a poder entrar hasta que le asignes un rol activo/i)).toBeInTheDocument()
      })
    })
  })
})
