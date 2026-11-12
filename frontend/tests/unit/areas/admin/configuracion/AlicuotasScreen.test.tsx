/**
 * Change 20c, tarea 7.3: pestaña "Alícuotas de IVA" de Configuración (spec `administracion-de-alicuotas`,
 * requisito "La pantalla de alícuotas de IVA"; `design.md` D6, D7, D8, D12; TR-02, CAT-01, CAT-05,
 * INV-03, INV-06, ADR-027, ADR-061). Incluye los "(?)" de la tarea 9.1.
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
import { clavesConfiguracion } from '../../../../../src/features/configuracion/claves'
import { enrutar, llamadas, type ReglaDeApi } from '../../../utils/enrutarApi'
import { queryClientConYo } from '../../../utils/permisosDePrueba'

const IVA21 = '11111111-1111-4111-8111-111111111111'
const IVA105 = '22222222-2222-4222-8222-222222222222'
const IVA0 = '33333333-3333-4333-8333-333333333333'

interface AlicuotaDeApi {
  id: string
  nombre: string
  valor: string
  activo: boolean
}

function alicuota(id: string, nombre: string, valor: string, activo = true): AlicuotaDeApi {
  return { id, nombre, valor, activo }
}

const URL_LISTA = '/configuracion/alicuotas'
const URL_MODIFICAR = /^\/configuracion\/alicuotas\/[^/]+$/

function servidor(opciones: { alRecibir?: ReglaDeApi['responder'] } = {}) {
  let alicuotas = [
    alicuota(IVA21, '21%', '0.210000'),
    alicuota(IVA105, '10,5%', '0.105000'),
    alicuota(IVA0, 'Exento', '0.000000', false),
  ]
  enrutar(apiFetchMock, [
    {
      metodo: 'GET',
      ruta: URL_LISTA,
      responder: () => ({ status: 200, cuerpo: { items: alicuotas, cursor_siguiente: null } }),
    },
    {
      metodo: 'POST',
      ruta: URL_LISTA,
      responder: (url, init) => {
        if (opciones.alRecibir) return opciones.alRecibir(url, init)
        const datos = JSON.parse(String(init?.body)) as { nombre: string; valor: string }
        const nueva = alicuota('44444444-4444-4444-8444-444444444444', datos.nombre, datos.valor)
        alicuotas = [...alicuotas, nueva]
        return { status: 201, cuerpo: nueva }
      },
    },
    {
      metodo: 'PUT',
      ruta: URL_MODIFICAR,
      responder: (url, init) => {
        if (opciones.alRecibir) return opciones.alRecibir(url, init)
        const id = url.pathname.split('/')[3]
        const datos = JSON.parse(String(init?.body)) as { nombre: string; activo: boolean }
        alicuotas = alicuotas.map((a) => (a.id === id ? { ...a, ...datos } : a))
        return { status: 200, cuerpo: alicuotas.find((a) => a.id === id) }
      },
    },
  ])
}

let queryClient: QueryClient

function montar(rol: 'ADM' | 'GES' = 'ADM') {
  queryClient = queryClientConYo(rol)
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/admin/configuracion/alicuotas']}>
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

const altas = () => llamadas(apiFetchMock, 'POST', URL_LISTA)
const modificaciones = () => llamadas(apiFetchMock, 'PUT', URL_MODIFICAR)
const operationId = (envio: { init: RequestInit }) => new Headers(envio.init.headers).get('Operation-Id')

describe('pestaña Alícuotas de IVA (tarea 7.3)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
    Object.defineProperty(window.navigator, 'onLine', { value: true, configurable: true })
  })
  afterEach(() => {
    vi.clearAllMocks()
  })

  it('la pestaña está en el menú; lista nombre, porcentaje y estado (activas e inactivas)', async () => {
    servidor()
    montar()

    await screen.findByText('Exento')
    expect(screen.getByRole('link', { name: 'Alícuotas de IVA' })).toHaveAttribute('href', '/admin/configuracion/alicuotas')
    expect(within(filaDe('21%')).getByText('21 %')).toBeInTheDocument()
    expect(within(filaDe('10,5%')).getByText('10,5 %')).toBeInTheDocument()
    expect(within(filaDe('21%')).getByText('Activo')).toBeInTheDocument()
    expect(within(filaDe('Exento')).getByText('De baja')).toBeInTheDocument()
  })

  describe('alta', () => {
    it('crea "27%": el porcentaje 27 viaja como fracción string "0.270000", con Operation-Id, y se invalidan las alícuotas', async () => {
      servidor()
      const usuario = userEvent.setup()
      montar()
      await screen.findByText('21%')

      await usuario.click(screen.getByRole('button', { name: 'Nueva alícuota' }))
      const dialogo = await screen.findByRole('dialog', { name: 'Nueva alícuota' })
      await usuario.type(within(dialogo).getByLabelText('Nombre'), ' 27% ')
      await usuario.type(within(dialogo).getByLabelText('Porcentaje'), '27')
      await usuario.click(within(dialogo).getByRole('button', { name: 'Guardar' }))

      await waitFor(() => expect(within(filaDe('27%')).getByText('27 %')).toBeInTheDocument())
      expect(JSON.parse(String(altas()[0]?.init.body))).toEqual({ nombre: '27%', valor: '0.270000' })
      expect(operationId(altas()[0] as { init: RequestInit })).toBeTruthy()
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
      expect(queryClient.getQueryState(clavesConfiguracion.alicuotas())?.isInvalidated).toBeDefined()
    })

    it('acepta la coma decimal: "10,5" viaja como "0.105000"', async () => {
      servidor()
      const usuario = userEvent.setup()
      montar()
      await screen.findByText('21%')

      await usuario.click(screen.getByRole('button', { name: 'Nueva alícuota' }))
      const dialogo = await screen.findByRole('dialog')
      await usuario.type(within(dialogo).getByLabelText('Nombre'), 'Reducida')
      await usuario.type(within(dialogo).getByLabelText('Porcentaje'), '10,5')
      await usuario.click(within(dialogo).getByRole('button', { name: 'Guardar' }))

      await waitFor(() => expect(altas()).toHaveLength(1))
      expect(JSON.parse(String(altas()[0]?.init.body))).toEqual({ nombre: 'Reducida', valor: '0.105000' })
    })

    it.each(['', '100', '-3', '1,23456', 'abc'])('el porcentaje %j no se envía y avisa', async (porcentaje) => {
      servidor()
      const usuario = userEvent.setup()
      montar()
      await screen.findByText('21%')

      await usuario.click(screen.getByRole('button', { name: 'Nueva alícuota' }))
      const dialogo = await screen.findByRole('dialog')
      await usuario.type(within(dialogo).getByLabelText('Nombre'), 'X')
      if (porcentaje) await usuario.type(within(dialogo).getByLabelText('Porcentaje'), porcentaje)
      await usuario.click(within(dialogo).getByRole('button', { name: 'Guardar' }))

      expect(await within(dialogo).findByText(/ingresá un porcentaje/i)).toBeInTheDocument()
      expect(altas()).toHaveLength(0)
    })

    it('VALOR_DUPLICADO se explica en palabras simples, sin reintentar, y el formulario sigue abierto', async () => {
      servidor({ alRecibir: () => ({ status: 409, cuerpo: { title: 'Valor duplicado.', codigo: 'VALOR_DUPLICADO' } }) })
      const usuario = userEvent.setup()
      montar()
      await screen.findByText('21%')

      await usuario.click(screen.getByRole('button', { name: 'Nueva alícuota' }))
      const dialogo = await screen.findByRole('dialog')
      await usuario.type(within(dialogo).getByLabelText('Nombre'), 'Otra 27')
      await usuario.type(within(dialogo).getByLabelText('Porcentaje'), '27')
      await usuario.click(within(dialogo).getByRole('button', { name: 'Guardar' }))

      expect(await within(dialogo).findByText(/ya hay una alícuota con ese porcentaje/i)).toBeInTheDocument()
      expect(altas()).toHaveLength(1)
      expect(screen.getByRole('dialog')).toBeInTheDocument()
    })

    it('el reintento tras un corte de red reenvía el mismo Operation-Id (INV-06)', async () => {
      let intentos = 0
      servidor({
        alRecibir: () => {
          intentos += 1
          if (intentos <= 3) throw new TypeError('Failed to fetch')
          return { status: 201, cuerpo: alicuota('44444444-4444-4444-8444-444444444444', '27%', '0.270000') }
        },
      })
      const usuario = userEvent.setup()
      montar()
      await screen.findByText('21%')

      await usuario.click(screen.getByRole('button', { name: 'Nueva alícuota' }))
      const dialogo = await screen.findByRole('dialog')
      await usuario.type(within(dialogo).getByLabelText('Nombre'), '27%')
      await usuario.type(within(dialogo).getByLabelText('Porcentaje'), '27')
      await usuario.click(within(dialogo).getByRole('button', { name: 'Guardar' }))
      expect(await within(dialogo).findByText(/se necesita conexión/i)).toBeInTheDocument()
      await usuario.click(within(dialogo).getByRole('button', { name: 'Guardar' }))

      await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
      expect(new Set(altas().map(operationId)).size).toBe(1)
    })
  })

  describe('edición, baja y reactivación', () => {
    it('el porcentaje de una alícuota existente no es editable; renombrar envía el valor guardado sin cambios', async () => {
      servidor()
      const usuario = userEvent.setup()
      montar()
      await screen.findByText('21%')

      await usuario.click(within(filaDe('21%')).getByRole('button', { name: 'Editar 21%' }))
      const dialogo = await screen.findByRole('dialog', { name: 'Editar alícuota' })
      const porcentaje = within(dialogo).getByLabelText('Porcentaje')
      expect(porcentaje).toBeDisabled()
      expect(porcentaje).toHaveValue('21')
      const nombre = within(dialogo).getByLabelText('Nombre')
      await usuario.clear(nombre)
      await usuario.type(nombre, 'IVA general')
      await usuario.click(within(dialogo).getByRole('button', { name: 'Guardar' }))

      await waitFor(() => expect(filaDe('IVA general')).toBeInTheDocument())
      expect(modificaciones()[0]?.url.pathname).toBe(`/configuracion/alicuotas/${IVA21}`)
      expect(JSON.parse(String(modificaciones()[0]?.init.body))).toEqual({
        nombre: 'IVA general',
        valor: '0.210000',
        activo: true,
      })
    })

    it('dar de baja pide confirmación: antes no se envía nada y al confirmar el PUT lleva activo=false', async () => {
      servidor()
      const usuario = userEvent.setup()
      montar()
      await screen.findByText('10,5%')

      await usuario.click(within(filaDe('10,5%')).getByRole('button', { name: 'Dar de baja 10,5%' }))
      const dialogo = await screen.findByRole('dialog', { name: 'Dar de baja 10,5%' })
      expect(modificaciones()).toHaveLength(0)
      await usuario.click(within(dialogo).getByRole('button', { name: 'Confirmar baja' }))

      await waitFor(() => expect(within(filaDe('10,5%')).getByText('De baja')).toBeInTheDocument())
      expect(JSON.parse(String(modificaciones()[0]?.init.body))).toEqual({ nombre: '10,5%', valor: '0.105000', activo: false })
    })

    it('reactivar pide confirmación y envía activo=true', async () => {
      servidor()
      const usuario = userEvent.setup()
      montar()
      await screen.findByText('Exento')

      await usuario.click(within(filaDe('Exento')).getByRole('button', { name: 'Reactivar Exento' }))
      const dialogo = await screen.findByRole('dialog', { name: 'Reactivar Exento' })
      expect(modificaciones()).toHaveLength(0)
      await usuario.click(within(dialogo).getByRole('button', { name: 'Confirmar reactivación' }))

      await waitFor(() => expect(within(filaDe('Exento')).getByText('Activo')).toBeInTheDocument())
      expect(JSON.parse(String(modificaciones()[0]?.init.body))).toMatchObject({ valor: '0.000000', activo: true })
    })

    it('ALICUOTA_EN_USO explica el rechazo con la cantidad de productos y la alícuota sigue activa', async () => {
      servidor({
        alRecibir: () => ({ status: 409, cuerpo: { title: 'En uso.', codigo: 'ALICUOTA_EN_USO', productos: 3 } }),
      })
      const usuario = userEvent.setup()
      montar()
      await screen.findByText('21%')

      await usuario.click(within(filaDe('21%')).getByRole('button', { name: 'Dar de baja 21%' }))
      const dialogo = await screen.findByRole('dialog')
      await usuario.click(within(dialogo).getByRole('button', { name: 'Confirmar baja' }))

      expect(await within(dialogo).findByText(/la usan 3 productos activos/i)).toBeInTheDocument()
      await usuario.click(within(dialogo).getByRole('button', { name: 'Cancelar' }))
      expect(within(filaDe('21%')).getByText('Activo')).toBeInTheDocument()
    })

    it('ULTIMA_ALICUOTA_ACTIVA explica que tiene que quedar una activa', async () => {
      servidor({
        alRecibir: () => ({ status: 409, cuerpo: { title: 'Última.', codigo: 'ULTIMA_ALICUOTA_ACTIVA' } }),
      })
      const usuario = userEvent.setup()
      montar()
      await screen.findByText('21%')

      await usuario.click(within(filaDe('21%')).getByRole('button', { name: 'Dar de baja 21%' }))
      const dialogo = await screen.findByRole('dialog')
      await usuario.click(within(dialogo).getByRole('button', { name: 'Confirmar baja' }))

      expect(await within(dialogo).findByText(/al menos una alícuota activa/i)).toBeInTheDocument()
    })
  })

  describe('ayuda contextual (tarea 9.1; textos aprobados el 2026-10-30)', () => {
    it('"Porcentaje" y "Dar de baja" traen su "(?)" con el texto aprobado', async () => {
      servidor()
      const usuario = userEvent.setup()
      montar()
      await screen.findByText('21%')

      await usuario.click(screen.getAllByRole('button', { name: `Ayuda: ${AYUDAS['alicuotas.baja'].titulo}` })[0] as HTMLElement)
      expect(await screen.findByText(AYUDAS['alicuotas.baja'].texto)).toBeInTheDocument()

      await usuario.click(screen.getByRole('button', { name: 'Nueva alícuota' }))
      const dialogo = await screen.findByRole('dialog')
      await usuario.click(within(dialogo).getByRole('button', { name: `Ayuda: ${AYUDAS['alicuotas.valor'].titulo}` }))
      expect(await screen.findByText(AYUDAS['alicuotas.valor'].texto)).toBeInTheDocument()
    })
  })

  describe('sin permiso (ADR-027)', () => {
    it('sin ADMIN_CONFIGURACION no se ofrece la pestaña, la pantalla avisa y no pide nada', async () => {
      servidor()
      montar('GES')

      expect(await screen.findByText(/no tenés permiso/i)).toBeInTheDocument()
      expect(screen.queryByRole('link', { name: 'Alícuotas de IVA' })).not.toBeInTheDocument()
      expect(screen.queryByRole('button', { name: 'Nueva alícuota' })).not.toBeInTheDocument()
      expect(llamadas(apiFetchMock, 'GET', URL_LISTA)).toHaveLength(0)
    })
  })
})
