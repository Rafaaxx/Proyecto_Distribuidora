/**
 * Change 18b, tarea 14.2 (D21 parte A): pestaña "PIN de autorización" de Roles (spec
 * `identidad/pin-de-autorizacion`; SEG-05, ADR-011, ADR-019, ADR-027, INV-06, SEG-06). GREEN-only
 * según `tasks.md`.
 */

import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }))
vi.mock('../../../../../src/lib/api/httpClient', () => ({ apiFetch: apiFetchMock }))

import RolesArea from '../../../../../src/areas/admin/roles/RolesArea'
import { enrutar, llamadas, type ReglaDeApi } from '../../../utils/enrutarApi'
import { queryClientConYo, type RolDePrueba } from '../../../utils/permisosDePrueba'

const R_SUP = '22222222-2222-4222-8222-222222222222'
const R_VEN = '33333333-3333-4333-8333-333333333333'
const MARTA = 'a1000000-0000-4000-8000-000000000001'
const EVA = 'a1000000-0000-4000-8000-000000000002'
const PEDRO = 'a1000000-0000-4000-8000-000000000003'
const ANA = 'a1000000-0000-4000-8000-000000000004'
const PIN = '482913'

function usuario(id: string, nombre: string, rol: string, tienePin: boolean, estado = 'ACTIVO') {
  return { id, usuario: nombre.toLowerCase(), nombre, email: null, rol_id: rol, estado, tiene_pin_autorizacion: tienePin }
}

function servidor(opciones: { alRotar?: ReglaDeApi['responder'] } = {}) {
  let usuarios = [
    usuario(MARTA, 'Marta', R_SUP, true),
    usuario(EVA, 'Eva', R_SUP, false),
    usuario(PEDRO, 'Pedro', R_VEN, false),
    usuario(ANA, 'Ana', R_SUP, false, 'INACTIVO'),
  ]
  enrutar(apiFetchMock, [
    { metodo: 'GET', ruta: '/identidad/usuarios', responder: () => ({ status: 200, cuerpo: usuarios }) },
    {
      metodo: 'GET',
      ruta: '/identidad/roles',
      responder: () => ({
        status: 200,
        cuerpo: [
          { id: R_SUP, nombre: 'Supervisor comercial', activo: true, tope_descuento: '0.05', permisos: ['AUTORIZAR_DESCUENTO', 'VENDER'], usuarios_activos: 2 },
          { id: R_VEN, nombre: 'Vendedor', activo: true, tope_descuento: '0', permisos: ['VENDER'], usuarios_activos: 1 },
        ],
      }),
    },
    { metodo: 'GET', ruta: '/identidad/permisos', responder: () => ({ status: 200, cuerpo: [] }) },
    {
      metodo: 'POST',
      ruta: /^\/identidad\/usuarios\/[^/]+\/pin$/,
      responder: (url, init) => {
        if (opciones.alRotar) return opciones.alRotar(url, init)
        const id = url.pathname.split('/')[3]
        usuarios = usuarios.map((u) => (u.id === id ? { ...u, tiene_pin_autorizacion: true } : u))
        return { status: 204, cuerpo: null }
      },
    },
  ])
}

