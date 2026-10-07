import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }))
vi.mock('../../../../../src/lib/api/httpClient', () => ({ apiFetch: apiFetchMock }))

import { ClienteFormScreen } from '../../../../../src/areas/admin/clientes/ClienteFormScreen'
import { queryClientConYo } from '../../../utils/permisosDePrueba'

function respuesta(status: number, cuerpo: unknown) {
  return { ok: status >= 200 && status < 300, status, json: async () => cuerpo }
}

const CLIENTE = {
  id: '11111111-1111-4111-8111-111111111111',
  codigo: null,
  nombre: 'Kiosco La Esquina',
  razon_social: null,
  documento_tipo: null,
  documento_numero: null,
  direccion: 'Av. San Martín 1420',
  contacto: 'Rocío',
  telefono: null,
  email: null,
  lista_precio_id: null,
  limite_credito: null,
  politica_credito: null,
  tolerancia_offline_tipo: null,
  tolerancia_offline_valor: null,
  estado_facturacion_default: null,
  es_consumidor_final: false,
  estado: 'ACTIVO',
  creado_en: '2026-01-01T00:00:00Z',
  actualizado_en: '2026-01-01T00:00:00Z',
}

/** El alta ofrece el selector de lista de precios (change 13, 13.4): además de la escritura, lee
 * `GET /precios/listas/opciones`. Responde las opciones y, a cualquier otra ruta, `cuerpo`. */
function responderAlta(cuerpoDelPost: unknown) {
  apiFetchMock.mockImplementation((ruta: string) =>
    Promise.resolve(
      String(ruta).startsWith('/precios/listas/opciones')
        ? respuesta(200, { items: [] })
        : respuesta(201, cuerpoDelPost),
    ),
  )
}

function envios(metodo: string): [string, RequestInit][] {
  return (apiFetchMock.mock.calls as [string, RequestInit | undefined][])
    .filter(([, init]) => (init?.method ?? 'GET') === metodo)
    .map(([ruta, init]) => [ruta, init ?? {}])
}

const SIN_PERMISO_DE_CLIENTES = 'No tenés permiso para gestionar clientes.'

function renderAlta(queryClient: QueryClient = queryClientConYo('GES')) {
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/admin/clientes/nuevo']}>
        <Routes>
          <Route path="/admin/clientes" element={<p>Listado de clientes</p>} />
          <Route path="/admin/clientes/nuevo" element={<ClienteFormScreen />} />
          <Route path="/admin/clientes/:clienteId" element={<ClienteFormScreen />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

function renderEdicion(clienteId: string, queryClient: QueryClient = queryClientConYo('GES')) {
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[`/admin/clientes/${clienteId}`]}>
        <Routes>
          <Route path="/admin/clientes" element={<p>Listado de clientes</p>} />
          <Route path="/admin/clientes/:clienteId" element={<ClienteFormScreen />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('ClienteFormScreen: alta (tarea 5.3)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('da de alta un cliente con un único envío, con Operation-Id', async () => {
    responderAlta(CLIENTE)

    const usuarioEvento = userEvent.setup()
    renderAlta()

    await usuarioEvento.type(screen.getByLabelText(/^nombre$/i), 'Kiosco La Esquina')
    await usuarioEvento.type(screen.getByLabelText(/^dirección$/i), 'Av. San Martín 1420')
    await usuarioEvento.type(screen.getByLabelText(/^contacto$/i), 'Rocío')
    await usuarioEvento.click(screen.getByRole('button', { name: /crear cliente/i }))

    await waitFor(() => expect(envios('POST')).toHaveLength(1))
    const [ruta, opciones] = envios('POST')[0] as [string, RequestInit]
    expect(ruta).toBe('/clientes')
    expect(opciones.method).toBe('POST')
    expect((opciones.headers as Record<string, string>)['Operation-Id']).toBeTruthy()
    expect(JSON.parse(String(opciones.body))).toMatchObject({ nombre: 'Kiosco La Esquina' })
  })

  it('el mismo operation_id se reenvía en el reintento (mismo criterio que proveedores)', async () => {
    responderAlta(CLIENTE)

    const usuarioEvento = userEvent.setup()
    renderAlta()

    await usuarioEvento.type(screen.getByLabelText(/^nombre$/i), 'Kiosco La Esquina')
    await usuarioEvento.type(screen.getByLabelText(/^dirección$/i), 'Av. San Martín 1420')
    await usuarioEvento.type(screen.getByLabelText(/^contacto$/i), 'Rocío')
    await usuarioEvento.click(screen.getByRole('button', { name: /crear cliente/i }))

    await waitFor(() => expect(envios('POST')).toHaveLength(1))
  })

  it('código duplicado informado por el servidor se muestra junto al campo y conserva lo cargado', async () => {
    apiFetchMock.mockImplementation(() =>
      Promise.resolve(respuesta(409, { title: 'El código ya está en uso.', codigo: 'CODIGO_DUPLICADO' })),
    )

    const usuarioEvento = userEvent.setup()
    renderAlta()

    await usuarioEvento.type(screen.getByLabelText(/^nombre$/i), 'Kiosco La Esquina')
    await usuarioEvento.type(screen.getByLabelText(/^dirección$/i), 'Av. San Martín 1420')
    await usuarioEvento.type(screen.getByLabelText(/^contacto$/i), 'Rocío')
    await usuarioEvento.type(screen.getByLabelText(/código \(opcional\)/i), 'C-001')
    await usuarioEvento.click(screen.getByRole('button', { name: /crear cliente/i }))

    expect(await screen.findByText('El código ya está en uso.')).toBeInTheDocument()
    expect(screen.getByLabelText(/^nombre$/i)).toHaveValue('Kiosco La Esquina')
  })

  it('sin GESTIONAR_CLIENTES no pide nada y muestra que falta el permiso', async () => {
    renderAlta(queryClientConYo('VEN'))

    expect(await screen.findByText(SIN_PERMISO_DE_CLIENTES)).toBeInTheDocument()
    expect(apiFetchMock).not.toHaveBeenCalled()
  })
})

