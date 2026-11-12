/**
 * Change 17b, tarea 9.1 (gobernanza CRÍTICA, diseño D9-A aprobado el 2026-10-17): pantalla "Roles y
 * permisos" (spec `identidad/administracion-de-roles`, requisito "La pantalla de roles y
 * permisos"; `design.md` D7, D9; `01` §19, ADR-011, ADR-017, ADR-027, ADR-053, INV-06, SEG-06).
 * Solo cambia los permisos de los roles que existen: no crea, desactiva ni borra roles.
 */

import { QueryClientProvider, type QueryClient } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }))
vi.mock('../../../../../src/lib/api/httpClient', () => ({ apiFetch: apiFetchMock }))

import RolesArea from '../../../../../src/areas/admin/roles/RolesArea'
import { seccionesPermitidas } from '../../../../../src/features/identidad/secciones'
import { clavesIdentidad } from '../../../../../src/features/identidad/claves'
import { enrutar, llamadas, type ReglaDeApi } from '../../../utils/enrutarApi'
import { PERMISOS_POR_ROL, queryClientConYo, type RolDePrueba } from '../../../utils/permisosDePrueba'

const ADMINISTRADOR = '11111111-1111-4111-8111-111111111111'
const SUPERVISOR = '22222222-2222-4222-8222-222222222222'
const VENDEDOR = '33333333-3333-4333-8333-333333333333'

const CATALOGO = [
  { codigo: 'ADMIN_USUARIOS', descripcion: 'Usuarios, roles y permisos', modulo: 'identidad' },
  { codigo: 'REGISTRAR_COBRANZA', descripcion: 'Registrar cobranzas', modulo: 'cobranzas' },
  { codigo: 'ANULAR_COBRANZA', descripcion: 'Anular cobranzas', modulo: 'cobranzas' },
  { codigo: 'VENDER', descripcion: 'Confirmar ventas', modulo: 'ventas' },
  { codigo: 'AUTORIZAR_DESCUENTO', descripcion: 'Superar tope de descuento', modulo: 'ventas' },
  { codigo: 'SUPERAR_CREDITO', descripcion: 'Vender con exceso de crédito', modulo: 'ventas' },
  { codigo: 'VER_REPORTES', descripcion: 'Reportes', modulo: 'reportes' },
]

interface RolDeApi {
  id: string
  nombre: string
  activo: boolean
  tope_descuento: string
  permisos: string[]
  usuarios_activos: number
}

function rolDeApi(id: string, nombre: string, permisos: string[], usuarios: number, activo = true): RolDeApi {
  return { id, nombre, activo, tope_descuento: '0.000000', permisos: [...permisos].sort(), usuarios_activos: usuarios }
}

function rolesIniciales(): RolDeApi[] {
  return [
    rolDeApi(ADMINISTRADOR, 'Administrador', CATALOGO.map((p) => p.codigo), 1),
    rolDeApi(SUPERVISOR, 'Supervisor comercial', ['REGISTRAR_COBRANZA', 'ANULAR_COBRANZA', 'AUTORIZAR_DESCUENTO', 'SUPERAR_CREDITO'], 2),
    rolDeApi(VENDEDOR, 'Vendedor/Repartidor', ['VENDER'], 5, false),
  ]
}

const URL_ROLES = '/identidad/roles'
const URL_PERMISOS = '/identidad/permisos'
const URL_CAMBIO = /^\/identidad\/roles\/[^/]+\/permisos$/

/** Un servidor de roles que guarda los permisos que recibe, como el real. */
function servidor(opciones: { alGuardar?: ReglaDeApi['responder'] } = {}) {
  let roles = rolesIniciales()
  enrutar(apiFetchMock, [
    // La sesión propia se vuelve a pedir al guardar (['yo'] se invalida): responde lo mismo.
    { metodo: 'GET', ruta: '/yo', responder: () => ({ status: 200, cuerpo: queryClient.getQueryData(clavesIdentidad.yo()) }) },
    { metodo: 'GET', ruta: URL_ROLES, responder: () => ({ status: 200, cuerpo: roles }) },
    { metodo: 'GET', ruta: URL_PERMISOS, responder: () => ({ status: 200, cuerpo: CATALOGO }) },
    {
      metodo: 'PUT',
      ruta: URL_CAMBIO,
      responder: (url, init) => {
        if (opciones.alGuardar) return opciones.alGuardar(url, init)
        const id = url.pathname.split('/')[3]
        const { permisos } = JSON.parse(String(init?.body)) as { permisos: string[] }
        roles = roles.map((r) => (r.id === id ? { ...r, permisos: [...permisos].sort() } : r))
        return { status: 200, cuerpo: roles.find((r) => r.id === id) }
      },
    },
  ])
}

