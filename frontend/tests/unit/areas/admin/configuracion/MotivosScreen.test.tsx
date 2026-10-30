/**
 * Change 20c, tarea 7.2: pestaña "Motivos" de Configuración (spec `administracion-de-motivos`,
 * requisito "La pantalla de motivos"; `design.md` D2, D4, D12; TR-09, CAT-05, INV-06, ADR-027,
 * ADR-061). Incluye los "(?)" de la tarea 9.1.
 */

import { QueryClientProvider, type QueryClient } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }))
vi.mock('../../../../../src/lib/api/httpClient', () => ({ apiFetch: apiFetchMock }))

import ConfiguracionArea from '../../../../../src/areas/admin/configuracion/ConfiguracionArea'
import { AYUDAS } from '../../../../../src/ayuda/textos'
import { clavesConfiguracionDeCompras } from '../../../../../src/features/compras/claves'
import { enrutar, llamadas, type ReglaDeApi } from '../../../utils/enrutarApi'
import { queryClientConYo } from '../../../utils/permisosDePrueba'

const ROBO = '11111111-1111-4111-8111-111111111111'
const ROTURA = '22222222-2222-4222-8222-222222222222'
const VENCIDO = '33333333-3333-4333-8333-333333333333'
const MOMENTO = '2026-10-30T12:00:00Z'

interface MotivoDeApi {
  id: string
  ambito: string
  nombre: string
  activo: boolean
  actualizado_en: string
}

function motivo(id: string, nombre: string, activo = true, ambito = 'AJUSTE_STOCK'): MotivoDeApi {
  return { id, ambito, nombre, activo, actualizado_en: MOMENTO }
}

const URL_TODOS = '/configuracion/motivos/todos'
const URL_ALTA = '/configuracion/motivos'
const URL_MODIFICAR = /^\/configuracion\/motivos\/[^/]+$/

/** Un servidor que guarda lo que recibe, como el real; `alRecibir` fuerza una respuesta a las escrituras. */
function servidor(opciones: { alRecibir?: ReglaDeApi['responder']; motivos?: MotivoDeApi[] } = {}) {
  let motivos = opciones.motivos ?? [motivo(ROBO, 'Robo'), motivo(ROTURA, 'Rotura'), motivo(VENCIDO, 'Vencido', false)]
  enrutar(apiFetchMock, [
    {
      metodo: 'GET',
      ruta: URL_TODOS,
      responder: (url) => ({
        status: 200,
        cuerpo: { items: motivos.filter((m) => m.ambito === url.searchParams.get('ambito')) },
      }),
    },
    {
      metodo: 'POST',
      ruta: URL_ALTA,
      responder: (url, init) => {
        if (opciones.alRecibir) return opciones.alRecibir(url, init)
        const datos = JSON.parse(String(init?.body)) as { ambito: string; nombre: string }
        const nuevo = motivo('44444444-4444-4444-8444-444444444444', datos.nombre, true, datos.ambito)
        motivos = [...motivos, nuevo]
        return { status: 201, cuerpo: nuevo }
      },
    },
    {
      metodo: 'PUT',
      ruta: URL_MODIFICAR,
      responder: (url, init) => {
        if (opciones.alRecibir) return opciones.alRecibir(url, init)
        const id = url.pathname.split('/')[3]
        const datos = JSON.parse(String(init?.body)) as { nombre: string; activo: boolean }
        motivos = motivos.map((m) => (m.id === id ? { ...m, ...datos } : m))
        return { status: 200, cuerpo: motivos.find((m) => m.id === id) }
      },
    },
  ])
}

let queryClient: QueryClient