function renderPantalla(rol: RolDePrueba = 'ADM') {
  return render(
    <QueryClientProvider client={queryClientConYo(rol)}>
      <MemoryRouter initialEntries={['/admin/roles/pin']}>
        <Routes>
          <Route path="/admin/roles/*" element={<RolesArea />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('PIN de autorización en Roles (tarea 14.2)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
    window.localStorage.clear()
    window.sessionStorage.clear()
  })
  afterEach(() => {
    vi.clearAllMocks()
  })

  it('lista solo a los usuarios activos con rol que autoriza, con "PIN definido: sí/no" y sin nunca mostrar un PIN', async () => {
    servidor()
    renderPantalla()

    const tabla = await screen.findByRole('table', { name: /pin de autorización/i })
    const filas = within(tabla).getAllByRole('row').slice(1)
    expect(filas.map((f) => f.textContent)).toEqual([
      expect.stringContaining('Eva'),
      expect.stringContaining('Marta'),
    ])
    expect(within(filas[0] as HTMLElement).getByText('No')).toBeInTheDocument()
    expect(within(filas[1] as HTMLElement).getByText('Sí')).toBeInTheDocument()
    expect(within(tabla).queryByText('Pedro')).not.toBeInTheDocument() // su rol no autoriza
    expect(within(tabla).queryByText('Ana')).not.toBeInTheDocument() // inactiva
    expect(screen.getByRole('button', { name: /ayuda: pin de autorización/i })).toBeInTheDocument()
  })

  it('las dos pestañas de Roles están y la de PIN está activa', async () => {
    servidor()
    renderPantalla()
    await screen.findByRole('table', { name: /pin de autorización/i })
    expect(screen.getByRole('link', { name: /roles y permisos/i })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /pin de autorización/i })).toBeInTheDocument()
  })

  it('sin ADMIN_USUARIOS no se monta ni pide nada (ADR-027, SEG-06)', () => {
    servidor()
    renderPantalla('SUP')

    expect(screen.getByText(/no ten[eé]s permiso para administrar usuarios/i)).toBeInTheDocument()
    expect(llamadas(apiFetchMock, 'GET', '/identidad/usuarios')).toHaveLength(0)
  })

  it('definir el PIN: dos veces, enmascarado; viaja una sola vez a su ruta con Operation-Id y la lista se actualiza', async () => {
    servidor()
    const usuario = userEvent.setup()
    renderPantalla()
    await screen.findByRole('table', { name: /pin de autorización/i })

    await usuario.click(screen.getByRole('button', { name: /definir el pin de eva/i }))
    const dialogo = await screen.findByRole('dialog', { name: /pin de eva/i })
    expect(within(dialogo).getByLabelText(/^pin nuevo$/i)).toHaveAttribute('type', 'password')
    expect(within(dialogo).getByLabelText(/repetí el pin/i)).toHaveAttribute('type', 'password')
    await usuario.type(within(dialogo).getByLabelText(/^pin nuevo$/i), PIN)
    await usuario.type(within(dialogo).getByLabelText(/repetí el pin/i), PIN)
    await usuario.click(within(dialogo).getByRole('button', { name: /guardar pin/i }))

    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    const envios = llamadas(apiFetchMock, 'POST', `/identidad/usuarios/${EVA}/pin`)
    expect(envios).toHaveLength(1)
    expect(JSON.parse(String(envios[0]?.init.body))).toEqual({ pin: PIN })
    expect(new Headers(envios[0]?.init.headers).get('Operation-Id')).toMatch(/^[0-9a-f-]{36}$/i)
    const filaDeEva = (await screen.findAllByRole('row')).find((f) => f.textContent?.includes('Eva'))
    await waitFor(() => expect(within(filaDeEva as HTMLElement).queryByText('Sí')).toBeInTheDocument())
    expect(screen.getByRole('button', { name: /cambiar el pin de eva/i })).toBeInTheDocument()
  })

  it('el PIN no queda en ningún almacenamiento del navegador', async () => {
    servidor()
    const usuario = userEvent.setup()
    const escrituras: string[] = []
    const setItem = vi.spyOn(Storage.prototype, 'setItem').mockImplementation((clave, valor) => {
      escrituras.push(`${clave}=${valor}`)
    })
    renderPantalla()
    await screen.findByRole('table', { name: /pin de autorización/i })
    await usuario.click(screen.getByRole('button', { name: /definir el pin de eva/i }))
    const dialogo = await screen.findByRole('dialog', { name: /pin de eva/i })
    await usuario.type(within(dialogo).getByLabelText(/^pin nuevo$/i), PIN)
    await usuario.type(within(dialogo).getByLabelText(/repetí el pin/i), PIN)
    await usuario.click(within(dialogo).getByRole('button', { name: /guardar pin/i }))
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())

    expect(escrituras.some((e) => e.includes(PIN))).toBe(false)
    expect(JSON.stringify({ ...window.localStorage })).not.toContain(PIN)
    expect(JSON.stringify({ ...window.sessionStorage })).not.toContain(PIN)
    setItem.mockRestore()
  })

  it('errores de formato: PIN corto o distinto en las dos veces no se envían', async () => {
    servidor()
    const usuario = userEvent.setup()
    renderPantalla()
    await screen.findByRole('table', { name: /pin de autorización/i })
    await usuario.click(screen.getByRole('button', { name: /definir el pin de eva/i }))
    const dialogo = await screen.findByRole('dialog', { name: /pin de eva/i })

    await usuario.type(within(dialogo).getByLabelText(/^pin nuevo$/i), '123')
    await usuario.type(within(dialogo).getByLabelText(/repetí el pin/i), '123')
    await usuario.click(within(dialogo).getByRole('button', { name: /guardar pin/i }))
    expect(await within(dialogo).findByText(/al menos 6 números/i)).toBeInTheDocument()

    await usuario.clear(within(dialogo).getByLabelText(/^pin nuevo$/i))
    await usuario.clear(within(dialogo).getByLabelText(/repetí el pin/i))
    await usuario.type(within(dialogo).getByLabelText(/^pin nuevo$/i), PIN)
    await usuario.type(within(dialogo).getByLabelText(/repetí el pin/i), '482914')
    await usuario.click(within(dialogo).getByRole('button', { name: /guardar pin/i }))
    expect(await within(dialogo).findByText(/tienen que ser iguales/i)).toBeInTheDocument()
    expect(llamadas(apiFetchMock, 'POST', /\/pin$/)).toHaveLength(0)
  })

  it('un PIN fácil de adivinar lo rechaza el servidor y se explica en palabras; el diálogo queda abierto y el PIN se borró', async () => {
    servidor({
      alRotar: () => ({
        status: 422,
        cuerpo: { title: 'PIN inválido.', codigo: 'IDENTIDAD_PIN_AUTORIZACION_INVALIDO' },
      }),
    })
    const usuario = userEvent.setup()
    renderPantalla()
    await screen.findByRole('table', { name: /pin de autorización/i })
    await usuario.click(screen.getByRole('button', { name: /definir el pin de eva/i }))
    const dialogo = await screen.findByRole('dialog', { name: /pin de eva/i })
    await usuario.type(within(dialogo).getByLabelText(/^pin nuevo$/i), '123456')
    await usuario.type(within(dialogo).getByLabelText(/repetí el pin/i), '123456')
    await usuario.click(within(dialogo).getByRole('button', { name: /guardar pin/i }))

    expect(await within(dialogo).findByText(/no puede ser fácil de adivinar/i)).toBeInTheDocument()
    expect(within(dialogo).getByLabelText(/^pin nuevo$/i)).toHaveValue('')
    expect(within(dialogo).getByLabelText(/repetí el pin/i)).toHaveValue('')
  })

  it('cada envío limpia el rechazo anterior: tras "PIN fácil" un error de formato muestra solo el actual', async () => {
    servidor({
      alRotar: () => ({ status: 422, cuerpo: { title: 'PIN inválido.', codigo: 'IDENTIDAD_PIN_AUTORIZACION_INVALIDO' } }),
    })
    const usuario = userEvent.setup()
    renderPantalla()
    await screen.findByRole('table', { name: /pin de autorización/i })
    await usuario.click(screen.getByRole('button', { name: /definir el pin de eva/i }))
    const dialogo = await screen.findByRole('dialog', { name: /pin de eva/i })
    await usuario.type(within(dialogo).getByLabelText(/^pin nuevo$/i), '123456')
    await usuario.type(within(dialogo).getByLabelText(/repetí el pin/i), '123456')
    await usuario.click(within(dialogo).getByRole('button', { name: /guardar pin/i }))
    expect(await within(dialogo).findByText(/no puede ser fácil de adivinar/i)).toBeInTheDocument()

    await usuario.type(within(dialogo).getByLabelText(/^pin nuevo$/i), '123')
    await usuario.type(within(dialogo).getByLabelText(/repetí el pin/i), '123')
    await usuario.click(within(dialogo).getByRole('button', { name: /guardar pin/i }))
    expect(await within(dialogo).findByText(/al menos 6 números/i)).toBeInTheDocument()
    expect(within(dialogo).queryByText(/no puede ser fácil de adivinar/i)).not.toBeInTheDocument()
  })

  it('cancelar cierra el diálogo y al volver a abrirlo no queda nada escrito', async () => {
    servidor()
    const usuario = userEvent.setup()
    renderPantalla()
    await screen.findByRole('table', { name: /pin de autorización/i })
    await usuario.click(screen.getByRole('button', { name: /definir el pin de eva/i }))
    let dialogo = await screen.findByRole('dialog', { name: /pin de eva/i })
    await usuario.type(within(dialogo).getByLabelText(/^pin nuevo$/i), PIN)
    await usuario.click(within(dialogo).getByRole('button', { name: /^cancelar$/i }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()

    await usuario.click(screen.getByRole('button', { name: /definir el pin de eva/i }))
    dialogo = await screen.findByRole('dialog', { name: /pin de eva/i })
    expect(within(dialogo).getByLabelText(/^pin nuevo$/i)).toHaveValue('')
    expect(llamadas(apiFetchMock, 'POST', /\/pin$/)).toHaveLength(0)
  })
})
