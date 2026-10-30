/**
 * Change 16, tarea 15.4 (gobernanza crítica, D13): pantalla "Topes por rol" (spec
 * `administracion-de-descuentos`, requisito "El tope de descuento manual de cada rol se define
 * desde la pantalla"; DSC-06, TR-02, INV-03, INV-06, SEG-06; `01` §19). Solo el tope: no cambia
 * permisos de rol ni el tope propio de un usuario.
 */

import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }))
vi.mock('../../../../../src/lib/api/httpClient', () => ({ apiFetch: apiFetchMock }))

import DescuentosArea from '../../../../../src/areas/admin/descuentos/DescuentosArea'
import { enrutar, llamadas, type ReglaDeApi } from '../../../utils/enrutarApi'
import { queryClientConYo } from '../../../utils/permisosDePrueba'
import { ROL_ADMINISTRADOR_ID, ROL_SUPERVISOR_ID, ROL_VENDEDOR_ID, ROLES, rol } from './descuentosDePrueba'

function montar() {
  return render(
    <QueryClientProvider client={queryClientConYo('ADM')}>
      <MemoryRouter initialEntries={['/admin/descuentos/topes']}>
        <Routes>
          <Route path="/admin/descuentos/*" element={<DescuentosArea />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

/** Un servidor de roles que guarda el tope que recibe, como el real. */
function servidorDeRoles(extra: ReglaDeApi[] = []) {
  let roles = ROLES.map((r) => ({ ...r }))
  enrutar(apiFetchMock, [
    ...extra,
    { metodo: 'GET', ruta: '/identidad/roles', responder: () => ({ status: 200, cuerpo: roles }) },
    {
      metodo: 'PUT',
      ruta: /^\/identidad\/roles\/[^/]+\/tope-descuento$/,
      responder: (url, init) => {
        const id = url.pathname.split('/')[3]
        const tope = (JSON.parse(String(init?.body)) as { tope_descuento: string }).tope_descuento
        roles = roles.map((r) => (r.id === id ? { ...r, tope_descuento: tope } : r))
        return { status: 200, cuerpo: roles.find((r) => r.id === id) }
      },
    },
  ])
}

function filaDe(nombre: string): HTMLElement {
  return screen.getByText(nombre).closest('tr') as HTMLElement
}

function envios() {
  return llamadas(apiFetchMock, 'PUT', /^\/identidad\/roles\/[^/]+\/tope-descuento$/)
}

describe('Topes por rol: usuarios con tope propio (change 20b, tarea 10.2, D12, tarea 8.6)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
    Object.defineProperty(window.navigator, 'onLine', { value: true, configurable: true })
  })
  afterEach(() => {
    vi.clearAllMocks()
  })

  function servidorConTopesPropios() {
    const roles = [
      rol({ id: ROL_VENDEDOR_ID, nombre: 'Vendedor/Repartidor', usuarios_con_tope_propio: 3, usuarios_con_tope_propio_activos: 2, usuarios_con_tope_propio_inactivos: 1 }),
      rol({ id: ROL_SUPERVISOR_ID, nombre: 'Supervisor comercial', usuarios_con_tope_propio: 2, usuarios_con_tope_propio_activos: 2, usuarios_con_tope_propio_inactivos: 0 }),
      rol({ id: ROL_ADMINISTRADOR_ID, nombre: 'Administrador', usuarios_con_tope_propio: 0 }),
    ]
    enrutar(apiFetchMock, [{ metodo: 'GET', ruta: '/identidad/roles', responder: () => ({ status: 200, cuerpo: roles }) }])
  }

  it('muestra "3 (1 inactivo)" y, sin inactivos, solo el número', async () => {
    servidorConTopesPropios()
    montar()

    await screen.findByText('Vendedor/Repartidor')
    expect(within(filaDe('Vendedor/Repartidor')).getByText('3 (1 inactivo)')).toBeInTheDocument()
    expect(within(filaDe('Supervisor comercial')).getByText('2')).toBeInTheDocument()
    expect(within(filaDe('Administrador')).getByText('0')).toBeInTheDocument()
  })

  it('el número enlaza al listado de usuarios de ese rol con tope propio; el cero no enlaza', async () => {
    servidorConTopesPropios()
    montar()

    await screen.findByText('Vendedor/Repartidor')
    const enlace = within(filaDe('Vendedor/Repartidor')).getByRole('link', { name: '3 (1 inactivo)' })
    expect(enlace).toHaveAttribute('href', `/admin/usuarios?rol_id=${ROL_VENDEDOR_ID}&con_tope_propio=true`)
    expect(within(filaDe('Administrador')).queryByRole('link')).not.toBeInTheDocument()
  })

  it('no ofrece selector de activos o todos: el filtro de estado del listado cumple esa función', async () => {
    servidorConTopesPropios()
    montar()

    await screen.findByText('Vendedor/Repartidor')
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument()
  })
})

