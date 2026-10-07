import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }))
vi.mock('../../../../../src/lib/api/httpClient', () => ({ apiFetch: apiFetchMock }))

import { ListaDetalleScreen } from '../../../../../src/areas/admin/precios/ListaDetalleScreen'
import { llamadas } from '../../../utils/enrutarApi'
import { queryClientConYo } from '../../../utils/permisosDePrueba'
import {
  CATEGORIA_CERVEZAS_ID,
  CATEGORIA_VINOS_ID,
  LISTA_ID,
  REGLA_ID,
  VERSION_HISTORICA,
  VERSION_PROGRAMADA_ID,
  VERSION_VIGENTE_ID,
  montarApi,
  regla,
  reglasDeDetalle,
} from './preciosDePrueba'

function renderDetalle(permisos?: string[]) {
  const cliente = permisos ? queryClientConYo('GES', { permisos } as never) : queryClientConYo('GES')
  return render(
    <QueryClientProvider client={cliente}>
      <MemoryRouter initialEntries={[`/admin/precios/${LISTA_ID}`]}>
        <Routes>
          <Route path="/admin/precios/:listaId" element={<ListaDetalleScreen />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

function filaDeRegla(texto: string): HTMLElement {
  const reglas = within(screen.getByRole('table', { name: /reglas de margen/i }))
  return reglas.getByText(texto).closest('tr') as HTMLElement
}

describe('ListaDetalleScreen: reglas (tarea 13.1; PRC-12, PRC-13, D8)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
    montarApi(apiFetchMock, reglasDeDetalle())
  })
  afterEach(() => {
    vi.clearAllMocks()
  })

  it('muestra cada regla con su alcance, su tipo, su valor y la fórmula que aplica', async () => {
    renderDetalle()

    const reglas = within(await screen.findByRole('table', { name: /reglas de margen/i }))
    const categoria = reglas.getByText('Vinos').closest('tr') as HTMLElement
    expect(within(categoria).getByText('Categoría')).toBeInTheDocument()
    expect(within(categoria).getByText('Markup')).toBeInTheDocument()
    expect(within(categoria).getByText('30%')).toBeInTheDocument()
    expect(within(categoria).getByText('Precio = costo × 1,30')).toBeInTheDocument()

    const deLista = reglas.getByText('Toda la lista').closest('tr') as HTMLElement
    expect(within(deLista).getByText('Margen bruto')).toBeInTheDocument()
    expect(within(deLista).getByText('Precio = costo ÷ 0,70')).toBeInTheDocument()
  })

  it('muestra el redondeo de la lista y el de cada categoría', async () => {
    renderDetalle()

    expect(await screen.findByText(/100,00 · hacia arriba/i)).toBeInTheDocument()
    const redondeos = within(screen.getByRole('table', { name: /redondeo por categoría/i }))
    const vinos = redondeos.getByText('Vinos').closest('tr') as HTMLElement
    expect(within(vinos).getByText('50,00 · Al más cercano')).toBeInTheDocument()
  })

  it('crea una regla de categoría: un POST con Operation-Id y el valor como fracción string', async () => {
    montarApi(apiFetchMock, [
      ...reglasDeDetalle(),
      { metodo: 'POST', ruta: `/precios/listas/${LISTA_ID}/reglas`, responder: () => ({ status: 201, cuerpo: regla() }) },
    ])
    const usuario = userEvent.setup()
    renderDetalle()

    await usuario.click(await screen.findByRole('button', { name: /nueva regla/i }))
    const dialogo = within(screen.getByRole('dialog'))
    await usuario.selectOptions(dialogo.getByLabelText(/tipo de margen/i), 'MARKUP')
    await usuario.type(dialogo.getByLabelText(/porcentaje/i), '12,5')
    await usuario.selectOptions(dialogo.getByLabelText(/se aplica a/i), 'CATEGORIA')
    await usuario.selectOptions(await dialogo.findByLabelText(/^entidad$/i), CATEGORIA_CERVEZAS_ID)
    expect(dialogo.getByText('Precio = costo × 1,125')).toBeInTheDocument()
    await usuario.click(dialogo.getByRole('button', { name: /guardar regla/i }))

    const envios = await vi.waitFor(() => {
      const hechos = llamadas(apiFetchMock, 'POST', `/precios/listas/${LISTA_ID}/reglas`)
      expect(hechos).toHaveLength(1)
      return hechos
    })
    expect(new Headers(envios[0]?.init.headers).get('Operation-Id')).toBeTruthy()
    expect(JSON.parse(String(envios[0]?.init.body))).toEqual({
      tipo: 'MARKUP',
      valor: '0.125000',
      alcance_tipo: 'CATEGORIA',
      alcance_id: CATEGORIA_CERVEZAS_ID,
    })
  })

  it('un margen bruto de 100% se marca como inválido y no envía el comando (TR-10)', async () => {
    const usuario = userEvent.setup()
    renderDetalle()

    await usuario.click(await screen.findByRole('button', { name: /nueva regla/i }))
    const dialogo = within(screen.getByRole('dialog'))
    await usuario.selectOptions(dialogo.getByLabelText(/tipo de margen/i), 'MARGEN_BRUTO')
    await usuario.type(dialogo.getByLabelText(/porcentaje/i), '100')
    await usuario.selectOptions(dialogo.getByLabelText(/se aplica a/i), 'LISTA')
    await usuario.click(dialogo.getByRole('button', { name: /guardar regla/i }))

    expect(await dialogo.findByText(/un margen bruto debe ser menor que 100%/i)).toBeInTheDocument()
    expect(llamadas(apiFetchMock, 'POST', `/precios/listas/${LISTA_ID}/reglas`)).toHaveLength(0)
  })

  it('REGLA_DUPLICADA se muestra junto al alcance y conserva lo cargado', async () => {
    montarApi(apiFetchMock, [
      ...reglasDeDetalle(),
      {
        metodo: 'POST',
        ruta: `/precios/listas/${LISTA_ID}/reglas`,
        responder: () => ({
          status: 409,
          cuerpo: { title: 'Ya hay una regla activa para esa categoría.', codigo: 'REGLA_DUPLICADA' },
        }),
      },
    ])
    const usuario = userEvent.setup()
    renderDetalle()

    await usuario.click(await screen.findByRole('button', { name: /nueva regla/i }))
    const dialogo = within(screen.getByRole('dialog'))
    await usuario.type(dialogo.getByLabelText(/porcentaje/i), '40')
    await usuario.selectOptions(dialogo.getByLabelText(/se aplica a/i), 'CATEGORIA')
    await usuario.selectOptions(await dialogo.findByLabelText(/^entidad$/i), CATEGORIA_VINOS_ID)
    await usuario.click(dialogo.getByRole('button', { name: /guardar regla/i }))

    expect(await dialogo.findByText('Ya hay una regla activa para esa categoría.')).toBeInTheDocument()
    expect(dialogo.getByLabelText(/porcentaje/i)).toHaveValue('40')
    expect(dialogo.getByLabelText(/^entidad$/i)).toHaveValue(CATEGORIA_VINOS_ID)
  })

  it('edita una regla: PUT con tipo, valor y actividad, sin tocar el alcance', async () => {
    montarApi(apiFetchMock, [
      ...reglasDeDetalle(),
      { metodo: 'PUT', ruta: `/precios/listas/${LISTA_ID}/reglas/${REGLA_ID}`, responder: () => ({ status: 200, cuerpo: regla() }) },
    ])
    const usuario = userEvent.setup()
    renderDetalle()

    await screen.findByRole('table', { name: /reglas de margen/i })
    await usuario.click(within(filaDeRegla('Vinos')).getByRole('button', { name: /editar/i }))
    const dialogo = within(screen.getByRole('dialog'))
    expect(dialogo.getByLabelText(/porcentaje/i)).toHaveValue('30')
    await usuario.selectOptions(dialogo.getByLabelText(/tipo de margen/i), 'MARGEN_BRUTO')
    await usuario.clear(dialogo.getByLabelText(/porcentaje/i))
    await usuario.type(dialogo.getByLabelText(/porcentaje/i), '25')
    await usuario.click(dialogo.getByRole('button', { name: /guardar regla/i }))

    const envios = await vi.waitFor(() => {
      const hechos = llamadas(apiFetchMock, 'PUT', `/precios/listas/${LISTA_ID}/reglas/${REGLA_ID}`)
      expect(hechos).toHaveLength(1)
      return hechos
    })
    expect(JSON.parse(String(envios[0]?.init.body))).toEqual({ tipo: 'MARGEN_BRUTO', valor: '0.250000', activo: true })
  })

  it('desactiva una regla con un PUT que solo cambia la actividad', async () => {
    montarApi(apiFetchMock, [
      ...reglasDeDetalle(),
      { metodo: 'PUT', ruta: `/precios/listas/${LISTA_ID}/reglas/${REGLA_ID}`, responder: () => ({ status: 200, cuerpo: regla({ activo: false }) }) },
    ])
    const usuario = userEvent.setup()
    renderDetalle()

    await screen.findByRole('table', { name: /reglas de margen/i })
    await usuario.click(within(filaDeRegla('Vinos')).getByRole('button', { name: /desactivar/i }))

    const envios = await vi.waitFor(() => {
      const hechos = llamadas(apiFetchMock, 'PUT', `/precios/listas/${LISTA_ID}/reglas/${REGLA_ID}`)
      expect(hechos).toHaveLength(1)
      return hechos
    })
    expect(JSON.parse(String(envios[0]?.init.body))).toEqual({ tipo: 'MARKUP', valor: '0.300000', activo: false })
  })

  it('con solo PUBLICAR_LISTAS ve las reglas sin ninguna acción de edición', async () => {
    renderDetalle(['PUBLICAR_LISTAS'])

    await screen.findByRole('table', { name: /reglas de margen/i })
    expect(screen.queryByRole('button', { name: /nueva regla/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /editar|desactivar/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /editar lista/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /guardar redondeo/i })).not.toBeInTheDocument()
  })
})

