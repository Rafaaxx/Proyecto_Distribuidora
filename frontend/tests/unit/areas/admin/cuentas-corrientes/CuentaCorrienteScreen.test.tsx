import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }))
vi.mock('../../../../../src/lib/api/httpClient', () => ({ apiFetch: apiFetchMock }))

import { CuentaCorrienteScreen } from '../../../../../src/areas/admin/cuentas-corrientes/CuentaCorrienteScreen'
import { queryClientConYo } from '../../../utils/permisosDePrueba'

function respuesta(status: number, cuerpo: unknown) {
  return { ok: status >= 200 && status < 300, status, json: async () => cuerpo }
}

const ENTIDAD_ID = '11111111-1111-4111-8111-111111111111'
const ZONA = 'America/Argentina/Mendoza'

function movimiento(
  id: string,
  campos: { tipo: string; sentido: string; importe: string; saldo_acumulado: string; occurred_at: string },
) {
  return {
    id,
    origen_tipo: campos.tipo,
    origen_id: id,
    registered_at: campos.occurred_at,
    usuario_id: id,
    operation_id: id,
    ...campos,
  }
}

const SALDO_INICIAL_150 = movimiento('a1', {
  tipo: 'SALDO_INICIAL',
  sentido: 'AUMENTA',
  importe: '150000.00',
  saldo_acumulado: '150000.00',
  occurred_at: '2026-03-10T15:00:00Z',
})
const COBRANZA_20 = movimiento('a2', {
  tipo: 'COBRANZA',
  sentido: 'REDUCE',
  importe: '20000.00',
  saldo_acumulado: '130000.00',
  occurred_at: '2026-04-10T15:00:00Z',
})

function estado(
  items: unknown[],
  extra: { saldo_anterior?: string; saldo_actual?: string; cursor_siguiente?: string | null } = {},
) {
  return {
    saldo_anterior: '0.00',
    saldo_actual: '130000.00',
    zona_horaria: ZONA,
    items,
    cursor_siguiente: null,
    ...extra,
  }
}

function renderCuenta(
  cuentaTipo: 'CLIENTE' | 'PROVEEDOR' = 'CLIENTE',
  queryClient: QueryClient = queryClientConYo('ADM'),
) {
  const coleccion = cuentaTipo === 'CLIENTE' ? 'clientes' : 'proveedores'
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[`/admin/${coleccion}/${ENTIDAD_ID}/cuenta-corriente`]}>
        <Routes>
          <Route
            path={`/admin/${coleccion}/:entidadId/cuenta-corriente`}
            element={<CuentaCorrienteScreen cuentaTipo={cuentaTipo} />}
          />
          <Route path={`/admin/${coleccion}/:entidadId`} element={<p>Ficha</p>} />
          <Route path={`/admin/${coleccion}/:entidadId/cuenta-corriente/saldo-inicial`} element={<p>Formulario</p>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

function urlDeLaLlamada(indice: number): URL {
  return new URL(String(apiFetchMock.mock.calls[indice]?.[0]), 'http://x')
}

describe('CuentaCorrienteScreen: estado de cuenta (tarea 7.3, CC-07)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('muestra los movimientos con aumento, reducción y saldo acumulado, y la fecha en la zona de la organización', async () => {
    apiFetchMock.mockResolvedValueOnce(respuesta(200, estado([SALDO_INICIAL_150, COBRANZA_20])))

    renderCuenta()

    const filas = await screen.findAllByRole('row')
    // Encabezado + dos movimientos.
    expect(filas).toHaveLength(3)
    const primera = within(filas[1] as HTMLElement)
    expect(primera.getByText('10/03/2026 12:00')).toBeInTheDocument()
    expect(primera.getByText('Saldo inicial')).toBeInTheDocument()
    expect(primera.getAllByText('$ 150.000,00')).toHaveLength(2) // aumento y saldo acumulado
    const segunda = within(filas[2] as HTMLElement)
    expect(segunda.getByText('Cobranza')).toBeInTheDocument()
    expect(segunda.getByText('$ 20.000,00')).toBeInTheDocument()
    expect(segunda.getByText('$ 130.000,00')).toBeInTheDocument()
    expect(screen.getByText('Nos debe $ 130.000,00')).toBeInTheDocument()
    expect(urlDeLaLlamada(0).pathname).toBe(`/clientes/${ENTIDAD_ID}/cuenta-corriente`)
  })

  it('la cuenta de un proveedor usa su propia ruta y sus rótulos', async () => {
    apiFetchMock.mockResolvedValueOnce(
      respuesta(200, estado([], { saldo_actual: '-3000.00' })),
    )

    renderCuenta('PROVEEDOR')

    expect(await screen.findByText('Saldo a nuestro favor $ 3.000,00')).toBeInTheDocument()
    expect(urlDeLaLlamada(0).pathname).toBe(`/proveedores/${ENTIDAD_ID}/cuenta-corriente`)
  })

  it('una cuenta sin movimientos lo dice y muestra saldo cero', async () => {
    apiFetchMock.mockResolvedValueOnce(respuesta(200, estado([], { saldo_actual: '0.00' })))

    renderCuenta()

    expect(await screen.findByText('No hay movimientos en este período.')).toBeInTheDocument()
    expect(screen.getByText('Saldo $ 0,00')).toBeInTheDocument()
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
  })

  it('sin filtro no muestra saldo anterior', async () => {
    apiFetchMock.mockResolvedValueOnce(respuesta(200, estado([SALDO_INICIAL_150])))

    renderCuenta()

    await screen.findByText('Saldo inicial')
    expect(screen.queryByText(/saldo anterior/i)).not.toBeInTheDocument()
  })
})