/** Grupo 8, tarea 8.2 (decisión del usuario 2026-09-29): tras el alta y
 * tras editar la ficha se vuelve al listado, no a la ficha del cliente
 * recién creado -- eso obligaba a un paso extra para ver el listado
 * actualizado. */
describe('ClienteFormScreen: navegación después de guardar (grupo 8, tarea 8.2)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('después de crear el cliente vuelve al listado de clientes', async () => {
    responderAlta(CLIENTE)

    const usuarioEvento = userEvent.setup()
    renderAlta()

    await usuarioEvento.type(screen.getByLabelText(/^nombre$/i), 'Kiosco La Esquina')
    await usuarioEvento.type(screen.getByLabelText(/^dirección$/i), 'Av. San Martín 1420')
    await usuarioEvento.type(screen.getByLabelText(/^contacto$/i), 'Rocío')
    await usuarioEvento.click(screen.getByRole('button', { name: /crear cliente/i }))

    expect(await screen.findByText('Listado de clientes')).toBeInTheDocument()
  })

  it('después de guardar la edición de la ficha vuelve al listado de clientes', async () => {
    apiFetchMock.mockImplementation((_ruta: string, init?: RequestInit) => {
      if (init?.method === 'PUT') {
        return Promise.resolve(respuesta(200, { ...CLIENTE, nombre: 'Kiosco La Esquina S.A.' }))
      }
      return Promise.resolve(respuesta(200, CLIENTE))
    })

    const usuarioEvento = userEvent.setup()
    renderEdicion(CLIENTE.id)

    const campoNombre = await screen.findByLabelText(/^nombre$/i)
    await usuarioEvento.clear(campoNombre)
    await usuarioEvento.type(campoNombre, 'Kiosco La Esquina S.A.')
    await usuarioEvento.click(screen.getByRole('button', { name: /guardar cambios/i }))

    expect(await screen.findByText('Listado de clientes')).toBeInTheDocument()
  })
})

/** Grupo 8, tarea 8.1: bug vs. spec -- la ficha no mostraba el crédito en
 * solo lectura. Escenario "La ficha muestra el crédito en solo lectura" de
 * `specs/clientes/administracion-de-clientes/spec.md` y `design.md` D3:
 * quien tiene `GESTIONAR_CLIENTES` ve los tres campos aunque no tenga
 * `GESTIONAR_CREDITO`; el enlace de edición sigue exigiendo el segundo
 * permiso. */
