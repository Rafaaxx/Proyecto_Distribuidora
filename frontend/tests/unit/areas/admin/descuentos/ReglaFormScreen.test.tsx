/**
 * Change 16, tarea 15.2: alta y edición de una regla de descuento (spec
 * `administracion-de-descuentos`, requisito "Las reglas se cargan y se revisan desde la pantalla";
 * DSC-01 a DSC-04, TR-02, TR-10, INV-03, INV-04, INV-06; `02` §6.5).
 */

import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }))
vi.mock('../../../../../src/lib/api/httpClient', () => ({ apiFetch: apiFetchMock }))

import DescuentosArea from '../../../../../src/areas/admin/descuentos/DescuentosArea'
import { enrutar, llamadas, type ReglaDeApi } from '../../../utils/enrutarApi'
import { queryClientConYo } from '../../../utils/permisosDePrueba'
import { CATEGORIA_ID, MARCA_ID, REGLA_ID, regla, reglaDeMarca, reglasDeCatalogo } from './descuentosDePrueba'

function montar(ruta: string) {
  return render(
    <QueryClientProvider client={queryClientConYo('ADM')}>
      <MemoryRouter initialEntries={[ruta]}>
        <Routes>
          <Route path="/admin/descuentos/*" element={<DescuentosArea />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

type Usuario = ReturnType<typeof userEvent.setup>

async function completarAlta(usuario: Usuario, campos: { umbral?: string; valor?: string } = {}) {
  await usuario.type(screen.getByLabelText(/^nombre$/i), 'Mayorista 20 cajas')
  await usuario.type(screen.getByLabelText(/^umbral$/i), campos.umbral ?? '20')
  await usuario.type(screen.getByLabelText(/porcentaje de descuento/i), campos.valor ?? '5')
  await usuario.type(screen.getByLabelText(/^prioridad$/i), '10')
}

function altaOk(): ReglaDeApi {
  return { metodo: 'POST', ruta: '/descuentos/reglas', responder: () => ({ status: 201, cuerpo: regla() }) }
}

function envios() {
  return llamadas(apiFetchMock, 'POST', '/descuentos/reglas')
}

function cuerpoDe(indice = 0): Record<string, unknown> {
  return JSON.parse(String(envios()[indice]?.init.body)) as Record<string, unknown>
}

function operationIdDe(indice = 0): string | null {
  return new Headers(envios()[indice]?.init.headers).get('Operation-Id')
}

describe('alta de una regla de descuento (tarea 15.2)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
    Object.defineProperty(window.navigator, 'onLine', { value: true, configurable: true })
  })
  afterEach(() => {
    vi.clearAllMocks()
  })

  it('crea "cajas ≥ 20 → 5 %" sobre toda la venta con un POST con Operation-Id y va al detalle', async () => {
    enrutar(apiFetchMock, [
      altaOk(),
      { metodo: 'GET', ruta: `/descuentos/reglas/${REGLA_ID}`, responder: () => ({ status: 200, cuerpo: regla() }) },
    ])
    const usuario = userEvent.setup()
    montar('/admin/descuentos/nueva')

    await completarAlta(usuario)
    await usuario.click(screen.getByRole('button', { name: /guardar regla/i }))

    expect(await screen.findByRole('heading', { name: 'Mayorista 20 cajas' })).toBeInTheDocument()
    expect(envios()).toHaveLength(1)
    expect(operationIdDe()).toBeTruthy()
    expect(cuerpoDe()).toEqual({
      nombre: 'Mayorista 20 cajas',
      tipo: 'VOLUMEN_OPERACION',
      medida: 'CAJAS_EQUIVALENTES',
      operador: 'GTE',
      umbral: '20',
      accion_tipo: 'PORCENTAJE',
      accion_valor: '0.050000',
      prioridad: 10,
      acumulable: false,
      alcances: [],
      vigencia_desde: null,
      vigencia_hasta: null,
    })
  })

  it('Escenario el porcentaje se escribe como porcentaje: "12,5" viaja como "0.125000"', async () => {
    enrutar(apiFetchMock, [altaOk()])
    const usuario = userEvent.setup()
    montar('/admin/descuentos/nueva')

    await completarAlta(usuario, { valor: '12,5' })
    await usuario.click(screen.getByRole('button', { name: /guardar regla/i }))

    await waitFor(() => expect(envios()).toHaveLength(1))
    expect(cuerpoDe().accion_valor).toBe('0.125000')
  })

  it('con importe fijo el valor se pide como importe y viaja tal cual, con punto', async () => {
    enrutar(apiFetchMock, [altaOk()])
    const usuario = userEvent.setup()
    montar('/admin/descuentos/nueva')

    await usuario.selectOptions(screen.getByLabelText(/^acción$/i), 'IMPORTE_FIJO')
    await usuario.type(screen.getByLabelText(/^nombre$/i), 'Fija')
    await usuario.type(screen.getByLabelText(/^umbral$/i), '20')
    await usuario.type(screen.getByLabelText(/importe fijo/i), '1000,50')
    await usuario.type(screen.getByLabelText(/^prioridad$/i), '5')
    await usuario.click(screen.getByLabelText(/^acumulable$/i))
    await usuario.click(screen.getByRole('button', { name: /guardar regla/i }))

    await waitFor(() => expect(envios()).toHaveLength(1))
    expect(cuerpoDe()).toMatchObject({ accion_tipo: 'IMPORTE_FIJO', accion_valor: '1000.50', acumulable: true })
  })

  it('Escenario los alcances se piden solo en reglas de alcance', async () => {
    enrutar(apiFetchMock, [...reglasDeCatalogo(), altaOk()])
    const usuario = userEvent.setup()
    montar('/admin/descuentos/nueva')

    // Por defecto: sobre toda la venta, sin selector de alcances.
    expect(screen.getByLabelText(/^alcance de la regla$/i)).toHaveValue('VOLUMEN_OPERACION')
    expect(screen.queryByRole('button', { name: /agregar alcance/i })).not.toBeInTheDocument()
    expect(screen.queryByLabelText(/tipo de alcance/i)).not.toBeInTheDocument()

    await usuario.selectOptions(screen.getByLabelText(/^alcance de la regla$/i), 'VOLUMEN_ALCANCE')
    expect(screen.getByRole('button', { name: /agregar alcance/i })).toBeInTheDocument()

    // Sin ningún alcance elegido, no deja guardar y lo señala sin enviar nada.
    await completarAlta(usuario)
    await usuario.click(screen.getByRole('button', { name: /guardar regla/i }))
    expect(await screen.findByText(/elegí al menos un producto, una categoría o una marca/i)).toBeInTheDocument()
    expect(envios()).toHaveLength(0)

    // Elige una marca y una categoría, y viajan los dos.
    await usuario.selectOptions(screen.getByLabelText(/tipo de alcance/i), 'MARCA')
    await usuario.selectOptions(await screen.findByLabelText(/^entidad$/i), MARCA_ID)
    await usuario.click(screen.getByRole('button', { name: /agregar alcance/i }))
    await usuario.selectOptions(screen.getByLabelText(/tipo de alcance/i), 'CATEGORIA')
    await usuario.selectOptions(await screen.findByLabelText(/^entidad$/i), CATEGORIA_ID)
    await usuario.click(screen.getByRole('button', { name: /agregar alcance/i }))
    expect(screen.getByText('Marca Coca-Cola')).toBeInTheDocument()
    expect(screen.getByText('Categoría Gaseosas')).toBeInTheDocument()
    await usuario.click(screen.getByRole('button', { name: /guardar regla/i }))

    await waitFor(() => expect(envios()).toHaveLength(1))
    expect(cuerpoDe()).toMatchObject({
      tipo: 'VOLUMEN_ALCANCE',
      alcances: [
        { tipo: 'MARCA', entidad_id: MARCA_ID },
        { tipo: 'CATEGORIA', entidad_id: CATEGORIA_ID },
      ],
    })
  })

  it('un alcance agregado se puede quitar, y al volver a "toda la venta" se descartan', async () => {
    enrutar(apiFetchMock, [...reglasDeCatalogo(), altaOk()])
    const usuario = userEvent.setup()
    montar('/admin/descuentos/nueva')
    await usuario.selectOptions(screen.getByLabelText(/^alcance de la regla$/i), 'VOLUMEN_ALCANCE')
    await usuario.selectOptions(screen.getByLabelText(/tipo de alcance/i), 'MARCA')
    await usuario.selectOptions(await screen.findByLabelText(/^entidad$/i), MARCA_ID)
    await usuario.click(screen.getByRole('button', { name: /agregar alcance/i }))

    await usuario.click(screen.getByRole('button', { name: /quitar marca coca-cola/i }))
    expect(screen.queryByText('Marca Coca-Cola')).not.toBeInTheDocument()

    await usuario.selectOptions(screen.getByLabelText(/tipo de alcance/i), 'MARCA')
    await usuario.selectOptions(await screen.findByLabelText(/^entidad$/i), MARCA_ID)
    await usuario.click(screen.getByRole('button', { name: /agregar alcance/i }))
    await usuario.selectOptions(screen.getByLabelText(/^alcance de la regla$/i), 'VOLUMEN_OPERACION')
    await completarAlta(usuario)
    await usuario.click(screen.getByRole('button', { name: /guardar regla/i }))

    await waitFor(() => expect(envios()).toHaveLength(1))
    expect(cuerpoDe()).toMatchObject({ tipo: 'VOLUMEN_OPERACION', alcances: [] })
  })

  it('Escenario umbral según la medida: unidades base con decimales se señala antes de enviar', async () => {
    enrutar(apiFetchMock, [altaOk()])
    const usuario = userEvent.setup()
    montar('/admin/descuentos/nueva')

    await usuario.selectOptions(screen.getByLabelText(/^medida$/i), 'UNIDADES_BASE')
    await completarAlta(usuario, { umbral: '60,5' })
    await usuario.click(screen.getByRole('button', { name: /guardar regla/i }))

    expect(await screen.findByText(/en unidades base el umbral es un entero/i)).toBeInTheDocument()
    expect(apiFetchMock).not.toHaveBeenCalled()
  })

  it('un porcentaje fuera de rango y una prioridad inválida se señalan junto a su campo', async () => {
    enrutar(apiFetchMock, [altaOk()])
    const usuario = userEvent.setup()
    montar('/admin/descuentos/nueva')

    await usuario.type(screen.getByLabelText(/^nombre$/i), 'X')
    await usuario.type(screen.getByLabelText(/^umbral$/i), '20')
    await usuario.type(screen.getByLabelText(/porcentaje de descuento/i), '120')
    await usuario.type(screen.getByLabelText(/^prioridad$/i), '0')
    await usuario.click(screen.getByRole('button', { name: /guardar regla/i }))

    expect(await screen.findByText(/porcentaje mayor que cero y hasta 100/i)).toBeInTheDocument()
    expect(screen.getByText(/la prioridad es un entero desde 1/i)).toBeInTheDocument()
    expect(apiFetchMock).not.toHaveBeenCalled()
  })

  it('Escenario vigencia invertida: el cliente la señala junto a la vigencia hasta y no envía', async () => {
    enrutar(apiFetchMock, [altaOk()])
    const usuario = userEvent.setup()
    montar('/admin/descuentos/nueva')

    await completarAlta(usuario)
    await usuario.type(screen.getByLabelText(/vigencia desde/i), '2026-12-01T10:00')
    await usuario.type(screen.getByLabelText(/vigencia hasta/i), '2026-11-01T10:00')
    await usuario.click(screen.getByRole('button', { name: /guardar regla/i }))

    expect(await screen.findByText(/la vigencia hasta debe ser posterior a la vigencia desde/i)).toBeInTheDocument()
    expect(apiFetchMock).not.toHaveBeenCalled()
  })

  it('Escenario error del servidor junto al campo: VIGENCIA_INVALIDA se muestra junto a la vigencia y conserva lo cargado', async () => {
    enrutar(apiFetchMock, [
      {
        metodo: 'POST',
        ruta: '/descuentos/reglas',
        responder: () => ({ status: 422, cuerpo: { title: 'La vigencia hasta debe ser posterior a la desde.', codigo: 'VIGENCIA_INVALIDA' } }),
      },
    ])
    const usuario = userEvent.setup()
    montar('/admin/descuentos/nueva')

    await completarAlta(usuario)
    await usuario.click(screen.getByRole('button', { name: /guardar regla/i }))

    const mensaje = await screen.findByText('La vigencia hasta debe ser posterior a la desde.')
    expect(mensaje.closest('div')).toContainElement(screen.getByLabelText(/vigencia hasta/i))
    expect(screen.getByLabelText(/^nombre$/i)).toHaveValue('Mayorista 20 cajas')
    expect(screen.getByLabelText(/^umbral$/i)).toHaveValue('20')
    expect(screen.getByLabelText(/porcentaje de descuento/i)).toHaveValue('5')
    expect(envios()).toHaveLength(1)
  })

  it.each([
    ['UMBRAL_INVALIDO', /^umbral$/i],
    ['ACCION_INVALIDA', /porcentaje de descuento/i],
    ['PRIORIDAD_INVALIDA', /^prioridad$/i],
  ])('el rechazo %s del servidor se muestra junto a su campo', async (codigo, campo) => {
    enrutar(apiFetchMock, [
      { metodo: 'POST', ruta: '/descuentos/reglas', responder: () => ({ status: 422, cuerpo: { title: `Mensaje de ${codigo}`, codigo } }) },
    ])
    const usuario = userEvent.setup()
    montar('/admin/descuentos/nueva')

    await completarAlta(usuario)
    await usuario.click(screen.getByRole('button', { name: /guardar regla/i }))

    const mensaje = await screen.findByText(`Mensaje de ${codigo}`)
    expect(mensaje.closest('div')).toContainElement(screen.getByLabelText(campo))
  })

  it('Escenario reintento seguro: tras perder la respuesta, reintentar sin cambiar nada reenvía el mismo operation_id', async () => {
    let intentos = 0
    apiFetchMock.mockImplementation((ruta: string, init?: RequestInit) => {
      if ((init?.method ?? 'GET') === 'POST' && ruta === '/descuentos/reglas') {
        intentos += 1
        // Los tres intentos automáticos del primer envío se pierden; el reintento manual entra.
        if (intentos <= 3) return Promise.reject(new TypeError('Failed to fetch'))
        return Promise.resolve({ ok: true, status: 201, json: async () => regla() })
      }
      return Promise.resolve({ ok: true, status: 200, json: async () => regla() })
    })
    const usuario = userEvent.setup()
    montar('/admin/descuentos/nueva')
    await completarAlta(usuario)

    await usuario.click(screen.getByRole('button', { name: /guardar regla/i }))
    expect(await screen.findByText(/se necesita conexión para completar esta operación/i)).toBeInTheDocument()
    await usuario.click(screen.getByRole('button', { name: /guardar regla/i }))

    expect(await screen.findByRole('heading', { name: 'Mayorista 20 cajas' })).toBeInTheDocument()
    const ids = envios().map((e) => new Headers(e.init.headers).get('Operation-Id'))
    expect(ids).toHaveLength(4)
    expect(new Set(ids).size).toBe(1)
  })

  it('si cambia el contenido tras el error de red, el reintento es otra operación (otro operation_id)', async () => {
    let intentos = 0
    apiFetchMock.mockImplementation((ruta: string, init?: RequestInit) => {
      if ((init?.method ?? 'GET') === 'POST' && ruta === '/descuentos/reglas') {
        intentos += 1
        if (intentos <= 3) return Promise.reject(new TypeError('Failed to fetch'))
        return Promise.resolve({ ok: true, status: 201, json: async () => regla() })
      }
      return Promise.resolve({ ok: true, status: 200, json: async () => regla() })
    })
    const usuario = userEvent.setup()
    montar('/admin/descuentos/nueva')
    await completarAlta(usuario)
    await usuario.click(screen.getByRole('button', { name: /guardar regla/i }))
    await screen.findByText(/se necesita conexión/i)

    await usuario.clear(screen.getByLabelText(/^prioridad$/i))
    await usuario.type(screen.getByLabelText(/^prioridad$/i), '11')
    await usuario.click(screen.getByRole('button', { name: /guardar regla/i }))

    await waitFor(() => expect(envios()).toHaveLength(4))
    const ids = envios().map((e) => new Headers(e.init.headers).get('Operation-Id'))
    expect(ids[3]).not.toBe(ids[0])
    expect(new Set(ids.slice(0, 3)).size).toBe(1)
  })

  it('Escenario sin conexión: avisa que requiere conexión y no envía nada', async () => {
    Object.defineProperty(window.navigator, 'onLine', { value: false, configurable: true })
    enrutar(apiFetchMock, [altaOk()])
    const usuario = userEvent.setup()
    montar('/admin/descuentos/nueva')

    await completarAlta(usuario)
    await usuario.click(screen.getByRole('button', { name: /guardar regla/i }))

    expect(await screen.findByText(/se necesita conexión para completar esta operación/i)).toBeInTheDocument()
    expect(envios()).toHaveLength(0)
  })
})

