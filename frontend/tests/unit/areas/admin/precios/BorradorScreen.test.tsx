import { QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }))
vi.mock('../../../../../src/lib/api/httpClient', () => ({ apiFetch: apiFetchMock }))

import { BorradorScreen } from '../../../../../src/areas/admin/precios/BorradorScreen'
import { llamadas, type ReglaDeApi } from '../../../utils/enrutarApi'
import { queryClientConYo } from '../../../utils/permisosDePrueba'
import {
  CERVEZA_B_ID,
  GASEOSA_C_ID,
  LISTA_ID,
  PRECIO_MANUAL_CON_SENAL,
  VERSION_BORRADOR,
  VERSION_BORRADOR_ID,
  VINO_A_ID,
  borrador,
  borradorSinCostos,
  montarApi,
  precio,
  reglasDeBorrador,
} from './preciosDePrueba'

const PERMISOS_SIN_COSTOS = ['GESTIONAR_LISTAS', 'PUBLICAR_LISTAS']

function renderBorrador(rol: 'ADM' | 'GES' = 'GES', permisos?: string[]) {
  const cliente = permisos ? queryClientConYo(rol, { permisos } as never) : queryClientConYo(rol)
  return render(
    <QueryClientProvider client={cliente}>
      <MemoryRouter initialEntries={[`/admin/precios/${LISTA_ID}/borrador`]}>
        <Routes>
          <Route path="/admin/precios/:listaId/borrador" element={<BorradorScreen />} />
          <Route path="/admin/precios/:listaId" element={<p>Detalle de la lista</p>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

function filaDe(producto: string): HTMLElement {
  const tabla = within(screen.getByRole('table', { name: /precios del borrador/i }))
  return tabla.getByText(producto).closest('tr') as HTMLElement
}

const GENERACION = {
  version_id: VERSION_BORRADOR_ID,
  numero: 4,
  regenerado: true,
  cantidad_precios: 2,
  productos_sin_precio: [{ producto_id: GASEOSA_C_ID, producto_nombre: 'Gaseosa C', causa: 'SIN_COSTO' }],
  precios_con_otra_regla_iva: 1,
  precios_con_costos_distintos: 0,
}

describe('BorradorScreen: lectura (tarea 13.2; PRC-17, PRC-22)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
    montarApi(apiFetchMock, reglasDeBorrador())
  })
  afterEach(() => {
    vi.clearAllMocks()
  })

  it('compara con la versión base: precio anterior → nuevo, que cambia, y la botella con PRC-22', async () => {
    renderBorrador()

    await screen.findByRole('table', { name: /precios del borrador/i })
    const vino = filaDe('Vino A')
    const celdas = within(vino).getAllByRole('cell')
    expect(celdas[1]).toHaveTextContent('$ 8.600,00')
    expect(celdas[2]).toHaveTextContent('$ 9.500,00')
    expect(within(vino).getByText('Cambia')).toBeInTheDocument()
    expect(await within(vino).findByText(/botella.*1\.583,33/i)).toBeInTheDocument()
    expect(within(vino).getByText(/caja x6.*9\.500,00/i)).toBeInTheDocument()
    expect(within(vino).queryByText(/pallet/i)).not.toBeInTheDocument()
  })

  it('el precio por presentación sale de las presentaciones de la línea y no pide el detalle de ningún producto', async () => {
    renderBorrador()

    await screen.findByRole('table', { name: /precios del borrador/i })
    const cerveza = filaDe('Cerveza B')
    expect(await within(cerveza).findByText(/lata.*2\.583,33/i)).toBeInTheDocument()
    expect(within(cerveza).getByText(/caja x12.*31\.000,00/i)).toBeInTheDocument()
    expect(llamadas(apiFetchMock, 'GET', /^\/catalogo\/productos\/[^/]+$/)).toEqual([])
  })

  it('un precio manual con margen menor lo dice y lo marca como manual', async () => {
    renderBorrador()

    await screen.findByRole('table', { name: /precios del borrador/i })
    const cerveza = filaDe('Cerveza B')
    expect(within(cerveza).getByText('Manual')).toBeInTheDocument()
    expect(within(cerveza).getByText('Margen menor que el de la regla')).toBeInTheDocument()
    expect(within(cerveza).getByRole('button', { name: /quitar precio manual/i })).toBeInTheDocument()
    expect(within(filaDe('Vino A')).queryByText('Manual')).not.toBeInTheDocument()
  })

  it('lista aparte los productos sin precio con su causa y ofrece fijarles uno', async () => {
    renderBorrador()

    const sinPrecio = within(await screen.findByRole('table', { name: /productos sin precio/i }))
    const gaseosa = sinPrecio.getByText('Gaseosa C').closest('tr') as HTMLElement
    expect(within(gaseosa).getByText('Sin costo informado vigente')).toBeInTheDocument()
    expect(within(gaseosa).getByRole('button', { name: /fijar precio/i })).toBeInTheDocument()
  })

  it('un producto sin presentación de referencia dice su causa y no ofrece precio manual', async () => {
    montarApi(apiFetchMock, [
      ...reglasDeBorrador(
        borrador({
          productos_sin_precio: [
            { producto_id: GASEOSA_C_ID, producto_nombre: 'Gaseosa C', causa: 'SIN_PRESENTACION_DE_REFERENCIA' },
          ],
        }),
      ),
    ])
    renderBorrador()

    const sinPrecio = within(await screen.findByRole('table', { name: /productos sin precio/i }))
    const gaseosa = sinPrecio.getByText('Gaseosa C').closest('tr') as HTMLElement
    expect(within(gaseosa).getByText(/sin presentación de referencia/i)).toBeInTheDocument()
    expect(within(gaseosa).queryByRole('button', { name: /fijar precio/i })).not.toBeInTheDocument()
    expect(within(gaseosa).getByText(/asignale una presentación de referencia en el catálogo/i)).toBeInTheDocument()
  })

  it('con VER_COSTOS muestra costo de referencia, regla y precio calculado', async () => {
    renderBorrador('GES')

    const tabla = within(await screen.findByRole('table', { name: /precios del borrador/i }))
    expect(tabla.getByRole('columnheader', { name: /costo de referencia/i })).toBeInTheDocument()
    expect(tabla.getByRole('columnheader', { name: /regla/i })).toBeInTheDocument()
    expect(tabla.getByRole('columnheader', { name: /precio calculado/i })).toBeInTheDocument()
    const vino = filaDe('Vino A')
    expect(within(vino).getByText(/6\.600,00/)).toBeInTheDocument()
    expect(within(vino).getByText('Markup 30%')).toBeInTheDocument()
    expect(within(vino).getByText(/8\.580,00/)).toBeInTheDocument()
  })

  it('sin VER_COSTOS no muestra columnas de costo, margen ni precio calculado, pero sí precios y señales', async () => {
    montarApi(apiFetchMock, reglasDeBorrador(borradorSinCostos()))
    renderBorrador('GES', PERMISOS_SIN_COSTOS)

    const tabla = within(await screen.findByRole('table', { name: /precios del borrador/i }))
    expect(tabla.queryByRole('columnheader', { name: /costo de referencia|regla|precio calculado/i })).not.toBeInTheDocument()
    expect(within(filaDe('Vino A')).getAllByRole('cell')[2]).toHaveTextContent('$ 9.500,00')
    expect(within(filaDe('Cerveza B')).getByText('Margen menor que el de la regla')).toBeInTheDocument()
  })

  it('indica cuándo se generó el borrador y que publicar no recalcula', async () => {
    renderBorrador()

    expect(await screen.findByText(/generado el 05\/10\/2026/i)).toBeInTheDocument()
    expect(screen.getByText(/publicar no recalcula/i)).toBeInTheDocument()
  })

  it('con GESTIONAR_LISTAS y sin PUBLICAR_LISTAS ve "Regenerar" y la edición de precios, no "Publicar"', async () => {
    renderBorrador('GES')

    await screen.findByRole('table', { name: /precios del borrador/i })
    expect(screen.getByRole('button', { name: /regenerar/i })).toBeInTheDocument()
    expect(within(filaDe('Vino A')).getByRole('button', { name: /fijar precio/i })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /^publicar$/i })).not.toBeInTheDocument()
  })

  it('un Administrador con los dos permisos ve "Regenerar", la edición y "Publicar"', async () => {
    renderBorrador('ADM')

    await screen.findByRole('table', { name: /precios del borrador/i })
    expect(screen.getByRole('button', { name: /regenerar/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /^publicar$/i })).toBeInTheDocument()
  })

  it('con solo PUBLICAR_LISTAS ve el borrador y "Publicar", sin edición', async () => {
    renderBorrador('ADM', ['PUBLICAR_LISTAS'])

    await screen.findByRole('table', { name: /precios del borrador/i })
    expect(screen.getByRole('button', { name: /^publicar$/i })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /regenerar|fijar precio|quitar precio manual/i })).not.toBeInTheDocument()
  })

  it('sin borrador, lo dice y ofrece generarlo solo con GESTIONAR_LISTAS', async () => {
    montarApi(apiFetchMock, [
      {
        metodo: 'GET',
        ruta: `/precios/listas/${LISTA_ID}/borrador`,
        responder: () => ({ status: 404, cuerpo: { title: 'La lista no tiene borrador.', codigo: 'RECURSO_NO_ENCONTRADO' } }),
      },
      ...reglasDeBorrador(),
    ])
    renderBorrador('GES')

    expect(await screen.findByText(/la lista no tiene borrador/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /generar borrador/i })).toBeInTheDocument()
    expect(screen.queryByRole('table', { name: /precios del borrador/i })).not.toBeInTheDocument()
  })

  it('trae todas las páginas del borrador', async () => {
    const segunda = { ...borrador({ precios: [precio({ producto_id: 'zz', producto_nombre: 'Zeta' })] }) }
    montarApi(apiFetchMock, [
      {
        metodo: 'GET',
        ruta: `/precios/listas/${LISTA_ID}/borrador`,
        responder: (url) =>
          url.searchParams.get('cursor') === 'c1'
            ? { status: 200, cuerpo: { ...segunda, siguiente_cursor: null } }
            : { status: 200, cuerpo: borrador({ siguiente_cursor: 'c1' }) },
      },
      ...reglasDeBorrador().slice(1),
    ])
    renderBorrador()

    expect(await screen.findByText('Zeta')).toBeInTheDocument()
    expect(screen.getByText('Vino A')).toBeInTheDocument()
  })
})