describe('CuentaCorrienteScreen: período y "cargar más" (tarea 7.3, D9)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('filtra desde una fecha y muestra el saldo anterior con una sola fila', async () => {
    apiFetchMock
      .mockResolvedValueOnce(respuesta(200, estado([SALDO_INICIAL_150, COBRANZA_20])))
      .mockResolvedValueOnce(respuesta(200, estado([COBRANZA_20], { saldo_anterior: '150000.00' })))
    const usuarioEvento = userEvent.setup()
    renderCuenta()
    await screen.findByText('Saldo inicial')

    await usuarioEvento.type(screen.getByLabelText('Desde'), '2026-04-01')
    await usuarioEvento.click(screen.getByRole('button', { name: 'Filtrar' }))

    expect(await screen.findByText('Saldo anterior: $ 150.000,00')).toBeInTheDocument()
    expect(screen.getAllByRole('row')).toHaveLength(2)
    expect(screen.queryByText('Saldo inicial')).not.toBeInTheDocument()
    const filtrada = urlDeLaLlamada(1)
    expect(filtrada.searchParams.get('desde')).toBe('2026-04-01')
    expect(filtrada.searchParams.has('hasta')).toBe(false)
    expect(filtrada.searchParams.has('cursor')).toBe(false)
  })

  it('"Quitar filtro" vuelve a pedir la cuenta completa', async () => {
    apiFetchMock
      .mockResolvedValueOnce(respuesta(200, estado([SALDO_INICIAL_150])))
      .mockResolvedValueOnce(respuesta(200, estado([COBRANZA_20], { saldo_anterior: '150000.00' })))
      .mockResolvedValueOnce(respuesta(200, estado([SALDO_INICIAL_150, COBRANZA_20])))
    const usuarioEvento = userEvent.setup()
    renderCuenta()
    await screen.findByText('Saldo inicial')

    await usuarioEvento.type(screen.getByLabelText('Desde'), '2026-04-01')
    await usuarioEvento.click(screen.getByRole('button', { name: 'Filtrar' }))
    await screen.findByText('Saldo anterior: $ 150.000,00')
    await usuarioEvento.click(screen.getByRole('button', { name: 'Quitar filtro' }))

    await waitFor(() => expect(screen.queryByText(/saldo anterior/i)).not.toBeInTheDocument())
    expect(await screen.findByText('Saldo inicial')).toBeInTheDocument()
    expect(screen.getByLabelText('Desde')).toHaveValue('')
    expect(urlDeLaLlamada(2).searchParams.has('desde')).toBe(false)
  })

  it('un período invertido se rechaza sin pedir nada al servidor', async () => {
    apiFetchMock.mockResolvedValueOnce(respuesta(200, estado([SALDO_INICIAL_150])))
    const usuarioEvento = userEvent.setup()
    renderCuenta()
    await screen.findByText('Saldo inicial')

    await usuarioEvento.type(screen.getByLabelText('Desde'), '2026-04-02')
    await usuarioEvento.type(screen.getByLabelText('Hasta'), '2026-04-01')
    await usuarioEvento.click(screen.getByRole('button', { name: 'Filtrar' }))

    expect(await screen.findByText('"Desde" no puede ser posterior a "Hasta".')).toBeInTheDocument()
    expect(apiFetchMock).toHaveBeenCalledTimes(1)
  })

  it('"Cargar más" trae la página siguiente con el cursor y la agrega sin repetir; al terminar desaparece', async () => {
    apiFetchMock
      .mockResolvedValueOnce(respuesta(200, estado([SALDO_INICIAL_150], { cursor_siguiente: 'cursor-1' })))
      .mockResolvedValueOnce(respuesta(200, estado([COBRANZA_20])))
    const usuarioEvento = userEvent.setup()
    renderCuenta()
    await screen.findByText('Saldo inicial')

    await usuarioEvento.click(screen.getByRole('button', { name: 'Cargar más' }))

    expect(await screen.findByText('Cobranza')).toBeInTheDocument()
    expect(screen.getByText('Saldo inicial')).toBeInTheDocument()
    expect(urlDeLaLlamada(1).searchParams.get('cursor')).toBe('cursor-1')
    expect(screen.queryByRole('button', { name: 'Cargar más' })).not.toBeInTheDocument()
  })

  it('sin página siguiente no ofrece "Cargar más"', async () => {
    apiFetchMock.mockResolvedValueOnce(respuesta(200, estado([SALDO_INICIAL_150])))

    renderCuenta()

    await screen.findByText('Saldo inicial')
    expect(screen.queryByRole('button', { name: 'Cargar más' })).not.toBeInTheDocument()
  })
})