describe('edición de una regla en borrador (tarea 15.2)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
    Object.defineProperty(window.navigator, 'onLine', { value: true, configurable: true })
  })
  afterEach(() => {
    vi.clearAllMocks()
  })

  it('carga lo guardado como lo escribió la persona y reemplaza el borrador con un PUT completo', async () => {
    enrutar(apiFetchMock, [
      { metodo: 'GET', ruta: `/descuentos/reglas/${REGLA_ID}`, responder: () => ({ status: 200, cuerpo: regla() }) },
      { metodo: 'PUT', ruta: `/descuentos/reglas/${REGLA_ID}`, responder: () => ({ status: 200, cuerpo: regla({ prioridad: 3 }) }) },
    ])
    const usuario = userEvent.setup()
    montar(`/admin/descuentos/${REGLA_ID}/editar`)

    expect(await screen.findByLabelText(/^nombre$/i)).toHaveValue('Mayorista 20 cajas')
    expect(screen.getByLabelText(/^umbral$/i)).toHaveValue('20')
    expect(screen.getByLabelText(/porcentaje de descuento/i)).toHaveValue('5')
    expect(screen.getByLabelText(/^prioridad$/i)).toHaveValue('10')

    await usuario.clear(screen.getByLabelText(/^prioridad$/i))
    await usuario.type(screen.getByLabelText(/^prioridad$/i), '3')
    await usuario.click(screen.getByRole('button', { name: /guardar cambios/i }))

    await waitFor(() => expect(llamadas(apiFetchMock, 'PUT', `/descuentos/reglas/${REGLA_ID}`)).toHaveLength(1))
    const envio = llamadas(apiFetchMock, 'PUT', `/descuentos/reglas/${REGLA_ID}`)[0]
    expect(new Headers(envio?.init.headers).get('Operation-Id')).toBeTruthy()
    expect(JSON.parse(String(envio?.init.body))).toMatchObject({ nombre: 'Mayorista 20 cajas', accion_valor: '0.050000', prioridad: 3 })
  })

  it('una regla de alcance trae sus alcances con nombre', async () => {
    enrutar(apiFetchMock, [
      ...reglasDeCatalogo(),
      {
        metodo: 'GET',
        ruta: `/descuentos/reglas/${REGLA_ID}`,
        responder: () => ({ status: 200, cuerpo: reglaDeMarca({ id: REGLA_ID, estado: 'BORRADOR' }) }),
      },
    ])
    montar(`/admin/descuentos/${REGLA_ID}/editar`)

    expect(await screen.findByText('Marca Coca-Cola')).toBeInTheDocument()
    expect(screen.getByLabelText(/importe fijo/i)).toHaveValue('5000')
  })

  it('una regla que ya no es borrador no se edita: lo explica y vuelve al detalle', async () => {
    enrutar(apiFetchMock, [
      { metodo: 'GET', ruta: `/descuentos/reglas/${REGLA_ID}`, responder: () => ({ status: 200, cuerpo: regla({ estado: 'ACTIVA' }) }) },
    ])
    montar(`/admin/descuentos/${REGLA_ID}/editar`)

    expect(await screen.findByText(/solo se edita una regla en borrador/i)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /guardar cambios/i })).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: /volver al detalle/i })).toHaveAttribute('href', `/admin/descuentos/${REGLA_ID}`)
  })
})