let queryClient: QueryClient

function montar(rol: RolDePrueba = 'ADM', propio: string = ADMINISTRADOR) {
  queryClient = queryClientConYo(rol, { rol: { id: propio, nombre: 'Rol propio' } })
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

function filaDe(nombre: string): HTMLElement {
  return screen.getByText(nombre).closest('tr') as HTMLElement
}

async function elegir(usuario: ReturnType<typeof userEvent.setup>, nombre: string) {
  await screen.findByText(nombre)
  await usuario.click(screen.getByRole('button', { name: `Editar permisos de ${nombre}` }))
  return screen.findByRole('region', { name: `Permisos de ${nombre}` })
}

const guardados = () => llamadas(apiFetchMock, 'PUT', URL_CAMBIO)
const operationId = (envio: { init: RequestInit }) => new Headers(envio.init.headers).get('Operation-Id')

describe('pantalla Roles y permisos (tarea 9.1)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
    Object.defineProperty(window.navigator, 'onLine', { value: true, configurable: true })
  })
  afterEach(() => {
    vi.clearAllMocks()
  })

  describe('lista de roles', () => {
    it('muestra cada rol con su estado, su cantidad de permisos y de usuarios activos', async () => {
      servidor()
      montar()

      await screen.findByText('Supervisor comercial')
      const supervisor = within(filaDe('Supervisor comercial'))
      expect(supervisor.getByText('Activo')).toBeInTheDocument()
      expect(supervisor.getByRole('cell', { name: '4' })).toBeInTheDocument()
      expect(supervisor.getByRole('cell', { name: '2' })).toBeInTheDocument()
      const vendedor = within(filaDe('Vendedor/Repartidor'))
      expect(vendedor.getByText('De baja')).toBeInTheDocument()
      expect(vendedor.getByRole('cell', { name: '5' })).toBeInTheDocument()
      expect(within(filaDe('Administrador')).getByRole('cell', { name: '7' })).toBeInTheDocument()
    })

    // Change 20b (D10, D11): desde acá se crea, renombra, da de baja y reactiva; nada se borra.
    it('ofrece el enlace a "Topes por rol", "Nuevo rol", renombrar y dar de baja, pero nunca borrar', async () => {
      servidor()
      montar()

      await screen.findByText('Supervisor comercial')
      expect(screen.getByRole('link', { name: 'Topes por rol' })).toHaveAttribute('href', '/admin/descuentos/topes')
      expect(screen.getByRole('button', { name: 'Nuevo rol' })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'Renombrar Supervisor comercial' })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'Dar de baja Supervisor comercial' })).toBeInTheDocument()
      expect(screen.queryByRole('button', { name: /borrar|eliminar|desactivar/i })).not.toBeInTheDocument()
    })

    it('sin ADMIN_USUARIOS avisa y no pide nada (ADR-027)', async () => {
      servidor()
      montar('GES')

      expect(await screen.findByText(/no tenés permiso/i)).toBeInTheDocument()
      expect(llamadas(apiFetchMock, 'GET', URL_ROLES)).toHaveLength(0)
      expect(llamadas(apiFetchMock, 'GET', URL_PERMISOS)).toHaveLength(0)
    })
  })

  describe('permisos del rol elegido', () => {
    it('los agrupa por módulo, con descripción y casilla marcada según el rol', async () => {
      servidor()
      const usuario = userEvent.setup()
      montar()

      const panel = await elegir(usuario, 'Supervisor comercial')

      expect(within(panel).getByRole('group', { name: 'Cobranzas' })).toBeInTheDocument()
      expect(within(panel).getByRole('group', { name: 'Ventas' })).toBeInTheDocument()
      expect(within(panel).getByRole('group', { name: 'Usuarios y organización' })).toBeInTheDocument()
      expect(within(panel).getByLabelText('Anular cobranzas')).toBeChecked()
      expect(within(panel).getByLabelText('Usuarios, roles y permisos')).not.toBeChecked()
      expect(within(panel).getByLabelText('Confirmar ventas')).not.toBeChecked()
    })

    it('marca "llega más adelante" solo en los permisos de módulos que todavía no existen (reportes, no ventas)', async () => {
      servidor()
      const usuario = userEvent.setup()
      montar()

      const panel = await elegir(usuario, 'Supervisor comercial')

      const ventas = within(within(panel).getByRole('group', { name: 'Ventas' }))
      expect(ventas.queryByText(/llega más adelante/i)).not.toBeInTheDocument()
      expect(within(within(panel).getByRole('group', { name: 'Reportes' })).getByText(/llega más adelante/i)).toBeInTheDocument()
      expect(within(within(panel).getByRole('group', { name: 'Cobranzas' })).queryByText(/llega más adelante/i)).not.toBeInTheDocument()
    })

    it('"Guardar cambios" está apagado mientras no haya cambios', async () => {
      servidor()
      const usuario = userEvent.setup()
      montar()

      const panel = await elegir(usuario, 'Supervisor comercial')
      expect(within(panel).getByRole('button', { name: 'Guardar cambios' })).toBeDisabled()
      await usuario.click(within(panel).getByLabelText('Anular cobranzas'))
      expect(within(panel).getByRole('button', { name: 'Guardar cambios' })).toBeEnabled()
      await usuario.click(within(panel).getByLabelText('Anular cobranzas'))
      expect(within(panel).getByRole('button', { name: 'Guardar cambios' })).toBeDisabled()
    })
  })

  describe('guardar con resumen y confirmación', () => {
    it('Escenario quitar un permiso: el resumen dice "Quita: Anular cobranzas", no se envía nada antes de confirmar y el PUT lleva los permisos que quedan', async () => {
      servidor()
      const usuario = userEvent.setup()
      montar()
      const panel = await elegir(usuario, 'Supervisor comercial')

      await usuario.click(within(panel).getByLabelText('Anular cobranzas'))
      await usuario.click(within(panel).getByRole('button', { name: 'Guardar cambios' }))
      const dialogo = await screen.findByRole('dialog', { name: 'Confirmar cambios en Supervisor comercial' })
      expect(within(dialogo).getByText('Quita: Anular cobranzas')).toBeInTheDocument()
      expect(within(dialogo).queryByText(/^Agrega:/)).not.toBeInTheDocument()
      expect(guardados()).toHaveLength(0)
      await usuario.click(within(dialogo).getByRole('button', { name: 'Confirmar cambios' }))

      await waitFor(() => expect(guardados()).toHaveLength(1))
      expect(guardados()[0]?.url.pathname).toBe(`/identidad/roles/${SUPERVISOR}/permisos`)
      expect(JSON.parse(String(guardados()[0]?.init.body))).toEqual({
        permisos: ['AUTORIZAR_DESCUENTO', 'REGISTRAR_COBRANZA', 'SUPERAR_CREDITO'],
      })
      expect(operationId(guardados()[0] as { init: RequestInit })).toBeTruthy()
      await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
      await waitFor(() => expect(within(filaDe('Supervisor comercial')).getByRole('cell', { name: '3' })).toBeInTheDocument())
    })

    it('el resumen lista lo que agrega y lo que quita a la vez, y el PUT lleva el conjunto completo', async () => {
      servidor()
      const usuario = userEvent.setup()
      montar()
      const panel = await elegir(usuario, 'Supervisor comercial')

      await usuario.click(within(panel).getByLabelText('Anular cobranzas'))
      await usuario.click(within(panel).getByLabelText('Reportes'))
      await usuario.click(within(panel).getByRole('button', { name: 'Guardar cambios' }))
      const dialogo = await screen.findByRole('dialog')

      expect(within(dialogo).getByText('Agrega: Reportes')).toBeInTheDocument()
      expect(within(dialogo).getByText('Quita: Anular cobranzas')).toBeInTheDocument()
      await usuario.click(within(dialogo).getByRole('button', { name: 'Confirmar cambios' }))
      await waitFor(() => expect(guardados()).toHaveLength(1))
      expect(JSON.parse(String(guardados()[0]?.init.body)).permisos).toEqual([
        'AUTORIZAR_DESCUENTO',
        'REGISTRAR_COBRANZA',
        'SUPERAR_CREDITO',
        'VER_REPORTES',
      ])
    })

    it('al guardar se invalida la consulta de la sesión propia (["yo"]) para que el menú se actualice', async () => {
      servidor()
      const usuario = userEvent.setup()
      montar()
      const panel = await elegir(usuario, 'Supervisor comercial')
      expect(llamadas(apiFetchMock, 'GET', '/yo')).toHaveLength(0)

      await usuario.click(within(panel).getByLabelText('Anular cobranzas'))
      await usuario.click(within(panel).getByRole('button', { name: 'Guardar cambios' }))
      await usuario.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Confirmar cambios' }))

      await waitFor(() => expect(guardados()).toHaveLength(1))
      await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
      // La invalidación vuelve a pedir la sesión propia (el menú se rehace con los permisos nuevos).
      await waitFor(() => expect(llamadas(apiFetchMock, 'GET', '/yo').length).toBeGreaterThanOrEqual(1))
    })

    it('cancelar la confirmación no envía nada y conserva lo editado', async () => {
      servidor()
      const usuario = userEvent.setup()
      montar()
      const panel = await elegir(usuario, 'Supervisor comercial')

      await usuario.click(within(panel).getByLabelText('Anular cobranzas'))
      await usuario.click(within(panel).getByRole('button', { name: 'Guardar cambios' }))
      await usuario.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Cancelar' }))

      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
      expect(guardados()).toHaveLength(0)
      expect(within(panel).getByLabelText('Anular cobranzas')).not.toBeChecked()
    })
  })

  describe('avisos de la confirmación', () => {
    it('Escenario aviso de PIN: si el rol se queda sin ningún permiso de autorización avisa que se borra el PIN de sus usuarios', async () => {
      servidor()
      const usuario = userEvent.setup()
      montar()
      const panel = await elegir(usuario, 'Supervisor comercial')

      await usuario.click(within(panel).getByLabelText('Superar tope de descuento'))
      await usuario.click(within(panel).getByLabelText('Vender con exceso de crédito'))
      await usuario.click(within(panel).getByRole('button', { name: 'Guardar cambios' }))
      const dialogo = await screen.findByRole('dialog')

      expect(within(dialogo).getByText(/se va a borrar el pin de autorización de los usuarios del rol/i)).toBeInTheDocument()
    })

    it('si le queda algún permiso de autorización no avisa del PIN', async () => {
      servidor()
      const usuario = userEvent.setup()
      montar()
      const panel = await elegir(usuario, 'Supervisor comercial')

      await usuario.click(within(panel).getByLabelText('Superar tope de descuento'))
      await usuario.click(within(panel).getByRole('button', { name: 'Guardar cambios' }))
      const dialogo = await screen.findByRole('dialog')

      expect(within(dialogo).queryByText(/pin/i)).not.toBeInTheDocument()
    })

    it('un rol que no tenía autorización y sigue sin tenerla tampoco avisa del PIN', async () => {
      servidor()
      const usuario = userEvent.setup()
      montar()
      const panel = await elegir(usuario, 'Vendedor/Repartidor')

      await usuario.click(within(panel).getByLabelText('Confirmar ventas'))
      await usuario.click(within(panel).getByRole('button', { name: 'Guardar cambios' }))

      expect(within(await screen.findByRole('dialog')).queryByText(/pin/i)).not.toBeInTheDocument()
    })

    it('al editar el propio rol avisa que cambia lo que la persona misma puede hacer', async () => {
      servidor()
      const usuario = userEvent.setup()
      montar('ADM', ADMINISTRADOR)
      const panel = await elegir(usuario, 'Administrador')

      await usuario.click(within(panel).getByLabelText('Reportes'))
      await usuario.click(within(panel).getByRole('button', { name: 'Guardar cambios' }))

      expect(within(await screen.findByRole('dialog')).getByText(/estás cambiando tu propio rol/i)).toBeInTheDocument()
    })

    it('al editar el rol de otra persona no avisa del propio rol', async () => {
      servidor()
      const usuario = userEvent.setup()
      montar('ADM', ADMINISTRADOR)
      const panel = await elegir(usuario, 'Supervisor comercial')

      await usuario.click(within(panel).getByLabelText('Anular cobranzas'))
      await usuario.click(within(panel).getByRole('button', { name: 'Guardar cambios' }))

      expect(within(await screen.findByRole('dialog')).queryByText(/tu propio rol/i)).not.toBeInTheDocument()
    })
  })

  describe('rechazos y reintentos', () => {
    it('Escenario sin administrador: IDENTIDAD_SIN_ADMINISTRADOR se explica en palabras simples y el rol queda como estaba', async () => {
      servidor({
        alGuardar: () => ({
          status: 409,
          cuerpo: { title: 'La organización se quedaría sin nadie que administre usuarios y roles', codigo: 'IDENTIDAD_SIN_ADMINISTRADOR' },
        }),
      })
      const usuario = userEvent.setup()
      montar()
      const panel = await elegir(usuario, 'Administrador')

      await usuario.click(within(panel).getByLabelText('Usuarios, roles y permisos'))
      await usuario.click(within(panel).getByRole('button', { name: 'Guardar cambios' }))
      await usuario.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Confirmar cambios' }))

      const aviso = await screen.findByText(/se quedaría sin nadie que administre usuarios y roles/i)
      expect(aviso).toBeInTheDocument()
      expect(guardados()).toHaveLength(1) // un rechazo de dominio no se reintenta
      expect(within(filaDe('Administrador')).getByRole('cell', { name: '7' })).toBeInTheDocument()
    })

    it('otro rechazo muestra lo que dijo el servidor', async () => {
      servidor({ alGuardar: () => ({ status: 422, cuerpo: { title: 'Permiso inexistente.', codigo: 'IDENTIDAD_PERMISO_INEXISTENTE' } }) })
      const usuario = userEvent.setup()
      montar()
      const panel = await elegir(usuario, 'Supervisor comercial')

      await usuario.click(within(panel).getByLabelText('Anular cobranzas'))
      await usuario.click(within(panel).getByRole('button', { name: 'Guardar cambios' }))
      await usuario.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Confirmar cambios' }))

      expect(await screen.findByText('Permiso inexistente.')).toBeInTheDocument()
    })

    it('el reintento tras un corte de red reenvía el mismo Operation-Id (INV-06), también al volver a confirmar', async () => {
      let intentos = 0
      servidor({
        alGuardar: () => {
          intentos += 1
          if (intentos <= 3) throw new TypeError('Failed to fetch')
          return { status: 200, cuerpo: rolesIniciales()[1] }
        },
      })
      const usuario = userEvent.setup()
      montar()
      const panel = await elegir(usuario, 'Supervisor comercial')

      await usuario.click(within(panel).getByLabelText('Anular cobranzas'))
      await usuario.click(within(panel).getByRole('button', { name: 'Guardar cambios' }))
      const dialogo = await screen.findByRole('dialog')
      await usuario.click(within(dialogo).getByRole('button', { name: 'Confirmar cambios' }))
      expect(await within(dialogo).findByText(/se necesita conexión/i)).toBeInTheDocument()
      await usuario.click(within(dialogo).getByRole('button', { name: 'Confirmar cambios' }))

      await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
      const ids = guardados().map(operationId)
      expect(ids.length).toBeGreaterThanOrEqual(4)
      expect(new Set(ids).size).toBe(1)
    })
  })

  describe('menú (ADR-027)', () => {
    it('"Roles y permisos" aparece solo con ADMIN_USUARIOS', () => {
      const etiquetas = (rol: RolDePrueba) =>
        seccionesPermitidas((permiso) => PERMISOS_POR_ROL[rol].includes(permiso)).map((s) => s.etiqueta)

      expect(etiquetas('ADM')).toContain('Roles y permisos')
      expect(etiquetas('GES')).not.toContain('Roles y permisos')
      expect(etiquetas('SUP')).not.toContain('Roles y permisos')
      const seccion = seccionesPermitidas(() => true).find((s) => s.etiqueta === 'Roles y permisos')
      expect(seccion?.ruta).toBe('/admin/roles')
    })
  })
})
