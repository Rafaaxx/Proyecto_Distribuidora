/**
 * Change 17b, tarea 8.1: pestaña "Medios de pago" de Configuración (spec
 * `administracion-de-medios-de-pago`, requisito "La pantalla de medios de pago"; `design.md` D2,
 * D4; TR-09, CAT-05, INV-06, SEG-06, ADR-027, ADR-053).
 */

import { QueryClientProvider, type QueryClient } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }))
vi.mock('../../../../../src/lib/api/httpClient', () => ({ apiFetch: apiFetchMock }))

import ConfiguracionArea from '../../../../../src/areas/admin/configuracion/ConfiguracionArea'
import { clavesConfiguracionDeCompras } from '../../../../../src/features/compras/claves'
import { enrutar, llamadas, type ReglaDeApi } from '../../../utils/enrutarApi'
import { queryClientConYo } from '../../../utils/permisosDePrueba'

const EFECTIVO = '11111111-1111-4111-8111-111111111111'
const TRANSFERENCIA = '22222222-2222-4222-8222-222222222222'
const BILLETERA = '33333333-3333-4333-8333-333333333333'
const MOMENTO = '2026-10-17T12:00:00Z'

interface MedioDeApi {
  id: string
  nombre: string
  requiere_referencia: boolean
  activo: boolean
  actualizado_en: string
}

function medio(id: string, nombre: string, requiere_referencia: boolean, activo = true): MedioDeApi {
  return { id, nombre, requiere_referencia, activo, actualizado_en: MOMENTO }
}

const URL_TODOS = '/configuracion/medios-pago/todos'
const URL_ALTA = '/configuracion/medios-pago'
const URL_MODIFICAR = /^\/configuracion\/medios-pago\/[^/]+$/

/** Un servidor de medios que guarda lo que recibe, como el real (y rechaza lo que el real rechaza). */
function servidor(opciones: { alRecibir?: ReglaDeApi['responder'] } = {}) {
  let medios = [
    medio(EFECTIVO, 'Efectivo', false),
    medio(TRANSFERENCIA, 'Transferencia', true),
    medio(BILLETERA, 'Billetera', false),
  ]
  const reglas: ReglaDeApi[] = [
    { metodo: 'GET', ruta: URL_TODOS, responder: () => ({ status: 200, cuerpo: { items: medios } }) },
    {
      metodo: 'POST',
      ruta: URL_ALTA,
      responder: (url, init) => {
        if (opciones.alRecibir) return opciones.alRecibir(url, init)
        const datos = JSON.parse(String(init?.body)) as { nombre: string; requiere_referencia: boolean }
        const nuevo = medio('44444444-4444-4444-8444-444444444444', datos.nombre, datos.requiere_referencia)
        medios = [...medios, nuevo]
        return { status: 201, cuerpo: nuevo }
      },
    },
    {
      metodo: 'PUT',
      ruta: URL_MODIFICAR,
      responder: (url, init) => {
        if (opciones.alRecibir) return opciones.alRecibir(url, init)
        const id = url.pathname.split('/')[3]
        const datos = JSON.parse(String(init?.body)) as Omit<MedioDeApi, 'id' | 'actualizado_en'>
        medios = medios.map((m) => (m.id === id ? { ...m, ...datos } : m))
        return { status: 200, cuerpo: medios.find((m) => m.id === id) }
      },
    },
  ]
  enrutar(apiFetchMock, reglas)
}

/** Un servidor con "Efectivo" activo y "Billetera" de baja. */
function servidorConBilleteraDeBaja(alModificar?: ReglaDeApi['responder']) {
  enrutar(apiFetchMock, [
    {
      metodo: 'GET',
      ruta: URL_TODOS,
      responder: () => ({
        status: 200,
        cuerpo: { items: [medio(EFECTIVO, 'Efectivo', false), medio(BILLETERA, 'Billetera', false, false)] },
      }),
    },
    {
      metodo: 'PUT',
      ruta: URL_MODIFICAR,
      responder:
        alModificar ?? (() => ({ status: 200, cuerpo: medio(BILLETERA, 'Billetera', false, true) })),
    },
  ])
}

let queryClient: QueryClient

