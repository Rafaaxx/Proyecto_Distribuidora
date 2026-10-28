/**
 * Change 20, tarea 12.5 (D15): sección "Datos de la organización" de Configuración (spec
 * `organizacion/parametros-de-organizacion`; VTA-13, AUD-01, INV-06, SEG-06, ADR-027).
 */

import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }))
vi.mock('../../../../../src/lib/api/httpClient', () => ({ apiFetch: apiFetchMock }))

import ConfiguracionArea from '../../../../../src/areas/admin/configuracion/ConfiguracionArea'
import { enrutar, llamadas, type ReglaDeApi } from '../../../utils/enrutarApi'
import { queryClientConYo, type RolDePrueba } from '../../../utils/permisosDePrueba'

interface Datos {
  nombre: string
  cuit: string | null
}

const RUTA = '/configuracion/organizacion'

/** Un servidor que guarda lo que recibe, como el real: normaliza el CUIT y valida nombre y CUIT. */
function servidor(inicial: Datos = { nombre: 'Distribuidora Sur', cuit: null }) {
  let actual = inicial
  const reglas: ReglaDeApi[] = [
    { metodo: 'GET', ruta: RUTA, responder: () => ({ status: 200, cuerpo: actual }) },
    {
      metodo: 'POST',
      ruta: RUTA,
      responder: (_url, init) => {
        const datos = JSON.parse(String(init?.body)) as Datos
        const digitos = (datos.cuit ?? '').replace(/[-\s]/g, '')
        if (datos.nombre.trim() === '') {
          return { status: 422, cuerpo: { title: 'El nombre de la organización es obligatorio.', codigo: 'NOMBRE_DE_ORGANIZACION_INVALIDO' } }
        }
        if (digitos !== '' && !/^\d{11}$/.test(digitos)) {
          return { status: 422, cuerpo: { title: 'El CUIT debe tener 11 dígitos.', codigo: 'CUIT_INVALIDO' } }
        }
        actual = { nombre: datos.nombre.trim(), cuit: digitos === '' ? null : digitos }
        return { status: 200, cuerpo: actual }
      },
    },
  ]
  enrutar(apiFetchMock, reglas)
}

