/**
 * Change 16, tarea 15.3: detalle de una regla de descuento, activar, pausar y poner fin (spec
 * `administracion-de-descuentos`, requisito "Activar y pausar se confirman desde la pantalla";
 * `01` §18; `design.md` D15, D16; INV-06, SEG-06).
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
import { queryClientConYo, type RolDePrueba } from '../../../utils/permisosDePrueba'
import { REGLA_ID, regla, reglaDeMarca } from './descuentosDePrueba'

function montar(rol: RolDePrueba = 'ADM', permisos?: string[]) {
  const cliente = permisos ? queryClientConYo(rol, { permisos } as never) : queryClientConYo(rol)
  return render(
    <QueryClientProvider client={cliente}>
      <MemoryRouter initialEntries={[`/admin/descuentos/${REGLA_ID}`]}>
        <Routes>
          <Route path="/admin/descuentos/*" element={<DescuentosArea />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

/** Una regla que cambia de estado según los POST que recibe, como el servidor. */
function servidorConRegla(inicial: Record<string, unknown>, extra: ReglaDeApi[] = []) {
  let actual = inicial
  enrutar(apiFetchMock, [
    ...extra,
    { metodo: 'GET', ruta: `/descuentos/reglas/${REGLA_ID}`, responder: () => ({ status: 200, cuerpo: actual }) },
    {
      metodo: 'POST',
      ruta: `/descuentos/reglas/${REGLA_ID}/activacion`,
      responder: () => {
        actual = { ...actual, estado: 'ACTIVA', vigencia_desde: '2026-10-14T15:00:00Z' }
        return { status: 200, cuerpo: actual }
      },
    },
    {
      metodo: 'POST',
      ruta: `/descuentos/reglas/${REGLA_ID}/pausa`,
      responder: () => {
        actual = { ...actual, estado: 'PAUSADA' }
        return { status: 200, cuerpo: actual }
      },
    },
    {
      metodo: 'PUT',
      ruta: `/descuentos/reglas/${REGLA_ID}`,
      responder: (_url, init) => {
        actual = { ...actual, ...JSON.parse(String(init?.body)) }
        return { status: 200, cuerpo: actual }
      },
    },
  ])
}