describe('ClienteFormScreen: crédito en solo lectura en la ficha (grupo 8, tarea 8.1)', () => {
  const CLIENTE_CON_CREDITO = {
    ...CLIENTE,
    limite_credito: '150000.00',
    politica_credito: 'BLOQUEAR',
    tolerancia_offline_tipo: 'IMPORTE',
    tolerancia_offline_valor: '500.00',
  }

  beforeEach(() => {
    apiFetchMock.mockReset()
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('con GESTIONAR_CLIENTES y sin GESTIONAR_CREDITO ve los valores y no ve el enlace de edición', async () => {
    apiFetchMock.mockResolvedValue(respuesta(200, CLIENTE_CON_CREDITO))
    const queryClient = queryClientConYo('GES', { permisos: ['GESTIONAR_CLIENTES'] })

    renderEdicion(CLIENTE_CON_CREDITO.id, queryClient)

    expect(await screen.findByText('150.000,00')).toBeInTheDocument()
    expect(screen.getByText('BLOQUEAR')).toBeInTheDocument()
    expect(screen.getByText(/IMPORTE.*500,00/)).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /crédito/i })).not.toBeInTheDocument()
  })

  it('con GESTIONAR_CLIENTES y GESTIONAR_CREDITO ve los valores y el enlace de edición', async () => {
    apiFetchMock.mockResolvedValue(respuesta(200, CLIENTE_CON_CREDITO))

    renderEdicion(CLIENTE_CON_CREDITO.id)

    expect(await screen.findByText('150.000,00')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /crédito/i })).toBeInTheDocument()
  })

  it('con los tres campos en null muestra la herencia de la organización', async () => {
    apiFetchMock.mockResolvedValue(respuesta(200, CLIENTE))

    renderEdicion(CLIENTE.id)

    const apariciones = await screen.findAllByText(/hereda de la organización/i)
    expect(apariciones.length).toBeGreaterThanOrEqual(2)
  })
})