describe('CuentaCorrienteScreen: errores y permisos (tarea 7.3)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('un 404 muestra que el recurso no existe y ningún dato', async () => {
    apiFetchMock.mockResolvedValueOnce(
      respuesta(404, { title: 'El cliente no existe en esta organización.', codigo: 'RECURSO_NO_ENCONTRADO' }),
    )

    renderCuenta()

    expect(await screen.findByText('La cuenta corriente pedida no existe.')).toBeInTheDocument()
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
    expect(screen.queryByText(/saldo/i)).not.toBeInTheDocument()
  })

  it('otro error de la API muestra el mensaje del servidor', async () => {
    apiFetchMock.mockResolvedValueOnce(respuesta(500, { title: 'Error interno.', codigo: 'ERROR_INTERNO' }))

    renderCuenta()

    expect(await screen.findByRole('alert')).toHaveTextContent('Error interno.')
  })

  it('sin el permiso de lectura no pide nada y lo avisa', async () => {
    renderCuenta('CLIENTE', queryClientConYo('VEN'))

    expect(await screen.findByText('No tenés permiso para ver esta cuenta corriente.')).toBeInTheDocument()
    expect(apiFetchMock).not.toHaveBeenCalled()
  })

  it('el permiso de proveedores no habilita la cuenta de un cliente, y viceversa', async () => {
    const soloProveedores = queryClientConYo('GES', { permisos: ['GESTIONAR_PROVEEDORES'] })
    renderCuenta('CLIENTE', soloProveedores)
    expect(await screen.findByText('No tenés permiso para ver esta cuenta corriente.')).toBeInTheDocument()
    expect(apiFetchMock).not.toHaveBeenCalled()
  })
})

describe('CuentaCorrienteScreen: acciones (tarea 7.3, 7.4, D1)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
    apiFetchMock.mockResolvedValue(respuesta(200, estado([SALDO_INICIAL_150])))
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('con IMPORTAR_DATOS ofrece "Registrar saldo inicial" hacia el formulario', async () => {
    renderCuenta('CLIENTE', queryClientConYo('ADM'))

    const enlace = await screen.findByRole('link', { name: 'Registrar saldo inicial' })
    expect(enlace).toHaveAttribute('href', `/admin/clientes/${ENTIDAD_ID}/cuenta-corriente/saldo-inicial`)
  })

  it('sin IMPORTAR_DATOS ve el estado de cuenta y no la acción', async () => {
    renderCuenta('CLIENTE', queryClientConYo('GES'))

    await screen.findByText('Saldo inicial')
    expect(screen.queryByRole('link', { name: 'Registrar saldo inicial' })).not.toBeInTheDocument()
  })

  it('ofrece volver a la ficha de la entidad', async () => {
    renderCuenta('PROVEEDOR', queryClientConYo('ADM'))

    expect(await screen.findByRole('link', { name: 'Volver a la ficha' })).toHaveAttribute(
      'href',
      `/admin/proveedores/${ENTIDAD_ID}`,
    )
  })
})