function montar(rol: 'ADM' | 'GES' = 'ADM') {
  queryClient = queryClientConYo(rol)
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/admin/configuracion/medios-pago']}>
        <Routes>
          <Route path="/admin/configuracion/*" element={<ConfiguracionArea />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

function filaDe(nombre: string): HTMLElement {
  return screen.getByText(nombre).closest('tr') as HTMLElement
}

const altas = () => llamadas(apiFetchMock, 'POST', URL_ALTA)
const modificaciones = () => llamadas(apiFetchMock, 'PUT', URL_MODIFICAR)
const operationId = (envio: { init: RequestInit }) => new Headers(envio.init.headers).get('Operation-Id')

describe('pestaña Medios de pago (tarea 8.1)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
    Object.defineProperty(window.navigator, 'onLine', { value: true, configurable: true })
  })
  afterEach(() => {
    vi.clearAllMocks()
  })

  it('lista todos los medios con nombre, "Pide referencia" y estado, y la pestaña está en el menú de Configuración', async () => {
    servidor()
    montar()

    await screen.findByText('Transferencia')
    expect(screen.getByRole('link', { name: 'Medios de pago' })).toHaveAttribute(
      'href',
      '/admin/configuracion/medios-pago',
    )
    expect(within(filaDe('Transferencia')).getByText('Sí')).toBeInTheDocument()
    expect(within(filaDe('Efectivo')).getByText('No')).toBeInTheDocument()
    expect(within(filaDe('Efectivo')).getByText('Activo')).toBeInTheDocument()
  })

  it('muestra "De baja" y la opción "Reactivar" en un medio inactivo, y "Dar de baja" en uno activo', async () => {
    servidorConBilleteraDeBaja()
    montar()

    await screen.findByText('Billetera')
    expect(within(filaDe('Billetera')).getByText('De baja')).toBeInTheDocument()
    expect(within(filaDe('Billetera')).getByRole('button', { name: 'Reactivar Billetera' })).toBeInTheDocument()
    expect(within(filaDe('Billetera')).queryByRole('button', { name: /dar de baja/i })).not.toBeInTheDocument()
    expect(within(filaDe('Efectivo')).getByRole('button', { name: 'Dar de baja Efectivo' })).toBeInTheDocument()
  })

  describe('alta', () => {
    it('agrega "Mercado Pago" con "Pide referencia": el POST lleva el nombre recortado y la marca, con Operation-Id, y aparece en la lista', async () => {
      servidor()
      const usuario = userEvent.setup()
      montar()
      await screen.findByText('Efectivo')
      queryClient.setQueryData(clavesConfiguracionDeCompras.mediosPago(), { items: [] })

      await usuario.click(screen.getByRole('button', { name: 'Nuevo medio de pago' }))
      const dialogo = await screen.findByRole('dialog', { name: 'Nuevo medio de pago' })
      await usuario.type(within(dialogo).getByLabelText('Nombre'), '  Mercado Pago ')
      await usuario.click(within(dialogo).getByLabelText('Pide referencia'))
      await usuario.click(within(dialogo).getByRole('button', { name: 'Guardar' }))

      await waitFor(() => expect(within(filaDe('Mercado Pago')).getByText('Sí')).toBeInTheDocument())
      expect(altas()).toHaveLength(1)
      expect(JSON.parse(String(altas()[0]?.init.body))).toEqual({ nombre: 'Mercado Pago', requiere_referencia: true })
      expect(operationId(altas()[0] as { init: RequestInit })).toBeTruthy()
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
      // Las consultas de medios activos (cobranzas, pagos, compras) quedan para releer.
      expect(queryClient.getQueryState(clavesConfiguracionDeCompras.mediosPago())?.isInvalidated).toBe(true)
    })

    it('sin marcar "Pide referencia" el medio nace sin referencia', async () => {
      servidor()
      const usuario = userEvent.setup()
      montar()
      await screen.findByText('Efectivo')

      await usuario.click(screen.getByRole('button', { name: 'Nuevo medio de pago' }))
      const dialogo = await screen.findByRole('dialog')
      await usuario.type(within(dialogo).getByLabelText('Nombre'), 'Cuenta DNI')
      await usuario.click(within(dialogo).getByRole('button', { name: 'Guardar' }))

      await waitFor(() => expect(within(filaDe('Cuenta DNI')).getByText('No')).toBeInTheDocument())
      expect(JSON.parse(String(altas()[0]?.init.body))).toEqual({ nombre: 'Cuenta DNI', requiere_referencia: false })
    })

    it('un nombre vacío no se envía y avisa', async () => {
      servidor()
      const usuario = userEvent.setup()
      montar()
      await screen.findByText('Efectivo')

      await usuario.click(screen.getByRole('button', { name: 'Nuevo medio de pago' }))
      const dialogo = await screen.findByRole('dialog')
      await usuario.type(within(dialogo).getByLabelText('Nombre'), '   ')
      await usuario.click(within(dialogo).getByRole('button', { name: 'Guardar' }))

      expect(await within(dialogo).findByText(/escribí un nombre/i)).toBeInTheDocument()
      expect(altas()).toHaveLength(0)
    })

    it('NOMBRE_DUPLICADO se explica en palabras simples y el formulario sigue abierto', async () => {
      servidor({
        alRecibir: () => ({ status: 409, cuerpo: { title: 'Nombre duplicado.', codigo: 'NOMBRE_DUPLICADO' } }),
      })
      const usuario = userEvent.setup()
      montar()
      await screen.findByText('Efectivo')

      await usuario.click(screen.getByRole('button', { name: 'Nuevo medio de pago' }))
      const dialogo = await screen.findByRole('dialog')
      await usuario.type(within(dialogo).getByLabelText('Nombre'), 'efectivo')
      await usuario.click(within(dialogo).getByRole('button', { name: 'Guardar' }))

      expect(await within(dialogo).findByText(/ya hay un medio de pago con ese nombre/i)).toBeInTheDocument()
      expect(altas()).toHaveLength(1) // un rechazo de dominio no se reintenta
      expect(screen.getByRole('dialog')).toBeInTheDocument()
    })

    it('el reintento tras un corte de red reenvía el mismo Operation-Id (INV-06), también al volver a pulsar Guardar', async () => {
      let intentos = 0
      servidor({
        alRecibir: () => {
          intentos += 1
          if (intentos <= 3) throw new TypeError('Failed to fetch')
          return { status: 201, cuerpo: medio('44444444-4444-4444-8444-444444444444', 'Mercado Pago', false) }
        },
      })
      const usuario = userEvent.setup()
      montar()
      await screen.findByText('Efectivo')

      await usuario.click(screen.getByRole('button', { name: 'Nuevo medio de pago' }))
      const dialogo = await screen.findByRole('dialog')
      await usuario.type(within(dialogo).getByLabelText('Nombre'), 'Mercado Pago')
      await usuario.click(within(dialogo).getByRole('button', { name: 'Guardar' }))
      expect(await within(dialogo).findByText(/se necesita conexión/i)).toBeInTheDocument()
      await usuario.click(within(dialogo).getByRole('button', { name: 'Guardar' }))

      await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
      const ids = altas().map(operationId)
      expect(ids.length).toBeGreaterThanOrEqual(4)
      expect(new Set(ids).size).toBe(1)
    })
  })

  describe('edición', () => {
    it('editar reemplaza el medio completo: el PUT lleva nombre, marca y el estado que ya tenía', async () => {
      servidor()
      const usuario = userEvent.setup()
      montar()
      await screen.findByText('Billetera')

      await usuario.click(within(filaDe('Billetera')).getByRole('button', { name: 'Editar Billetera' }))
      const dialogo = await screen.findByRole('dialog', { name: 'Editar medio de pago' })
      const nombre = within(dialogo).getByLabelText('Nombre')
      expect(nombre).toHaveValue('Billetera')
      await usuario.clear(nombre)
      await usuario.type(nombre, 'Mercado Pago')
      await usuario.click(within(dialogo).getByLabelText('Pide referencia'))
      await usuario.click(within(dialogo).getByRole('button', { name: 'Guardar' }))

      await waitFor(() => expect(within(filaDe('Mercado Pago')).getByText('Sí')).toBeInTheDocument())
      expect(modificaciones()).toHaveLength(1)
      expect(modificaciones()[0]?.url.pathname).toBe(`/configuracion/medios-pago/${BILLETERA}`)
      expect(JSON.parse(String(modificaciones()[0]?.init.body))).toEqual({
        nombre: 'Mercado Pago',
        requiere_referencia: true,
        activo: true,
      })
    })

    it('editar un medio de baja no lo reactiva', async () => {
      servidorConBilleteraDeBaja(() => ({ status: 200, cuerpo: medio(BILLETERA, 'Billetera', true, false) }))
      const usuario = userEvent.setup()
      montar()
      await screen.findByText('Billetera')

      await usuario.click(within(filaDe('Billetera')).getByRole('button', { name: 'Editar Billetera' }))
      const dialogo = await screen.findByRole('dialog')
      await usuario.click(within(dialogo).getByRole('button', { name: 'Guardar' }))

      await waitFor(() => expect(modificaciones()).toHaveLength(1))
      expect(JSON.parse(String(modificaciones()[0]?.init.body))).toMatchObject({ activo: false })
    })
  })

  describe('baja y reactivación', () => {
    it('dar de baja pide confirmación: antes de confirmar no se envía nada y al confirmar el PUT lleva activo=false', async () => {
      servidor()
      const usuario = userEvent.setup()
      montar()
      await screen.findByText('Billetera')

      await usuario.click(within(filaDe('Billetera')).getByRole('button', { name: 'Dar de baja Billetera' }))
      const dialogo = await screen.findByRole('dialog', { name: 'Dar de baja Billetera' })
      expect(within(dialogo).getByText(/deja de ofrecerse/i)).toBeInTheDocument()
      expect(modificaciones()).toHaveLength(0)
      await usuario.click(within(dialogo).getByRole('button', { name: 'Confirmar baja' }))

      await waitFor(() => expect(within(filaDe('Billetera')).getByText('De baja')).toBeInTheDocument())
      expect(within(filaDe('Billetera')).getByRole('button', { name: 'Reactivar Billetera' })).toBeInTheDocument()
      expect(JSON.parse(String(modificaciones()[0]?.init.body))).toEqual({
        nombre: 'Billetera',
        requiere_referencia: false,
        activo: false,
      })
    })

    it('cancelar la baja no envía nada', async () => {
      servidor()
      const usuario = userEvent.setup()
      montar()
      await screen.findByText('Billetera')

      await usuario.click(within(filaDe('Billetera')).getByRole('button', { name: 'Dar de baja Billetera' }))
      await usuario.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Cancelar' }))

      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
      expect(modificaciones()).toHaveLength(0)
      expect(within(filaDe('Billetera')).getByText('Activo')).toBeInTheDocument()
    })

    it('reactivar también pide confirmación y envía activo=true', async () => {
      servidorConBilleteraDeBaja()
      const usuario = userEvent.setup()
      montar()
      await screen.findByText('Billetera')

      await usuario.click(within(filaDe('Billetera')).getByRole('button', { name: 'Reactivar Billetera' }))
      const dialogo = await screen.findByRole('dialog', { name: 'Reactivar Billetera' })
      expect(modificaciones()).toHaveLength(0)
      await usuario.click(within(dialogo).getByRole('button', { name: 'Confirmar reactivación' }))

      await waitFor(() => expect(modificaciones()).toHaveLength(1))
      expect(JSON.parse(String(modificaciones()[0]?.init.body))).toMatchObject({ activo: true })
    })

    it('ULTIMO_MEDIO_ACTIVO: explica que tiene que quedar uno activo y el medio sigue activo', async () => {
      servidor({
        alRecibir: () => ({ status: 409, cuerpo: { title: 'Último medio.', codigo: 'ULTIMO_MEDIO_ACTIVO' } }),
      })
      const usuario = userEvent.setup()
      montar()
      await screen.findByText('Efectivo')

      await usuario.click(within(filaDe('Efectivo')).getByRole('button', { name: 'Dar de baja Efectivo' }))
      const dialogo = await screen.findByRole('dialog')
      await usuario.click(within(dialogo).getByRole('button', { name: 'Confirmar baja' }))

      expect(
        await within(dialogo).findByText(/tiene que quedar al menos un medio de pago activo/i),
      ).toBeInTheDocument()
      expect(modificaciones()).toHaveLength(1)
      await usuario.click(within(dialogo).getByRole('button', { name: 'Cancelar' }))
      expect(within(filaDe('Efectivo')).getByText('Activo')).toBeInTheDocument()
    })
  })

  describe('sin permiso (ADR-027)', () => {
    it('sin ADMIN_CONFIGURACION no se ofrece la pestaña, la pantalla avisa y no pide nada', async () => {
      servidor()
      montar('GES')

      expect(await screen.findByText(/no tenés permiso/i)).toBeInTheDocument()
      expect(screen.queryByRole('link', { name: 'Medios de pago' })).not.toBeInTheDocument()
      expect(screen.queryByRole('button', { name: 'Nuevo medio de pago' })).not.toBeInTheDocument()
      expect(llamadas(apiFetchMock, 'GET', URL_TODOS)).toHaveLength(0)
    })
  })
})