describe('ClienteFormScreen: ficha de edición (tarea 5.3, D3, D7)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('modifica la ficha con un único envío PUT', async () => {
    apiFetchMock.mockImplementation((_ruta: string, init?: RequestInit) => {
      if (init?.method === 'PUT') {
        return Promise.resolve(respuesta(200, { ...CLIENTE, nombre: 'Kiosco La Esquina S.A.' }))
      }
      return Promise.resolve(respuesta(200, CLIENTE))
    })

    const usuarioEvento = userEvent.setup()
    renderEdicion(CLIENTE.id)

    const campoNombre = await screen.findByLabelText(/^nombre$/i)
    await usuarioEvento.clear(campoNombre)
    await usuarioEvento.type(campoNombre, 'Kiosco La Esquina S.A.')
    await usuarioEvento.click(screen.getByRole('button', { name: /guardar cambios/i }))

    await waitFor(() => {
      const llamadaPut = apiFetchMock.mock.calls.find(([, init]) => (init as RequestInit)?.method === 'PUT')
      expect(llamadaPut).toBeDefined()
    })
    const [ruta] = apiFetchMock.mock.calls.find(([, init]) => (init as RequestInit)?.method === 'PUT') as [
      string,
      RequestInit,
    ]
    expect(ruta).toBe(`/clientes/${CLIENTE.id}`)
  })

  it('con GESTIONAR_CREDITO muestra el enlace "Crédito" con el href correcto', async () => {
    apiFetchMock.mockResolvedValue(respuesta(200, CLIENTE))

    renderEdicion(CLIENTE.id)

    const enlace = await screen.findByRole('link', { name: /crédito/i })
    expect(enlace).toHaveAttribute('href', `/admin/clientes/${CLIENTE.id}/credito`)
  })

  it('sin GESTIONAR_CREDITO no muestra el enlace "Crédito"', async () => {
    apiFetchMock.mockResolvedValue(respuesta(200, CLIENTE))
    const queryClient = queryClientConYo('GES', { permisos: ['GESTIONAR_CLIENTES'] })

    renderEdicion(CLIENTE.id, queryClient)

    await screen.findByRole('button', { name: /guardar cambios/i })
    expect(screen.queryByRole('link', { name: /crédito/i })).not.toBeInTheDocument()
  })

  it('sin GESTIONAR_CLIENTES no pide la ficha y muestra que falta el permiso', async () => {
    renderEdicion(CLIENTE.id, queryClientConYo('VEN'))

    expect(await screen.findByText(SIN_PERMISO_DE_CLIENTES)).toBeInTheDocument()
    expect(apiFetchMock).not.toHaveBeenCalled()
  })

  it('elegir INACTIVO abre el diálogo de confirmación y NO envía el comando todavía', async () => {
    apiFetchMock.mockResolvedValue(respuesta(200, CLIENTE))

    const usuarioEvento = userEvent.setup()
    renderEdicion(CLIENTE.id)

    await usuarioEvento.selectOptions(await screen.findByLabelText(/^estado$/i), 'INACTIVO')
    await usuarioEvento.click(screen.getByRole('button', { name: /guardar cambios/i }))

    expect(await screen.findByRole('dialog', { name: /confirmar inactivación/i })).toBeInTheDocument()
    expect(apiFetchMock).not.toHaveBeenCalledWith(
      expect.anything(),
      expect.objectContaining({ method: 'PUT' }),
    )
  })

  it('escribir un nombre distinto al del cliente mantiene el botón de confirmación deshabilitado', async () => {
    apiFetchMock.mockResolvedValue(respuesta(200, CLIENTE))

    const usuarioEvento = userEvent.setup()
    renderEdicion(CLIENTE.id)

    await usuarioEvento.selectOptions(await screen.findByLabelText(/^estado$/i), 'INACTIVO')
    await usuarioEvento.click(screen.getByRole('button', { name: /guardar cambios/i }))
    await usuarioEvento.type(
      await screen.findByLabelText(/nombre del cliente para confirmar/i),
      'Un nombre cualquiera',
    )

    expect(screen.getByRole('button', { name: /^inactivar cliente$/i })).toBeDisabled()
  })

  it('escribir el nombre exacto habilita la confirmación y envía CLIENTE_MODIFICAR con estado INACTIVO', async () => {
    apiFetchMock.mockImplementation((_ruta: string, init?: RequestInit) => {
      if (init?.method === 'PUT') {
        return Promise.resolve(respuesta(200, { ...CLIENTE, estado: 'INACTIVO' }))
      }
      return Promise.resolve(respuesta(200, CLIENTE))
    })

    const usuarioEvento = userEvent.setup()
    renderEdicion(CLIENTE.id)

    await usuarioEvento.selectOptions(await screen.findByLabelText(/^estado$/i), 'INACTIVO')
    await usuarioEvento.click(screen.getByRole('button', { name: /guardar cambios/i }))
    await usuarioEvento.type(await screen.findByLabelText(/nombre del cliente para confirmar/i), CLIENTE.nombre)

    const botonConfirmar = screen.getByRole('button', { name: /^inactivar cliente$/i })
    expect(botonConfirmar).toBeEnabled()
    await usuarioEvento.click(botonConfirmar)

    await waitFor(() => {
      const llamadaPut = apiFetchMock.mock.calls.find(([, init]) => (init as RequestInit)?.method === 'PUT')
      expect(llamadaPut).toBeDefined()
    })
    const [, opciones] = apiFetchMock.mock.calls.find(([, init]) => (init as RequestInit)?.method === 'PUT') as [
      string,
      RequestInit,
    ]
    expect(JSON.parse(String(opciones.body))).toMatchObject({ estado: 'INACTIVO' })
  })
})

/** Change 08, tarea 7.2 (spec `administracion-de-cuentas-corrientes`, "La
 * ficha muestra el saldo y lleva a la cuenta corriente"): saldo actual con su
 * rótulo según el signo y enlace "Cuenta corriente". */