describe('pantalla Topes por rol (tarea 15.4)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
    Object.defineProperty(window.navigator, 'onLine', { value: true, configurable: true })
  })
  afterEach(() => {
    vi.clearAllMocks()
  })

  it('lista los roles con su tope como porcentaje, y "Sin tope" cuando es 100 %', async () => {
    servidorDeRoles()
    montar()

    await screen.findByText('Administrador')
    expect(within(filaDe('Administrador')).getByText('Sin tope')).toBeInTheDocument()
    expect(within(filaDe('Supervisor comercial')).getByText('10 %')).toBeInTheDocument()
    expect(within(filaDe('Vendedor/Repartidor')).getByText('0 %')).toBeInTheDocument()
    expect(llamadas(apiFetchMock, 'GET', '/identidad/roles')).toHaveLength(1)
  })

  it('Escenario aviso de tope cero: solo los roles con 0 % y DESCUENTO_MANUAL avisan que necesitan autorización para cualquier descuento manual', async () => {
    servidorDeRoles()
    montar()

    await screen.findByText('Vendedor/Repartidor')
    const aviso = /necesita autorización para cualquier descuento manual/i
    expect(within(filaDe('Vendedor/Repartidor')).getByText(aviso)).toBeInTheDocument()
    // Tope 0 % pero sin el permiso de descuento manual: no hay nada que avisar.
    expect(within(filaDe('Administración')).queryByText(aviso)).not.toBeInTheDocument()
    expect(within(filaDe('Administrador')).queryByText(aviso)).not.toBeInTheDocument()
    expect(within(filaDe('Supervisor comercial')).queryByText(aviso)).not.toBeInTheDocument()
  })

  it('Escenario definir el tope del Vendedor: escribe 5, confirma, el comando lleva "0.050000" y el listado muestra 5 %', async () => {
    servidorDeRoles()
    const usuario = userEvent.setup()
    montar()
    await screen.findByText('Vendedor/Repartidor')

    await usuario.click(within(filaDe('Vendedor/Repartidor')).getByRole('button', { name: /definir tope/i }))
    const dialogo = await screen.findByRole('dialog', { name: /tope de descuento/i })
    await usuario.type(within(dialogo).getByLabelText(/tope de descuento \(%\)/i), '5')
    expect(within(dialogo).getByText(/de 0 % a 5 %/i)).toBeInTheDocument()
    expect(envios()).toHaveLength(0)
    await usuario.click(within(dialogo).getByRole('button', { name: /confirmar tope/i }))

    await waitFor(() => expect(within(filaDe('Vendedor/Repartidor')).getByText('5 %')).toBeInTheDocument())
    expect(envios()).toHaveLength(1)
    expect(envios()[0]?.url.pathname).toBe(`/identidad/roles/${ROL_VENDEDOR_ID}/tope-descuento`)
    expect(new Headers(envios()[0]?.init.headers).get('Operation-Id')).toBeTruthy()
    expect(JSON.parse(String(envios()[0]?.init.body))).toEqual({ tope_descuento: '0.050000' })
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    // Ya no tiene tope cero: el aviso desaparece de esa fila.
    expect(within(filaDe('Vendedor/Repartidor')).queryByText(/necesita autorización/i)).not.toBeInTheDocument()
  })

  it('el formulario parte del tope actual, y 100 se resume como "Sin tope"', async () => {
    servidorDeRoles()
    const usuario = userEvent.setup()
    montar()
    await screen.findByText('Supervisor comercial')

    await usuario.click(within(filaDe('Supervisor comercial')).getByRole('button', { name: /definir tope/i }))
    const dialogo = await screen.findByRole('dialog')
    const campo = within(dialogo).getByLabelText(/tope de descuento \(%\)/i)
    expect(campo).toHaveValue('10')
    await usuario.clear(campo)
    await usuario.type(campo, '100')

    expect(within(dialogo).getByText(/de 10 % a sin tope/i)).toBeInTheDocument()
  })

  it('cancelar no envía nada', async () => {
    servidorDeRoles()
    const usuario = userEvent.setup()
    montar()
    await screen.findByText('Vendedor/Repartidor')
    await usuario.click(within(filaDe('Vendedor/Repartidor')).getByRole('button', { name: /definir tope/i }))

    await usuario.click(within(await screen.findByRole('dialog')).getByRole('button', { name: /cancelar/i }))

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(envios()).toHaveLength(0)
  })

  it.each(['120', '100,01', '-1', 'abc', ''])(
    'Escenario tope fuera de rango: "%s" se señala junto al campo y no envía nada',
    async (escrito) => {
      servidorDeRoles()
      const usuario = userEvent.setup()
      montar()
      await screen.findByText('Vendedor/Repartidor')
      await usuario.click(within(filaDe('Vendedor/Repartidor')).getByRole('button', { name: /definir tope/i }))
      const dialogo = await screen.findByRole('dialog')
      const campo = within(dialogo).getByLabelText(/tope de descuento \(%\)/i)

      await usuario.clear(campo)
      if (escrito) await usuario.type(campo, escrito)
      await usuario.click(within(dialogo).getByRole('button', { name: /confirmar tope/i }))

      expect(await within(dialogo).findByText(/porcentaje de 0 a 100/i)).toBeInTheDocument()
      expect(envios()).toHaveLength(0)
    },
  )

  it('el rechazo IDENTIDAD_TOPE_DESCUENTO_FUERA_DE_RANGO del servidor se muestra junto al campo', async () => {
    servidorDeRoles([
      {
        metodo: 'PUT',
        ruta: /^\/identidad\/roles\/[^/]+\/tope-descuento$/,
        responder: () => ({ status: 422, cuerpo: { title: 'El tope debe estar entre 0 y 1.', codigo: 'IDENTIDAD_TOPE_DESCUENTO_FUERA_DE_RANGO' } }),
      },
    ])
    const usuario = userEvent.setup()
    montar()
    await screen.findByText('Vendedor/Repartidor')
    await usuario.click(within(filaDe('Vendedor/Repartidor')).getByRole('button', { name: /definir tope/i }))
    const dialogo = await screen.findByRole('dialog')

    await usuario.type(within(dialogo).getByLabelText(/tope de descuento \(%\)/i), '5')
    await usuario.click(within(dialogo).getByRole('button', { name: /confirmar tope/i }))

    const mensaje = await within(dialogo).findByText('El tope debe estar entre 0 y 1.')
    expect(mensaje.closest('div')).toContainElement(within(dialogo).getByLabelText(/tope de descuento \(%\)/i))
    expect(screen.getByRole('dialog')).toBeInTheDocument()
  })

  it('reintentar el mismo tope tras perder la respuesta reenvía el mismo operation_id', async () => {
    let puts = 0
    apiFetchMock.mockImplementation((ruta: string, init?: RequestInit) => {
      if ((init?.method ?? 'GET') === 'PUT') {
        puts += 1
        if (puts <= 3) return Promise.reject(new TypeError('Failed to fetch'))
        return Promise.resolve({ ok: true, status: 200, json: async () => rol({ tope_descuento: '0.050000' }) })
      }
      return Promise.resolve({ ok: true, status: 200, json: async () => ROLES })
    })
    const usuario = userEvent.setup()
    montar()
    await screen.findByText('Vendedor/Repartidor')
    await usuario.click(within(filaDe('Vendedor/Repartidor')).getByRole('button', { name: /definir tope/i }))
    const dialogo = await screen.findByRole('dialog')
    await usuario.type(within(dialogo).getByLabelText(/tope de descuento \(%\)/i), '5')

    await usuario.click(within(dialogo).getByRole('button', { name: /confirmar tope/i }))
    expect(await within(dialogo).findByText(/se necesita conexión/i)).toBeInTheDocument()
    await usuario.click(within(dialogo).getByRole('button', { name: /confirmar tope/i }))

    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    const ids = envios().map((e) => new Headers(e.init.headers).get('Operation-Id'))
    expect(ids).toHaveLength(4)
    expect(new Set(ids).size).toBe(1)
  })

  it('sin conexión avisa y no envía nada', async () => {
    Object.defineProperty(window.navigator, 'onLine', { value: false, configurable: true })
    servidorDeRoles()
    const usuario = userEvent.setup()
    montar()
    await screen.findByText('Vendedor/Repartidor')
    await usuario.click(within(filaDe('Vendedor/Repartidor')).getByRole('button', { name: /definir tope/i }))
    const dialogo = await screen.findByRole('dialog')

    await usuario.type(within(dialogo).getByLabelText(/tope de descuento \(%\)/i), '5')
    await usuario.click(within(dialogo).getByRole('button', { name: /confirmar tope/i }))

    expect(await within(dialogo).findByText(/se necesita conexión para completar esta operación/i)).toBeInTheDocument()
    expect(envios()).toHaveLength(0)
  })

  it('la pantalla solo cambia el tope: no ofrece tocar permisos ni topes de usuarios', async () => {
    servidorDeRoles()
    montar()

    await screen.findByText('Administración')

    expect(screen.queryByRole('button', { name: /permisos/i })).not.toBeInTheDocument()
    expect(screen.getAllByRole('button').map((b) => b.textContent)).toEqual(Array(ROLES.length).fill('Definir tope'))
    expect(screen.queryByRole('link', { name: /usuarios?/i })).not.toBeInTheDocument()
  })

  it('si falla la lectura de roles, lo avisa; si el servidor responde 403, avisa la falta de permiso', async () => {
    enrutar(apiFetchMock, [
      { metodo: 'GET', ruta: '/identidad/roles', responder: () => ({ status: 403, cuerpo: { title: 'Sin permiso', codigo: 'PERMISO_REQUERIDO' } }) },
    ])
    montar()

    expect(await screen.findByText(/no tenés permiso para definir los topes de descuento/i)).toBeInTheDocument()
  })

  it('un error de lectura distinto de 403 se informa', async () => {
    enrutar(apiFetchMock, [
      { metodo: 'GET', ruta: '/identidad/roles', responder: () => ({ status: 500, cuerpo: { title: 'Error', codigo: 'ERROR_INTERNO' } }) },
    ])
    montar()

    expect(await screen.findByText(/no se pudieron obtener los roles/i)).toBeInTheDocument()
  })
})