describe('BorradorScreen: regenerar (tarea 13.2; D5, INV-06)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
  })
  afterEach(() => {
    vi.clearAllMocks()
    vi.restoreAllMocks()
  })

  const reglaGenerar = (respuesta: ReglaDeApi['responder']): ReglaDeApi => ({
    metodo: 'POST',
    ruta: `/precios/listas/${LISTA_ID}/borrador`,
    responder: respuesta,
  })

  it('regenera con un POST con Operation-Id y muestra el resultado con sus señales', async () => {
    montarApi(apiFetchMock, [...reglasDeBorrador(), reglaGenerar(() => ({ status: 200, cuerpo: GENERACION }))])
    const usuario = userEvent.setup()
    renderBorrador()

    await usuario.click(await screen.findByRole('button', { name: /regenerar/i }))

    expect(await screen.findByText(/2 precios, 1 producto sin precio/i)).toBeInTheDocument()
    expect(screen.getByText(/1 precio calculado con otra regla de iva/i)).toBeInTheDocument()
    const envios = llamadas(apiFetchMock, 'POST', `/precios/listas/${LISTA_ID}/borrador`)
    expect(envios).toHaveLength(1)
    expect(new Headers(envios[0]?.init.headers).get('Operation-Id')).toBeTruthy()
  })

  it('tras un error de red, reintentar sin cambiar nada reenvía el mismo Operation-Id; otra regeneración usa uno nuevo', async () => {
    let intento = 0
    montarApi(apiFetchMock, [...reglasDeBorrador()])
    const base = apiFetchMock.getMockImplementation() as (ruta: string, init?: RequestInit) => Promise<unknown>
    apiFetchMock.mockImplementation((ruta: string, init?: RequestInit) => {
      if (init?.method === 'POST') {
        intento += 1
        // Los tres primeros envíos (el original y sus dos reintentos automáticos) caen por la red.
        if (intento <= 3) return Promise.reject(new TypeError('Failed to fetch'))
        return Promise.resolve({ ok: true, status: 200, json: async () => GENERACION })
      }
      return base(ruta, init)
    })
    const usuario = userEvent.setup()
    renderBorrador()

    await usuario.click(await screen.findByRole('button', { name: /regenerar/i }))
    expect(await screen.findByText(/se necesita conexión/i)).toBeInTheDocument()
    await usuario.click(screen.getByRole('button', { name: /regenerar/i }))
    await screen.findByText(/2 precios, 1 producto sin precio/i)
    await usuario.click(screen.getByRole('button', { name: /regenerar/i }))
    await waitFor(() => expect(llamadas(apiFetchMock, 'POST', `/precios/listas/${LISTA_ID}/borrador`)).toHaveLength(5))

    const ids = llamadas(apiFetchMock, 'POST', `/precios/listas/${LISTA_ID}/borrador`).map((c) =>
      new Headers(c.init.headers).get('Operation-Id'),
    )
    expect(new Set(ids.slice(0, 4)).size).toBe(1)
    expect(ids[4]).toBeTruthy()
    expect(ids[4]).not.toBe(ids[0])
  })

  it('sin conexión no envía el comando y avisa que se necesita conexión', async () => {
    montarApi(apiFetchMock, [...reglasDeBorrador(), reglaGenerar(() => ({ status: 200, cuerpo: GENERACION }))])
    vi.spyOn(window.navigator, 'onLine', 'get').mockReturnValue(false)
    const usuario = userEvent.setup()
    renderBorrador()

    await usuario.click(await screen.findByRole('button', { name: /regenerar/i }))

    expect(await screen.findByText(/se necesita conexión/i)).toBeInTheDocument()
    expect(llamadas(apiFetchMock, 'POST', `/precios/listas/${LISTA_ID}/borrador`)).toHaveLength(0)
  })

  it('un rechazo del servidor se muestra y no se reintenta', async () => {
    montarApi(apiFetchMock, [
      ...reglasDeBorrador(),
      reglaGenerar(() => ({ status: 409, cuerpo: { title: 'La lista está inactiva.', codigo: 'LISTA_INACTIVA' } })),
    ])
    const usuario = userEvent.setup()
    renderBorrador()

    await usuario.click(await screen.findByRole('button', { name: /regenerar/i }))

    expect(await screen.findByText('La lista está inactiva.')).toBeInTheDocument()
    expect(llamadas(apiFetchMock, 'POST', `/precios/listas/${LISTA_ID}/borrador`)).toHaveLength(1)
  })
})