function montar(rol: 'ADM' | 'GES' = 'ADM') {
  queryClient = queryClientConYo(rol)
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/admin/configuracion/motivos']}>
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

describe('pestaña Motivos (tarea 7.2)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
    Object.defineProperty(window.navigator, 'onLine', { value: true, configurable: true })
  })
  afterEach(() => {
    vi.clearAllMocks()
  })

  it('la pestaña está en el menú; lista los motivos del ámbito con su estado y pide el ámbito elegido', async () => {
    servidor()
    montar()

    await screen.findByText('Rotura')
    expect(screen.getByRole('link', { name: 'Motivos' })).toHaveAttribute('href', '/admin/configuracion/motivos')
    expect(within(filaDe('Rotura')).getByText('Activo')).toBeInTheDocument()
    expect(within(filaDe('Vencido')).getByText('De baja')).toBeInTheDocument()
    expect(llamadas(apiFetchMock, 'GET', URL_TODOS)[0]?.url.searchParams.get('ambito')).toBe('AJUSTE_STOCK')
  })

  it('el selector ofrece los diez ámbitos con su nombre en castellano y al cambiarlo pide los de ese ámbito', async () => {
    servidor({
      motivos: [motivo(ROBO, 'Robo'), motivo(ROTURA, 'Otro', true, 'LIBERACION_JORNADA')],
    })
    const usuario = userEvent.setup()
    montar()
    await screen.findByText('Robo')

    const selector = screen.getByLabelText('Ámbito')
    expect(within(selector).getAllByRole('option')).toHaveLength(10)
    await usuario.selectOptions(selector, 'Liberación de jornada')

    expect(await screen.findByText('Otro')).toBeInTheDocument()
    expect(screen.queryByText('Robo')).not.toBeInTheDocument()
  })

  describe('alta', () => {
    it('crea "Robo" en el ámbito elegido: el POST lleva ámbito y nombre recortado, con Operation-Id; se invalidan los motivos por ámbito', async () => {
      servidor({ motivos: [motivo(ROTURA, 'Rotura')] })
      const usuario = userEvent.setup()
      montar()
      await screen.findByText('Rotura')
      queryClient.setQueryData(clavesConfiguracionDeCompras.motivos('AJUSTE_STOCK'), { items: [] })

      await usuario.click(screen.getByRole('button', { name: 'Nuevo motivo' }))
      const dialogo = await screen.findByRole('dialog', { name: 'Nuevo motivo' })
      await usuario.type(within(dialogo).getByLabelText('Nombre'), '  Robo ')
      await usuario.click(within(dialogo).getByRole('button', { name: 'Guardar' }))

      await waitFor(() => expect(filaDe('Robo')).toBeInTheDocument())
      expect(altas()).toHaveLength(1)
      expect(JSON.parse(String(altas()[0]?.init.body))).toEqual({ ambito: 'AJUSTE_STOCK', nombre: 'Robo' })
      expect(operationId(altas()[0] as { init: RequestInit })).toBeTruthy()
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
      expect(queryClient.getQueryState(clavesConfiguracionDeCompras.motivos('AJUSTE_STOCK'))?.isInvalidated).toBe(true)
    })

    it('un nombre vacío no se envía y avisa', async () => {
      servidor()
      const usuario = userEvent.setup()
      montar()
      await screen.findByText('Rotura')

      await usuario.click(screen.getByRole('button', { name: 'Nuevo motivo' }))
      const dialogo = await screen.findByRole('dialog')
      await usuario.type(within(dialogo).getByLabelText('Nombre'), '   ')
      await usuario.click(within(dialogo).getByRole('button', { name: 'Guardar' }))

      expect(await within(dialogo).findByText(/escribí un nombre/i)).toBeInTheDocument()
      expect(altas()).toHaveLength(0)
    })

    it('NOMBRE_DUPLICADO se explica en palabras simples, sin reintentar, y el formulario sigue abierto', async () => {
      servidor({ alRecibir: () => ({ status: 409, cuerpo: { title: 'Duplicado.', codigo: 'NOMBRE_DUPLICADO' } }) })
      const usuario = userEvent.setup()
      montar()
      await screen.findByText('Rotura')

      await usuario.click(screen.getByRole('button', { name: 'Nuevo motivo' }))
      const dialogo = await screen.findByRole('dialog')
      await usuario.type(within(dialogo).getByLabelText('Nombre'), 'robo')
      await usuario.click(within(dialogo).getByRole('button', { name: 'Guardar' }))

      expect(await within(dialogo).findByText(/ya hay un motivo con ese nombre/i)).toBeInTheDocument()
      expect(altas()).toHaveLength(1)
      expect(screen.getByRole('dialog')).toBeInTheDocument()
    })

    it('NOMBRE_INVALIDO del servidor se explica en palabras simples', async () => {
      servidor({ alRecibir: () => ({ status: 422, cuerpo: { title: 'Inválido.', codigo: 'NOMBRE_INVALIDO' } }) })
      const usuario = userEvent.setup()
      montar()
      await screen.findByText('Rotura')

      await usuario.click(screen.getByRole('button', { name: 'Nuevo motivo' }))
      const dialogo = await screen.findByRole('dialog')
      await usuario.type(within(dialogo).getByLabelText('Nombre'), 'x')
      await usuario.click(within(dialogo).getByRole('button', { name: 'Guardar' }))

      expect(await within(dialogo).findByText(/escribí un nombre para el motivo/i)).toBeInTheDocument()
    })

    it('el reintento tras un corte de red reenvía el mismo Operation-Id (INV-06)', async () => {
      let intentos = 0
      servidor({
        alRecibir: () => {
          intentos += 1
          if (intentos <= 3) throw new TypeError('Failed to fetch')
          return { status: 201, cuerpo: motivo('44444444-4444-4444-8444-444444444444', 'Robo') }
        },
      })
      const usuario = userEvent.setup()
      montar()
      await screen.findByText('Rotura')

      await usuario.click(screen.getByRole('button', { name: 'Nuevo motivo' }))
      const dialogo = await screen.findByRole('dialog')
      await usuario.type(within(dialogo).getByLabelText('Nombre'), 'Robo')
      await usuario.click(within(dialogo).getByRole('button', { name: 'Guardar' }))
      expect(await within(dialogo).findByText(/se necesita conexión/i)).toBeInTheDocument()
      await usuario.click(within(dialogo).getByRole('button', { name: 'Guardar' }))

      await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
      expect(new Set(altas().map(operationId)).size).toBe(1)
    })
  })

  describe('edición, baja y reactivación', () => {
    it('cambiar el nombre es un reemplazo completo que conserva el estado, sin campo de ámbito', async () => {
      servidor()
      const usuario = userEvent.setup()
      montar()
      await screen.findByText('Vencido')

      await usuario.click(within(filaDe('Vencido')).getByRole('button', { name: 'Editar Vencido' }))
      const dialogo = await screen.findByRole('dialog', { name: 'Editar motivo' })
      expect(within(dialogo).queryByLabelText('Ámbito')).not.toBeInTheDocument()
      const nombre = within(dialogo).getByLabelText('Nombre')
      expect(nombre).toHaveValue('Vencido')
      await usuario.clear(nombre)
      await usuario.type(nombre, 'Producto vencido')
      await usuario.click(within(dialogo).getByRole('button', { name: 'Guardar' }))

      await waitFor(() => expect(filaDe('Producto vencido')).toBeInTheDocument())
      expect(modificaciones()[0]?.url.pathname).toBe(`/configuracion/motivos/${VENCIDO}`)
      expect(JSON.parse(String(modificaciones()[0]?.init.body))).toEqual({ nombre: 'Producto vencido', activo: false })
    })

    it('dar de baja pide confirmación: antes no se envía nada y al confirmar el PUT lleva activo=false', async () => {
      servidor()
      const usuario = userEvent.setup()
      montar()
      await screen.findByText('Robo')

      await usuario.click(within(filaDe('Robo')).getByRole('button', { name: 'Dar de baja Robo' }))
      const dialogo = await screen.findByRole('dialog', { name: 'Dar de baja Robo' })
      expect(modificaciones()).toHaveLength(0)
      await usuario.click(within(dialogo).getByRole('button', { name: 'Confirmar baja' }))

      await waitFor(() => expect(within(filaDe('Robo')).getByText('De baja')).toBeInTheDocument())
      expect(JSON.parse(String(modificaciones()[0]?.init.body))).toEqual({ nombre: 'Robo', activo: false })
      expect(operationId(modificaciones()[0] as { init: RequestInit })).toBeTruthy()
    })

    it('cancelar la baja no envía nada', async () => {
      servidor()
      const usuario = userEvent.setup()
      montar()
      await screen.findByText('Robo')

      await usuario.click(within(filaDe('Robo')).getByRole('button', { name: 'Dar de baja Robo' }))
      await usuario.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Cancelar' }))

      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
      expect(modificaciones()).toHaveLength(0)
    })

    it('reactivar también pide confirmación y envía activo=true', async () => {
      servidor()
      const usuario = userEvent.setup()
      montar()
      await screen.findByText('Vencido')

      await usuario.click(within(filaDe('Vencido')).getByRole('button', { name: 'Reactivar Vencido' }))
      const dialogo = await screen.findByRole('dialog', { name: 'Reactivar Vencido' })
      expect(modificaciones()).toHaveLength(0)
      await usuario.click(within(dialogo).getByRole('button', { name: 'Confirmar reactivación' }))

      await waitFor(() => expect(within(filaDe('Vencido')).getByText('Activo')).toBeInTheDocument())
      expect(JSON.parse(String(modificaciones()[0]?.init.body))).toEqual({ nombre: 'Vencido', activo: true })
    })

    it('ULTIMO_MOTIVO_ACTIVO se explica en palabras simples y el motivo sigue activo', async () => {
      servidor({ alRecibir: () => ({ status: 409, cuerpo: { title: 'Último.', codigo: 'ULTIMO_MOTIVO_ACTIVO' } }) })
      const usuario = userEvent.setup()
      montar()
      await screen.findByText('Robo')

      await usuario.click(within(filaDe('Robo')).getByRole('button', { name: 'Dar de baja Robo' }))
      const dialogo = await screen.findByRole('dialog')
      await usuario.click(within(dialogo).getByRole('button', { name: 'Confirmar baja' }))

      expect(await within(dialogo).findByText(/al menos un motivo activo/i)).toBeInTheDocument()
      await usuario.click(within(dialogo).getByRole('button', { name: 'Cancelar' }))
      expect(within(filaDe('Robo')).getByText('Activo')).toBeInTheDocument()
    })
  })

  describe('ayuda contextual (tarea 9.1; textos aprobados el 2026-10-30)', () => {
    it('el selector, el nombre y la baja traen su "(?)" con el texto aprobado', async () => {
      servidor()
      const usuario = userEvent.setup()
      montar()
      await screen.findByText('Robo')

      await usuario.click(screen.getByRole('button', { name: `Ayuda: ${AYUDAS['motivos.ambito'].titulo}` }))
      expect(await screen.findByText(AYUDAS['motivos.ambito'].texto)).toBeInTheDocument()

      await usuario.click(screen.getAllByRole('button', { name: `Ayuda: ${AYUDAS['motivos.baja'].titulo}` })[0] as HTMLElement)
      expect(await screen.findByText(AYUDAS['motivos.baja'].texto)).toBeInTheDocument()

      await usuario.click(screen.getByRole('button', { name: 'Nuevo motivo' }))
      const dialogo = await screen.findByRole('dialog')
      await usuario.click(within(dialogo).getByRole('button', { name: `Ayuda: ${AYUDAS['motivos.nombre'].titulo}` }))
      expect(await screen.findByText(AYUDAS['motivos.nombre'].texto)).toBeInTheDocument()
    })
  })

  describe('sin permiso (ADR-027)', () => {
    it('sin ADMIN_CONFIGURACION no se ofrece la pestaña, la pantalla avisa y no pide nada', async () => {
      servidor()
      montar('GES')

      expect(screen.queryByRole('link', { name: 'Motivos' })).not.toBeInTheDocument()
      expect(screen.queryByRole('button', { name: 'Nuevo motivo' })).not.toBeInTheDocument()
      expect(llamadas(apiFetchMock, 'GET', URL_TODOS)).toHaveLength(0)
    })
  })
})