describe('ListaDetalleScreen: redondeos por categoría (tarea 13.1; PRC-14)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
  })
  afterEach(() => {
    vi.clearAllMocks()
  })

  it('define el redondeo de una categoría con PUT: múltiplo como string y dirección', async () => {
    montarApi(apiFetchMock, [
      ...reglasDeDetalle(),
      {
        metodo: 'PUT',
        ruta: `/precios/listas/${LISTA_ID}/redondeos-categoria/${CATEGORIA_CERVEZAS_ID}`,
        responder: () => ({ status: 200, cuerpo: {} }),
      },
    ])
    const usuario = userEvent.setup()
    renderDetalle()

    await screen.findByRole('option', { name: 'Cervezas' })
    await usuario.selectOptions(screen.getByLabelText(/categoría del redondeo/i), CATEGORIA_CERVEZAS_ID)
    await usuario.type(screen.getByLabelText(/múltiplo del redondeo/i), '10,5')
    await usuario.selectOptions(screen.getByLabelText(/dirección del redondeo de la categoría/i), 'ABAJO')
    await usuario.click(screen.getByRole('button', { name: /guardar redondeo/i }))

    const envios = await vi.waitFor(() => {
      const hechos = llamadas(apiFetchMock, 'PUT', `/precios/listas/${LISTA_ID}/redondeos-categoria/${CATEGORIA_CERVEZAS_ID}`)
      expect(hechos).toHaveLength(1)
      return hechos
    })
    expect(JSON.parse(String(envios[0]?.init.body))).toEqual({ multiplo: '10.5', direccion: 'ABAJO', activo: true })
  })

  it('un múltiplo inválido se marca y no envía nada', async () => {
    montarApi(apiFetchMock, reglasDeDetalle())
    const usuario = userEvent.setup()
    renderDetalle()

    await screen.findByRole('option', { name: 'Cervezas' })
    await usuario.selectOptions(screen.getByLabelText(/categoría del redondeo/i), CATEGORIA_CERVEZAS_ID)
    await usuario.type(screen.getByLabelText(/múltiplo del redondeo/i), '0')
    await usuario.click(screen.getByRole('button', { name: /guardar redondeo/i }))

    expect(await screen.findByText(/múltiplo mayor que cero/i)).toBeInTheDocument()
    expect(llamadas(apiFetchMock, 'PUT', /redondeos-categoria/)).toHaveLength(0)
  })
})