describe('detalle de una regla de descuento (tarea 15.3)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
    Object.defineProperty(window.navigator, 'onLine', { value: true, configurable: true })
  })
  afterEach(() => {
    vi.clearAllMocks()
  })

  it('muestra la regla completa: descripción, alcance, prioridad, acumulable, vigencia y estado', async () => {
    servidorConRegla(reglaDeMarca({ id: REGLA_ID, vigencia_hasta: '2026-12-31T23:00:00Z' }))
    montar()

    expect(await screen.findByRole('heading', { name: 'Coca-Cola importe fijo' })).toBeInTheDocument()
    expect(screen.getByText('Importe bruto ≥ $ 100.000,00 → $ 5.000,00 fijos')).toBeInTheDocument()
    expect(screen.getByText('Sobre Marca Coca-Cola')).toBeInTheDocument()
    expect(screen.getByText('Prioridad 2')).toBeInTheDocument()
    expect(screen.getByText('Acumulable')).toBeInTheDocument()
    expect(screen.getByText(/^Hasta \d{2}\/\d{2}\/\d{4}/)).toBeInTheDocument()
    expect(screen.getByText('Activa', { selector: 'span' })).toBeInTheDocument()
  })

  it('un borrador ofrece "Editar" y "Activar", y no "Pausar" ni "Poner fin"', async () => {
    servidorConRegla(regla())
    montar()

    expect(await screen.findByRole('link', { name: 'Editar' })).toHaveAttribute('href', `/admin/descuentos/${REGLA_ID}/editar`)
    expect(screen.getByRole('button', { name: 'Activar' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Pausar' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Poner fin' })).not.toBeInTheDocument()
  })

  it('Escenario activar con confirmación: avisa que ya no se podrá editar, activa y deja de ofrecer "Editar"', async () => {
    servidorConRegla(regla())
    const usuario = userEvent.setup()
    montar()
    await usuario.click(await screen.findByRole('button', { name: 'Activar' }))

    const dialogo = await screen.findByRole('dialog', { name: /activar regla/i })
    expect(within(dialogo).getByText(/ya no se podrá editar/i)).toBeInTheDocument()
    expect(llamadas(apiFetchMock, 'POST', /activacion$/)).toHaveLength(0)
    await usuario.click(within(dialogo).getByRole('button', { name: /confirmar activación/i }))

    await waitFor(() => expect(screen.getByText('Activa', { selector: 'span' })).toBeInTheDocument())
    expect(screen.queryByRole('link', { name: 'Editar' })).not.toBeInTheDocument()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    const envios = llamadas(apiFetchMock, 'POST', `/descuentos/reglas/${REGLA_ID}/activacion`)
    expect(envios).toHaveLength(1)
    expect(new Headers(envios[0]?.init.headers).get('Operation-Id')).toBeTruthy()
    expect(envios[0]?.init.body).toBeUndefined()
  })

  it('cancelar la confirmación no envía nada', async () => {
    servidorConRegla(regla())
    const usuario = userEvent.setup()
    montar()
    await usuario.click(await screen.findByRole('button', { name: 'Activar' }))

    await usuario.click(within(await screen.findByRole('dialog')).getByRole('button', { name: /cancelar/i }))

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(llamadas(apiFetchMock, 'POST', /activacion$/)).toHaveLength(0)
  })

  it('Escenario pausar una regla activa: pasa a "Pausada" y ofrece "Activar"', async () => {
    servidorConRegla(regla({ estado: 'ACTIVA', vigencia_desde: '2026-10-14T15:00:00Z' }))
    const usuario = userEvent.setup()
    montar()
    await usuario.click(await screen.findByRole('button', { name: 'Pausar' }))

    await usuario.click(within(await screen.findByRole('dialog', { name: /pausar regla/i })).getByRole('button', { name: /confirmar pausa/i }))

    await waitFor(() => expect(screen.getByText('Pausada', { selector: 'span' })).toBeInTheDocument())
    expect(screen.getByRole('button', { name: 'Activar' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Pausar' })).not.toBeInTheDocument()
  })

  it.each(['ACTIVA', 'PAUSADA'])(
    'Escenario regla activada de solo lectura: en %s no se edita, solo se puede "Poner fin"',
    async (estado) => {
      servidorConRegla(regla({ estado, vigencia_desde: '2026-10-14T15:00:00Z' }))
      montar()

      expect(await screen.findByRole('button', { name: 'Poner fin' })).toBeInTheDocument()
      expect(screen.queryByRole('link', { name: 'Editar' })).not.toBeInTheDocument()
      expect(screen.getByText(/ya no se edita/i)).toBeInTheDocument()
    },
  )

  it('"Poner fin" fija la vigencia hasta con un PUT que solo lleva ese campo', async () => {
    servidorConRegla(regla({ estado: 'ACTIVA', vigencia_desde: '2026-10-14T15:00:00Z' }))
    const usuario = userEvent.setup()
    montar()
    await usuario.click(await screen.findByRole('button', { name: 'Poner fin' }))
    const dialogo = await screen.findByRole('dialog', { name: /poner fin/i })

    await usuario.type(within(dialogo).getByLabelText(/vigencia hasta/i), '2027-01-31T18:00')
    await usuario.click(within(dialogo).getByRole('button', { name: /confirmar fin/i }))

    await waitFor(() => expect(llamadas(apiFetchMock, 'PUT', `/descuentos/reglas/${REGLA_ID}`)).toHaveLength(1))
    const envio = llamadas(apiFetchMock, 'PUT', `/descuentos/reglas/${REGLA_ID}`)[0]
    expect(JSON.parse(String(envio?.init.body))).toEqual({ vigencia_hasta: new Date('2027-01-31T18:00').toISOString() })
    expect(new Headers(envio?.init.headers).get('Operation-Id')).toBeTruthy()
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    expect(await screen.findByText(/^Desde .* hasta /)).toBeInTheDocument()
  })

  it('"Poner fin" sin fecha, o anterior a la vigencia desde, se señala junto al campo y no envía', async () => {
    servidorConRegla(regla({ estado: 'ACTIVA', vigencia_desde: '2026-10-14T15:00:00Z' }))
    const usuario = userEvent.setup()
    montar()
    await usuario.click(await screen.findByRole('button', { name: 'Poner fin' }))
    const dialogo = await screen.findByRole('dialog')

    await usuario.click(within(dialogo).getByRole('button', { name: /confirmar fin/i }))
    expect(await within(dialogo).findByText(/ingresá una fecha y hora válidas/i)).toBeInTheDocument()
    await usuario.type(within(dialogo).getByLabelText(/vigencia hasta/i), '2026-01-01T10:00')
    await usuario.click(within(dialogo).getByRole('button', { name: /confirmar fin/i }))
    expect(await within(dialogo).findByText(/posterior a la vigencia desde/i)).toBeInTheDocument()
    expect(llamadas(apiFetchMock, 'PUT', `/descuentos/reglas/${REGLA_ID}`)).toHaveLength(0)
  })

  it('"Poner fin": VIGENCIA_INVALIDA del servidor se muestra junto a la fecha y el diálogo sigue abierto', async () => {
    servidorConRegla(regla({ estado: 'ACTIVA', vigencia_desde: '2026-10-14T15:00:00Z' }), [
      {
        metodo: 'PUT',
        ruta: `/descuentos/reglas/${REGLA_ID}`,
        responder: () => ({ status: 422, cuerpo: { title: 'La vigencia hasta ya pasó.', codigo: 'VIGENCIA_INVALIDA' } }),
      },
    ])
    const usuario = userEvent.setup()
    montar()
    await usuario.click(await screen.findByRole('button', { name: 'Poner fin' }))
    const dialogo = await screen.findByRole('dialog')

    await usuario.type(within(dialogo).getByLabelText(/vigencia hasta/i), '2027-01-31T18:00')
    await usuario.click(within(dialogo).getByRole('button', { name: /confirmar fin/i }))

    expect(await within(dialogo).findByText('La vigencia hasta ya pasó.')).toBeInTheDocument()
    expect(screen.getByRole('dialog')).toBeInTheDocument()
  })

  it('Escenario estado cambiado por otra persona: REGLA_ESTADO_INVALIDO muestra el mensaje y refresca el estado actual', async () => {
    let estado = 'ACTIVA'
    enrutar(apiFetchMock, [
      {
        metodo: 'GET',
        ruta: `/descuentos/reglas/${REGLA_ID}`,
        responder: () => ({ status: 200, cuerpo: regla({ estado, vigencia_desde: '2026-10-14T15:00:00Z' }) }),
      },
      {
        metodo: 'POST',
        ruta: `/descuentos/reglas/${REGLA_ID}/pausa`,
        responder: () => {
          estado = 'PAUSADA' // otra persona la pausó antes
          return { status: 409, cuerpo: { title: 'Una regla PAUSADA no se puede pausar', codigo: 'REGLA_ESTADO_INVALIDO' } }
        },
      },
    ])
    const usuario = userEvent.setup()
    montar()
    await usuario.click(await screen.findByRole('button', { name: 'Pausar' }))

    await usuario.click(within(await screen.findByRole('dialog')).getByRole('button', { name: /confirmar pausa/i }))

    expect(await screen.findByText(/cambió de estado mientras mirabas la pantalla/i)).toBeInTheDocument()
    await waitFor(() => expect(screen.getByText('Pausada', { selector: 'span' })).toBeInTheDocument())
    expect(screen.getByRole('button', { name: 'Activar' })).toBeInTheDocument()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('reintentar el mismo cambio tras perder la respuesta reenvía el mismo operation_id', async () => {
    let pausas = 0
    apiFetchMock.mockImplementation((ruta: string, init?: RequestInit) => {
      const metodo = init?.method ?? 'GET'
      if (metodo === 'POST' && ruta.endsWith('/pausa')) {
        pausas += 1
        if (pausas <= 3) return Promise.reject(new TypeError('Failed to fetch'))
        return Promise.resolve({ ok: true, status: 200, json: async () => regla({ estado: 'PAUSADA' }) })
      }
      return Promise.resolve({ ok: true, status: 200, json: async () => regla({ estado: 'ACTIVA', vigencia_desde: '2026-10-14T15:00:00Z' }) })
    })
    const usuario = userEvent.setup()
    montar()
    await usuario.click(await screen.findByRole('button', { name: 'Pausar' }))
    const dialogo = await screen.findByRole('dialog')

    await usuario.click(within(dialogo).getByRole('button', { name: /confirmar pausa/i }))
    expect(await within(dialogo).findByText(/se necesita conexión/i)).toBeInTheDocument()
    await usuario.click(within(dialogo).getByRole('button', { name: /confirmar pausa/i }))

    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    const ids = llamadas(apiFetchMock, 'POST', /pausa$/).map((e) => new Headers(e.init.headers).get('Operation-Id'))
    expect(ids).toHaveLength(4)
    expect(new Set(ids).size).toBe(1)
  })

  it('sin conexión no envía la activación y lo avisa', async () => {
    Object.defineProperty(window.navigator, 'onLine', { value: false, configurable: true })
    servidorConRegla(regla())
    const usuario = userEvent.setup()
    montar()
    await usuario.click(await screen.findByRole('button', { name: 'Activar' }))

    await usuario.click(within(await screen.findByRole('dialog')).getByRole('button', { name: /confirmar activación/i }))

    expect(await screen.findByText(/se necesita conexión para completar esta operación/i)).toBeInTheDocument()
    expect(llamadas(apiFetchMock, 'POST', /activacion$/)).toHaveLength(0)
  })

  it('una regla inexistente (404) se informa', async () => {
    enrutar(apiFetchMock, [
      { metodo: 'GET', ruta: `/descuentos/reglas/${REGLA_ID}`, responder: () => ({ status: 404, cuerpo: { title: 'No existe', codigo: 'RECURSO_NO_ENCONTRADO' } }) },
    ])
    montar()

    expect(await screen.findByText(/no se encontró la regla/i)).toBeInTheDocument()
  })
})