describe('BorradorScreen: precio manual (tarea 13.2; D7)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
  })
  afterEach(() => {
    vi.clearAllMocks()
  })

  const rutaPrecio = (productoId: string) =>
    `/precios/listas/${LISTA_ID}/versiones/${VERSION_BORRADOR_ID}/precios/${productoId}`

  const reglaFijar = (productoId: string, responder: ReglaDeApi['responder']): ReglaDeApi => ({
    metodo: 'PUT',
    ruta: rutaPrecio(productoId),
    responder,
  })

  it('fija un precio manual con PUT: importe como string de dos decimales, con Operation-Id', async () => {
    montarApi(apiFetchMock, [
      ...reglasDeBorrador(),
      reglaFijar(VINO_A_ID, () => ({ status: 200, cuerpo: { version_id: VERSION_BORRADOR_ID, producto_id: VINO_A_ID, precio_final: '9000.00', manual: true } })),
    ])
    const usuario = userEvent.setup()
    renderBorrador()

    await screen.findByRole('table', { name: /precios del borrador/i })
    await usuario.click(within(filaDe('Vino A')).getByRole('button', { name: /fijar precio/i }))
    const dialogo = within(screen.getByRole('dialog'))
    await usuario.type(dialogo.getByLabelText(/precio manual/i), '9000')
    await usuario.click(dialogo.getByRole('button', { name: /guardar precio/i }))

    await waitFor(() => expect(llamadas(apiFetchMock, 'PUT', rutaPrecio(VINO_A_ID))).toHaveLength(1))
    const envio = llamadas(apiFetchMock, 'PUT', rutaPrecio(VINO_A_ID))[0]
    expect(new Headers(envio?.init.headers).get('Operation-Id')).toBeTruthy()
    expect(JSON.parse(String(envio?.init.body))).toEqual({ precio_final: '9000.00' })
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  })

  it('un importe inválido se marca junto al campo y no envía nada', async () => {
    montarApi(apiFetchMock, reglasDeBorrador())
    const usuario = userEvent.setup()
    renderBorrador()

    await screen.findByRole('table', { name: /precios del borrador/i })
    await usuario.click(within(filaDe('Vino A')).getByRole('button', { name: /fijar precio/i }))
    const dialogo = within(screen.getByRole('dialog'))
    await usuario.type(dialogo.getByLabelText(/precio manual/i), '0')
    await usuario.click(dialogo.getByRole('button', { name: /guardar precio/i }))

    expect(await dialogo.findByText(/importe mayor que cero/i)).toBeInTheDocument()
    expect(llamadas(apiFetchMock, 'PUT', rutaPrecio(VINO_A_ID))).toHaveLength(0)
  })

  it('un rechazo del servidor se muestra junto al campo y conserva lo escrito', async () => {
    montarApi(apiFetchMock, [
      ...reglasDeBorrador(),
      reglaFijar(VINO_A_ID, () => ({ status: 422, cuerpo: { title: 'El importe no es válido.', codigo: 'IMPORTE_INVALIDO' } })),
    ])
    const usuario = userEvent.setup()
    renderBorrador()

    await screen.findByRole('table', { name: /precios del borrador/i })
    await usuario.click(within(filaDe('Vino A')).getByRole('button', { name: /fijar precio/i }))
    const dialogo = within(screen.getByRole('dialog'))
    await usuario.type(dialogo.getByLabelText(/precio manual/i), '9000')
    await usuario.click(dialogo.getByRole('button', { name: /guardar precio/i }))

    expect(await dialogo.findByText('El importe no es válido.')).toBeInTheDocument()
    expect(dialogo.getByLabelText(/precio manual/i)).toHaveValue('9000')
  })

  it('el reintento tras un error de red reenvía el mismo Operation-Id y cambiar el importe usa uno nuevo', async () => {
    let intento = 0
    montarApi(apiFetchMock, reglasDeBorrador())
    const base = apiFetchMock.getMockImplementation() as (ruta: string, init?: RequestInit) => Promise<unknown>
    apiFetchMock.mockImplementation((ruta: string, init?: RequestInit) => {
      if (init?.method === 'PUT') {
        intento += 1
        if (intento <= 3) return Promise.reject(new TypeError('Failed to fetch'))
        return Promise.resolve({ ok: true, status: 200, json: async () => ({ version_id: VERSION_BORRADOR_ID, producto_id: VINO_A_ID, precio_final: '9000.00', manual: true }) })
      }
      return base(ruta, init)
    })
    const usuario = userEvent.setup()
    renderBorrador()

    await screen.findByRole('table', { name: /precios del borrador/i })
    await usuario.click(within(filaDe('Vino A')).getByRole('button', { name: /fijar precio/i }))
    const dialogo = within(screen.getByRole('dialog'))
    await usuario.type(dialogo.getByLabelText(/precio manual/i), '9000')
    await usuario.click(dialogo.getByRole('button', { name: /guardar precio/i }))
    expect(await dialogo.findByText(/se necesita conexión/i)).toBeInTheDocument()
    await usuario.click(dialogo.getByRole('button', { name: /guardar precio/i }))
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())

    const ids = llamadas(apiFetchMock, 'PUT', rutaPrecio(VINO_A_ID)).map((c) => new Headers(c.init.headers).get('Operation-Id'))
    expect(ids).toHaveLength(4)
    expect(new Set(ids).size).toBe(1)
  })

  it('cambiar el importe después de un error es otra operación: Operation-Id nuevo', async () => {
    let intento = 0
    montarApi(apiFetchMock, reglasDeBorrador())
    const base = apiFetchMock.getMockImplementation() as (ruta: string, init?: RequestInit) => Promise<unknown>
    apiFetchMock.mockImplementation((ruta: string, init?: RequestInit) => {
      if (init?.method === 'PUT') {
        intento += 1
        if (intento <= 3) return Promise.reject(new TypeError('Failed to fetch'))
        return Promise.resolve({ ok: true, status: 200, json: async () => ({ version_id: VERSION_BORRADOR_ID, producto_id: VINO_A_ID, precio_final: '9100.00', manual: true }) })
      }
      return base(ruta, init)
    })
    const usuario = userEvent.setup()
    renderBorrador()

    await screen.findByRole('table', { name: /precios del borrador/i })
    await usuario.click(within(filaDe('Vino A')).getByRole('button', { name: /fijar precio/i }))
    const dialogo = within(screen.getByRole('dialog'))
    await usuario.type(dialogo.getByLabelText(/precio manual/i), '9000')
    await usuario.click(dialogo.getByRole('button', { name: /guardar precio/i }))
    await dialogo.findByText(/se necesita conexión/i)
    await usuario.clear(dialogo.getByLabelText(/precio manual/i))
    await usuario.type(dialogo.getByLabelText(/precio manual/i), '9100')
    await usuario.click(dialogo.getByRole('button', { name: /guardar precio/i }))
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())

    const ids = llamadas(apiFetchMock, 'PUT', rutaPrecio(VINO_A_ID)).map((c) => new Headers(c.init.headers).get('Operation-Id'))
    expect(ids).toHaveLength(4)
    expect(new Set(ids.slice(0, 3)).size).toBe(1)
    expect(ids[3]).not.toBe(ids[0])
  })

  it('fija un precio manual a un producto sin precio', async () => {
    montarApi(apiFetchMock, [
      ...reglasDeBorrador(),
      reglaFijar(GASEOSA_C_ID, () => ({ status: 200, cuerpo: { version_id: VERSION_BORRADOR_ID, producto_id: GASEOSA_C_ID, precio_final: '1200.00', manual: true } })),
    ])
    const usuario = userEvent.setup()
    renderBorrador()

    const sinPrecio = within(await screen.findByRole('table', { name: /productos sin precio/i }))
    await usuario.click(sinPrecio.getByRole('button', { name: /fijar precio/i }))
    const dialogo = within(screen.getByRole('dialog'))
    await usuario.type(dialogo.getByLabelText(/precio manual/i), '1200,00')
    await usuario.click(dialogo.getByRole('button', { name: /guardar precio/i }))

    await waitFor(() => expect(llamadas(apiFetchMock, 'PUT', rutaPrecio(GASEOSA_C_ID))).toHaveLength(1))
    expect(JSON.parse(String(llamadas(apiFetchMock, 'PUT', rutaPrecio(GASEOSA_C_ID))[0]?.init.body))).toEqual({ precio_final: '1200.00' })
  })

  it('quita la marca manual con un PUT de precio nulo', async () => {
    montarApi(apiFetchMock, [
      ...reglasDeBorrador(),
      reglaFijar(CERVEZA_B_ID, () => ({ status: 200, cuerpo: { version_id: VERSION_BORRADOR_ID, producto_id: CERVEZA_B_ID, precio_final: '31168.00', manual: false } })),
    ])
    const usuario = userEvent.setup()
    renderBorrador()

    await screen.findByRole('table', { name: /precios del borrador/i })
    await usuario.click(within(filaDe('Cerveza B')).getByRole('button', { name: /quitar precio manual/i }))

    await waitFor(() => expect(llamadas(apiFetchMock, 'PUT', rutaPrecio(CERVEZA_B_ID))).toHaveLength(1))
    expect(JSON.parse(String(llamadas(apiFetchMock, 'PUT', rutaPrecio(CERVEZA_B_ID))[0]?.init.body))).toEqual({ precio_final: null })
  })

  it('sin conexión no envía el precio y avisa', async () => {
    montarApi(apiFetchMock, reglasDeBorrador())
    vi.spyOn(window.navigator, 'onLine', 'get').mockReturnValue(false)
    const usuario = userEvent.setup()
    renderBorrador()

    await screen.findByRole('table', { name: /precios del borrador/i })
    await usuario.click(within(filaDe('Vino A')).getByRole('button', { name: /fijar precio/i }))
    const dialogo = within(screen.getByRole('dialog'))
    await usuario.type(dialogo.getByLabelText(/precio manual/i), '9000')
    await usuario.click(dialogo.getByRole('button', { name: /guardar precio/i }))

    expect(await dialogo.findByText(/se necesita conexión/i)).toBeInTheDocument()
    expect(llamadas(apiFetchMock, 'PUT', rutaPrecio(VINO_A_ID))).toHaveLength(0)
    vi.restoreAllMocks()
  })
})