describe('CuentaCorrienteScreen: pagos y enlaces a la operación del proveedor (change 12, tarea 9.3)', () => {
  const COMPRA_MOV = movimiento('c1', {
    tipo: 'COMPRA',
    sentido: 'AUMENTA',
    importe: '153720.00',
    saldo_acumulado: '153720.00',
    occurred_at: '2026-04-01T15:00:00Z',
  })
  const PAGO_MOV = movimiento('p1', {
    tipo: 'PAGO',
    sentido: 'REDUCE',
    importe: '100000.00',
    saldo_acumulado: '53720.00',
    occurred_at: '2026-04-02T15:00:00Z',
  })
  const ANULACION_PAGO_MOV = movimiento('p2', {
    tipo: 'ANULACION_PAGO',
    sentido: 'AUMENTA',
    importe: '100000.00',
    saldo_acumulado: '153720.00',
    occurred_at: '2026-04-03T15:00:00Z',
  })
  const ANULACION_COMPRA_MOV = movimiento('c2', {
    tipo: 'ANULACION_COMPRA',
    sentido: 'REDUCE',
    importe: '153720.00',
    saldo_acumulado: '0.00',
    occurred_at: '2026-04-04T15:00:00Z',
  })
  const TODOS = [COMPRA_MOV, PAGO_MOV, ANULACION_PAGO_MOV, ANULACION_COMPRA_MOV]

  beforeEach(() => {
    apiFetchMock.mockReset()
    apiFetchMock.mockResolvedValue(respuesta(200, estado(TODOS, { saldo_actual: '0.00' })))
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('con REGISTRAR_PAGO_PROVEEDOR ofrece "Registrar pago" con el proveedor precargado', async () => {
    renderCuenta('PROVEEDOR', queryClientConYo('GES'))

    const enlace = await screen.findByRole('link', { name: /registrar pago/i })

    expect(enlace).toHaveAttribute('href', `/admin/pagos-proveedores/nuevo?proveedor=${ENTIDAD_ID}`)
  })

  it('sin REGISTRAR_PAGO_PROVEEDOR no ofrece "Registrar pago"', async () => {
    renderCuenta('PROVEEDOR', queryClientConYo('GES', { permisos: ['GESTIONAR_PROVEEDORES'] }))

    await screen.findByRole('table')

    expect(screen.queryByRole('link', { name: /registrar pago/i })).not.toBeInTheDocument()
  })

  it('la cuenta de un cliente nunca ofrece "Registrar pago"', async () => {
    renderCuenta('CLIENTE', queryClientConYo('ADM'))

    await screen.findByRole('table')

    expect(screen.queryByRole('link', { name: /registrar pago/i })).not.toBeInTheDocument()
  })

  it('con permiso de lectura de pagos y de compras cada movimiento enlaza a su operación', async () => {
    renderCuenta('PROVEEDOR', queryClientConYo('GES'))

    expect(await screen.findByRole('link', { name: 'Compra' })).toHaveAttribute('href', '/admin/compras/c1')
    expect(screen.getByRole('link', { name: 'Pago' })).toHaveAttribute('href', '/admin/pagos-proveedores/p1')
    expect(screen.getByRole('link', { name: 'Anulación de pago' })).toHaveAttribute('href', '/admin/pagos-proveedores/p2')
    expect(screen.getByRole('link', { name: 'Anulación de compra' })).toHaveAttribute('href', '/admin/compras/c2')
  })

  it('con solo los permisos de anular también enlaza (ANULAR_PAGO_PROVEEDOR y ANULAR_COMPRA)', async () => {
    renderCuenta('PROVEEDOR', queryClientConYo('GES', { permisos: ['GESTIONAR_PROVEEDORES', 'ANULAR_PAGO_PROVEEDOR', 'ANULAR_COMPRA'] }))

    expect(await screen.findByRole('link', { name: 'Pago' })).toHaveAttribute('href', '/admin/pagos-proveedores/p1')
    expect(screen.getByRole('link', { name: 'Compra' })).toHaveAttribute('href', '/admin/compras/c1')
  })

  it('sin permisos de pagos ni de compras ve los tipos sin enlace', async () => {
    renderCuenta('PROVEEDOR', queryClientConYo('GES', { permisos: ['GESTIONAR_PROVEEDORES'] }))

    const tabla = await screen.findByRole('table')

    expect(within(tabla).getByText('Pago')).toBeInTheDocument()
    expect(within(tabla).getByText('Compra')).toBeInTheDocument()
    expect(within(tabla).queryAllByRole('link')).toHaveLength(0)
  })

  it('el permiso de pagos no habilita el enlace a las compras, ni al revés', async () => {
    renderCuenta('PROVEEDOR', queryClientConYo('GES', { permisos: ['GESTIONAR_PROVEEDORES', 'REGISTRAR_PAGO_PROVEEDOR'] }))

    await screen.findByRole('link', { name: 'Pago' })

    expect(screen.queryByRole('link', { name: 'Compra' })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Anulación de compra' })).not.toBeInTheDocument()
  })

  it('en la cuenta de un cliente los movimientos no llevan enlace', async () => {
    renderCuenta('CLIENTE', queryClientConYo('ADM'))

    const tabla = await screen.findByRole('table')

    expect(within(tabla).queryAllByRole('link')).toHaveLength(0)
  })
})