describe('ListaDetalleScreen: versiones (tarea 13.3; PRC-03)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
    montarApi(apiFetchMock, reglasDeDetalle())
  })
  afterEach(() => {
    vi.clearAllMocks()
  })

  it('lista las versiones con su estado derivado y enlaza cada una a su pantalla', async () => {
    renderDetalle()

    const versiones = within(await screen.findByRole('table', { name: /versiones/i }))
    expect(within(versiones.getByText('Borrador').closest('tr') as HTMLElement).getByRole('link')).toHaveAttribute(
      'href',
      `/admin/precios/${LISTA_ID}/borrador`,
    )
    expect(within(versiones.getByText('Programada').closest('tr') as HTMLElement).getByRole('link')).toHaveAttribute(
      'href',
      `/admin/precios/${LISTA_ID}/versiones/${VERSION_PROGRAMADA_ID}`,
    )
    expect(within(versiones.getByText('Vigente').closest('tr') as HTMLElement).getByRole('link')).toHaveAttribute(
      'href',
      `/admin/precios/${LISTA_ID}/versiones/${VERSION_VIGENTE_ID}`,
    )
    expect(within(versiones.getByText('Histórica').closest('tr') as HTMLElement).getByRole('link')).toHaveAttribute(
      'href',
      `/admin/precios/${LISTA_ID}/versiones/${VERSION_HISTORICA.id}`,
    )
  })
})