function renderPantalla(rol: RolDePrueba = 'ADM') {
  const cliente = queryClientConYo(rol)
  const invalidar = vi.spyOn(cliente, 'invalidateQueries')
  const vista = render(
    <QueryClientProvider client={cliente}>
      <MemoryRouter initialEntries={['/admin/configuracion/organizacion']}>
        <Routes>
          <Route path="/admin/configuracion/*" element={<ConfiguracionArea />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
  return { ...vista, invalidar }
}

function cuerpoDelPost(indice = 0): Record<string, unknown> {
  return JSON.parse(String(llamadas(apiFetchMock, 'POST', RUTA)[indice]?.init.body)) as Record<string, unknown>
}

const GUARDAR = /guardar datos de la organizaci[oó]n/i

describe('Datos de la organización en Configuración (12.5, D15)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
  })
  afterEach(() => {
    vi.clearAllMocks()
  })

  it('el Administrador ve el enlace del menú y los valores vigentes precargados', async () => {
    servidor({ nombre: 'Distribuidora Sur SRL', cuit: '30712345678' })
    renderPantalla('ADM')

    const bloque = await screen.findByTestId('bloque-datos-organizacion')
    expect(within(bloque).getByLabelText(/^nombre$/i)).toHaveValue('Distribuidora Sur SRL')
    expect(within(bloque).getByLabelText(/^cuit$/i)).toHaveValue('30712345678')
    expect(screen.getByRole('link', { name: /^datos de la organizaci[oó]n$/i })).toBeInTheDocument()
    expect(within(bloque).queryByRole('button', { name: /ayuda/i })).not.toBeInTheDocument()
  })

  it('un CUIT nulo se muestra vacío', async () => {
    servidor({ nombre: 'Distribuidora Sur', cuit: null })
    renderPantalla()

    const bloque = await screen.findByTestId('bloque-datos-organizacion')
    expect(within(bloque).getByLabelText(/^cuit$/i)).toHaveValue('')
  })

  it('sin ADMIN_CONFIGURACION no se monta ni pide nada y no hay enlace (ADR-027, SEG-06)', () => {
    servidor()
    renderPantalla('VEN')

    expect(screen.getByText(/no ten[eé]s permiso para cambiar la configuraci[oó]n/i)).toBeInTheDocument()
    expect(llamadas(apiFetchMock, 'GET', RUTA)).toHaveLength(0)
    expect(screen.queryByRole('link', { name: /^datos de la organizaci[oó]n$/i })).not.toBeInTheDocument()
  })

  it('guarda nombre y CUIT con guiones en UNA llamada con su Operation-Id e invalida la nota (INV-06)', async () => {
    servidor()
    const usuario = userEvent.setup()
    const { invalidar } = renderPantalla()
    const bloque = await screen.findByTestId('bloque-datos-organizacion')
    const guardar = within(bloque).getByRole('button', { name: GUARDAR })
    expect(guardar).toBeDisabled()

    const nombre = within(bloque).getByLabelText(/^nombre$/i)
    await usuario.clear(nombre)
    await usuario.type(nombre, 'Distribuidora Norte')
    await usuario.type(within(bloque).getByLabelText(/^cuit$/i), '30-71234567-8')
    await usuario.click(guardar)

    await screen.findByText(/se guardaron los datos de la organizaci[oó]n/i)
    expect(llamadas(apiFetchMock, 'POST', RUTA)).toHaveLength(1)
    expect(cuerpoDelPost()).toEqual({ nombre: 'Distribuidora Norte', cuit: '30-71234567-8' })
    const encabezados = new Headers(llamadas(apiFetchMock, 'POST', RUTA)[0]?.init.headers)
    expect(encabezados.get('Operation-Id')).toMatch(/^[0-9a-f-]{36}$/i)
    expect(invalidar).toHaveBeenCalledWith({ queryKey: ['ventas', 'nota'] })
  })

  it('vaciar el CUIT envía nulo, no texto vacío', async () => {
    servidor({ nombre: 'Distribuidora Sur', cuit: '30712345678' })
    const usuario = userEvent.setup()
    renderPantalla()
    const bloque = await screen.findByTestId('bloque-datos-organizacion')

    await usuario.clear(within(bloque).getByLabelText(/^cuit$/i))
    await usuario.click(within(bloque).getByRole('button', { name: GUARDAR }))

    await screen.findByText(/se guardaron los datos de la organizaci[oó]n/i)
    expect(cuerpoDelPost()).toEqual({ nombre: 'Distribuidora Sur', cuit: null })
  })

  it('vaciar el nombre se bloquea antes de enviar y avisa junto al campo (Zod)', async () => {
    servidor()
    const usuario = userEvent.setup()
    renderPantalla()
    const bloque = await screen.findByTestId('bloque-datos-organizacion')

    await usuario.clear(within(bloque).getByLabelText(/^nombre$/i))
    await usuario.click(within(bloque).getByRole('button', { name: GUARDAR }))

    const campo = await screen.findByTestId('campo-nombre')
    expect(await within(campo).findByRole('alert')).toHaveTextContent(/escrib[ií] el nombre/i)
    expect(llamadas(apiFetchMock, 'POST', RUTA)).toHaveLength(0)
  })

  it('un nombre de solo espacios tampoco se envía', async () => {
    servidor()
    const usuario = userEvent.setup()
    renderPantalla()
    const bloque = await screen.findByTestId('bloque-datos-organizacion')

    const nombre = within(bloque).getByLabelText(/^nombre$/i)
    await usuario.clear(nombre)
    await usuario.type(nombre, '   ')
    await usuario.click(within(bloque).getByRole('button', { name: GUARDAR }))

    await waitFor(() => expect(within(screen.getByTestId('campo-nombre')).getByRole('alert')).toBeInTheDocument())
    expect(llamadas(apiFetchMock, 'POST', RUTA)).toHaveLength(0)
  })

  it('CUIT_INVALIDO se muestra junto al CUIT, conserva el nombre escrito y no dice que se guardó', async () => {
    servidor()
    const usuario = userEvent.setup()
    renderPantalla()
    const bloque = await screen.findByTestId('bloque-datos-organizacion')

    const nombre = within(bloque).getByLabelText(/^nombre$/i)
    await usuario.clear(nombre)
    await usuario.type(nombre, 'Nombre nuevo')
    await usuario.type(within(bloque).getByLabelText(/^cuit$/i), '3071234567')
    await usuario.click(within(bloque).getByRole('button', { name: GUARDAR }))

    const campo = await screen.findByTestId('campo-cuit')
    expect(await within(campo).findByRole('alert')).toHaveTextContent(/el cuit debe tener 11 d[ií]gitos/i)
    expect(within(bloque).getByLabelText(/^nombre$/i)).toHaveValue('Nombre nuevo')
    expect(within(bloque).getByLabelText(/^cuit$/i)).toHaveValue('3071234567')
    expect(screen.queryByText(/se guardaron los datos/i)).not.toBeInTheDocument()
  })

  it('NOMBRE_DE_ORGANIZACION_INVALIDO del servidor se muestra junto al nombre y conserva el CUIT', async () => {
    enrutar(apiFetchMock, [
      { metodo: 'GET', ruta: RUTA, responder: () => ({ status: 200, cuerpo: { nombre: 'Distribuidora Sur', cuit: null } }) },
      {
        metodo: 'POST',
        ruta: RUTA,
        responder: () => ({
          status: 422,
          cuerpo: { title: 'El nombre de la organización no puede superar los 200 caracteres.', codigo: 'NOMBRE_DE_ORGANIZACION_INVALIDO' },
        }),
      },
    ])
    const usuario = userEvent.setup()
    renderPantalla()
    const bloque = await screen.findByTestId('bloque-datos-organizacion')

    await usuario.type(within(bloque).getByLabelText(/^cuit$/i), '30712345678')
    await usuario.type(within(bloque).getByLabelText(/^nombre$/i), ' bis')
    await usuario.click(within(bloque).getByRole('button', { name: GUARDAR }))

    const campo = await screen.findByTestId('campo-nombre')
    expect(await within(campo).findByRole('alert')).toHaveTextContent(/no puede superar los 200 caracteres/i)
    expect(within(bloque).getByLabelText(/^cuit$/i)).toHaveValue('30712345678')
  })

  it('un error de red se avisa con el mensaje de reintento', async () => {
    enrutar(apiFetchMock, [
      { metodo: 'GET', ruta: RUTA, responder: () => ({ status: 200, cuerpo: { nombre: 'Distribuidora Sur', cuit: null } }) },
      {
        metodo: 'POST',
        ruta: RUTA,
        responder: () => {
          throw new TypeError('network')
        },
      },
    ])
    const usuario = userEvent.setup()
    renderPantalla()
    const bloque = await screen.findByTestId('bloque-datos-organizacion')

    await usuario.type(within(bloque).getByLabelText(/^cuit$/i), '30712345678')
    await usuario.click(within(bloque).getByRole('button', { name: GUARDAR }))

    expect(await within(bloque).findByRole('alert')).toHaveTextContent(/no se pudo guardar/i)
  })
})