describe('BorradorScreen: publicar (tarea 13.3; PRC-02, PRC-06, D6)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
  })
  afterEach(() => {
    vi.clearAllMocks()
  })

  const rutaPublicar = `/precios/listas/${LISTA_ID}/versiones/${VERSION_BORRADOR_ID}/publicar`

  const reglaPublicar = (responder: ReglaDeApi['responder']): ReglaDeApi => ({ metodo: 'POST', ruta: rutaPublicar, responder })

  it('la confirmación informa cuántos precios se publican y cuántos productos quedan sin precio', async () => {
    montarApi(apiFetchMock, reglasDeBorrador())
    const usuario = userEvent.setup()
    renderBorrador('ADM')

    await usuario.click(await screen.findByRole('button', { name: /^publicar$/i }))

    const dialogo = within(screen.getByRole('dialog'))
    expect(dialogo.getByText(/2 precios, 1 producto sin precio/i)).toBeInTheDocument()
  })

  it('el conteo incluye todas las páginas', async () => {
    montarApi(apiFetchMock, [
      {
        metodo: 'GET',
        ruta: `/precios/listas/${LISTA_ID}/borrador`,
        responder: (url) =>
          url.searchParams.get('cursor') === 'c1'
            ? { status: 200, cuerpo: borrador({ precios: [PRECIO_MANUAL_CON_SENAL], siguiente_cursor: null }) }
            : { status: 200, cuerpo: borrador({ precios: [precio()], siguiente_cursor: 'c1' }) },
      },
      ...reglasDeBorrador().slice(1),
    ])
    const usuario = userEvent.setup()
    renderBorrador('ADM')

    await waitFor(() => expect(llamadas(apiFetchMock, 'GET', `/precios/listas/${LISTA_ID}/borrador`)).toHaveLength(2))
    await usuario.click(await screen.findByRole('button', { name: /^publicar$/i }))

    expect(within(screen.getByRole('dialog')).getByText(/2 precios, 1 producto sin precio/i)).toBeInTheDocument()
  })

  it('publica sin vigencias: un POST con Operation-Id y las dos vigencias nulas, y vuelve al detalle', async () => {
    montarApi(apiFetchMock, [...reglasDeBorrador(), reglaPublicar(() => ({ status: 200, cuerpo: VERSION_BORRADOR }))])
    const usuario = userEvent.setup()
    renderBorrador('ADM')

    await usuario.click(await screen.findByRole('button', { name: /^publicar$/i }))
    await usuario.click(within(screen.getByRole('dialog')).getByRole('button', { name: /confirmar publicación/i }))

    expect(await screen.findByText(/detalle de la lista/i)).toBeInTheDocument()
    const envios = llamadas(apiFetchMock, 'POST', rutaPublicar)
    expect(envios).toHaveLength(1)
    expect(new Headers(envios[0]?.init.headers).get('Operation-Id')).toBeTruthy()
    expect(JSON.parse(String(envios[0]?.init.body))).toEqual({ vigencia_desde: null, vigencia_hasta: null })
  })

  it('con vigencias las manda como instantes con zona', async () => {
    montarApi(apiFetchMock, [...reglasDeBorrador(), reglaPublicar(() => ({ status: 200, cuerpo: VERSION_BORRADOR }))])
    const usuario = userEvent.setup()
    renderBorrador('ADM')

    await usuario.click(await screen.findByRole('button', { name: /^publicar$/i }))
    const dialogo = within(screen.getByRole('dialog'))
    fireEvent.change(dialogo.getByLabelText(/vigencia desde/i), { target: { value: '2099-10-10T09:00' } })
    fireEvent.change(dialogo.getByLabelText(/vigencia hasta/i), { target: { value: '2099-11-01T09:00' } })
    await usuario.click(dialogo.getByRole('button', { name: /confirmar publicación/i }))

    await screen.findByText(/detalle de la lista/i)
    const cuerpo = JSON.parse(String(llamadas(apiFetchMock, 'POST', rutaPublicar)[0]?.init.body)) as Record<string, string>
    expect(cuerpo.vigencia_desde).toMatch(/^2099-10-10T\d\d:00:00\.000Z$/)
    expect(cuerpo.vigencia_hasta).toMatch(/^2099-11-01T\d\d:00:00\.000Z$/)
  })

  it('una vigencia hasta anterior a la desde se marca y no envía el comando', async () => {
    montarApi(apiFetchMock, reglasDeBorrador())
    const usuario = userEvent.setup()
    renderBorrador('ADM')

    await usuario.click(await screen.findByRole('button', { name: /^publicar$/i }))
    const dialogo = within(screen.getByRole('dialog'))
    fireEvent.change(dialogo.getByLabelText(/vigencia desde/i), { target: { value: '2099-10-10T09:00' } })
    fireEvent.change(dialogo.getByLabelText(/vigencia hasta/i), { target: { value: '2099-10-09T09:00' } })
    await usuario.click(dialogo.getByRole('button', { name: /confirmar publicación/i }))

    expect(await dialogo.findByText(/vigencia hasta debe ser posterior/i)).toBeInTheDocument()
    expect(llamadas(apiFetchMock, 'POST', rutaPublicar)).toHaveLength(0)
  })

  it('VIGENCIA_INVALIDA se muestra junto a la fecha, el diálogo sigue abierto y el borrador sin publicar', async () => {
    montarApi(apiFetchMock, [
      ...reglasDeBorrador(),
      reglaPublicar(() => ({
        status: 422,
        cuerpo: { title: 'La vigencia desde no puede ser anterior a la publicación.', codigo: 'VIGENCIA_INVALIDA' },
      })),
    ])
    const usuario = userEvent.setup()
    renderBorrador('ADM')

    await usuario.click(await screen.findByRole('button', { name: /^publicar$/i }))
    const dialogo = within(screen.getByRole('dialog'))
    fireEvent.change(dialogo.getByLabelText(/vigencia desde/i), { target: { value: '2020-01-01T09:00' } })
    await usuario.click(dialogo.getByRole('button', { name: /confirmar publicación/i }))

    expect(await dialogo.findByText('La vigencia desde no puede ser anterior a la publicación.')).toBeInTheDocument()
    expect(dialogo.getByLabelText(/vigencia desde/i)).toHaveValue('2020-01-01T09:00')
    expect(screen.queryByText(/detalle de la lista/i)).not.toBeInTheDocument()
  })

  it('tras un error de red, reintentar reenvía el mismo Operation-Id', async () => {
    let intento = 0
    montarApi(apiFetchMock, reglasDeBorrador())
    const base = apiFetchMock.getMockImplementation() as (ruta: string, init?: RequestInit) => Promise<unknown>
    apiFetchMock.mockImplementation((ruta: string, init?: RequestInit) => {
      if (init?.method === 'POST') {
        intento += 1
        if (intento <= 3) return Promise.reject(new TypeError('Failed to fetch'))
        return Promise.resolve({ ok: true, status: 200, json: async () => VERSION_BORRADOR })
      }
      return base(ruta, init)
    })
    const usuario = userEvent.setup()
    renderBorrador('ADM')

    await usuario.click(await screen.findByRole('button', { name: /^publicar$/i }))
    const dialogo = within(screen.getByRole('dialog'))
    await usuario.click(dialogo.getByRole('button', { name: /confirmar publicación/i }))
    expect(await dialogo.findByText(/se necesita conexión/i)).toBeInTheDocument()
    await usuario.click(dialogo.getByRole('button', { name: /confirmar publicación/i }))
    await screen.findByText(/detalle de la lista/i)

    const ids = llamadas(apiFetchMock, 'POST', rutaPublicar).map((c) => new Headers(c.init.headers).get('Operation-Id'))
    expect(ids).toHaveLength(4)
    expect(new Set(ids).size).toBe(1)
  })
})