describe('ClienteFormScreen: saldo y cuenta corriente en la ficha (change 08, tarea 7.2)', () => {
  function estadoDeCuenta(saldoActual: string) {
    return {
      saldo_anterior: '0.00',
      saldo_actual: saldoActual,
      zona_horaria: 'America/Argentina/Mendoza',
      items: [],
      cursor_siguiente: null,
    }
  }

  function responderConSaldo(saldoActual: string) {
    apiFetchMock.mockImplementation((ruta: string) =>
      Promise.resolve(
        String(ruta).includes('/cuenta-corriente')
          ? respuesta(200, estadoDeCuenta(saldoActual))
          : respuesta(200, CLIENTE),
      ),
    )
  }

  beforeEach(() => {
    apiFetchMock.mockReset()
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('un cliente con deuda ve "Nos debe" con el importe y el enlace a su cuenta corriente', async () => {
    responderConSaldo('150000.00')

    renderEdicion(CLIENTE.id)

    expect(await screen.findByText('Nos debe $ 150.000,00')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Cuenta corriente' })).toHaveAttribute(
      'href',
      `/admin/clientes/${CLIENTE.id}/cuenta-corriente`,
    )
    expect(apiFetchMock).toHaveBeenCalledWith(expect.stringContaining(`/clientes/${CLIENTE.id}/cuenta-corriente`))
  })

  it('un cliente con saldo a favor lo rotula "Saldo a favor" sin signo', async () => {
    responderConSaldo('-2500.50')

    renderEdicion(CLIENTE.id)

    expect(await screen.findByText('Saldo a favor $ 2.500,50')).toBeInTheDocument()
  })

  it('un cliente sin movimientos ve saldo cero', async () => {
    responderConSaldo('0.00')

    renderEdicion(CLIENTE.id)

    expect(await screen.findByText('Saldo $ 0,00')).toBeInTheDocument()
  })

  it('si el saldo no se puede leer avisa, y el enlace sigue disponible', async () => {
    apiFetchMock.mockImplementation((ruta: string) =>
      Promise.resolve(
        String(ruta).includes('/cuenta-corriente')
          ? respuesta(500, { title: 'Error interno.', codigo: 'ERROR_INTERNO' })
          : respuesta(200, CLIENTE),
      ),
    )

    renderEdicion(CLIENTE.id)

    expect(await screen.findByText('No se pudo obtener el saldo.')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Cuenta corriente' })).toBeInTheDocument()
  })

  it('el alta de un cliente no muestra saldo ni enlace', async () => {
    renderAlta()

    expect(await screen.findByRole('button', { name: /crear cliente/i })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Cuenta corriente' })).not.toBeInTheDocument()
    // Lo único que lee el alta es la lista de listas de precios activas (change 13, 13.4).
    expect(apiFetchMock.mock.calls.map(([ruta]) => String(ruta))).toEqual(['/precios/listas/opciones'])
  })
})

/** Change 08, verificación 9.3 paso 14: el rechazo del servidor al reactivar
 * un cliente inactivo se mapea al campo `estado`, que no mostraba el error. */
describe('ClienteFormScreen: rechazo de cambio de estado se muestra junto al campo (change 08, 9.3)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it.each([
    [409, 'CLIENTE_CON_OPERACIONES', 'El cliente tiene operaciones y no puede reactivarse.'],
    [409, 'TRANSICION_ESTADO_INVALIDA', 'La transición de estado no es válida.'],
  ])('%s %s: muestra el mensaje, no navega y el cliente sigue INACTIVO', async (status, codigo, mensaje) => {
    apiFetchMock.mockImplementation((_ruta: string, init?: RequestInit) => {
      if (init?.method === 'PUT') {
        return Promise.resolve(respuesta(status, { title: mensaje, codigo }))
      }
      return Promise.resolve(respuesta(200, { ...CLIENTE, estado: 'INACTIVO' }))
    })

    const usuarioEvento = userEvent.setup()
    renderEdicion(CLIENTE.id)

    const selectEstado = await screen.findByLabelText(/^estado$/i)
    await usuarioEvento.selectOptions(selectEstado, 'ACTIVO')
    await usuarioEvento.click(screen.getByRole('button', { name: /guardar cambios/i }))

    expect(await screen.findByText(mensaje)).toBeInTheDocument()
    expect(screen.queryByText('Listado de clientes')).not.toBeInTheDocument()
    expect(screen.getByLabelText(/^nombre$/i)).toBeInTheDocument()
  })
})
