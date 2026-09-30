import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }))
vi.mock('../../../../../src/lib/api/httpClient', () => ({ apiFetch: apiFetchMock }))

import { SaldoInicialScreen } from '../../../../../src/areas/admin/cuentas-corrientes/SaldoInicialScreen'
import { queryClientConYo } from '../../../utils/permisosDePrueba'

function respuesta(status: number, cuerpo: unknown) {
  return { ok: status >= 200 && status < 300, status, json: async () => cuerpo }
}

const ENTIDAD_ID = '11111111-1111-4111-8111-111111111111'
const ACEPTADO = { movimiento_id: '22222222-2222-4222-8222-222222222222', saldo: '150000.00' }
const SIN_PERMISO = 'No tenés permiso para registrar saldos iniciales.'
const AVISO_SIN_CONEXION = 'Se necesita conexión para completar esta operación. Probá de nuevo cuando tengas conexión.'

function renderFormulario(
  cuentaTipo: 'CLIENTE' | 'PROVEEDOR' = 'CLIENTE',
  queryClient: QueryClient = queryClientConYo('ADM'),
) {
  const coleccion = cuentaTipo === 'CLIENTE' ? 'clientes' : 'proveedores'
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[`/admin/${coleccion}/${ENTIDAD_ID}/cuenta-corriente/saldo-inicial`]}>
        <Routes>
          <Route
            path={`/admin/${coleccion}/:entidadId/cuenta-corriente/saldo-inicial`}
            element={<SaldoInicialScreen cuentaTipo={cuentaTipo} />}
          />
          <Route path={`/admin/${coleccion}/:entidadId/cuenta-corriente`} element={<p>Estado de cuenta</p>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

function operationIdDeLaLlamada(indice: number): string | null {
  const [, opciones] = apiFetchMock.mock.calls[indice] as [string, RequestInit]
  return new Headers(opciones.headers).get('Operation-Id')
}

function cuerpoDeLaLlamada(indice: number): unknown {
  const [, opciones] = apiFetchMock.mock.calls[indice] as [string, RequestInit]
  return JSON.parse(String(opciones.body))
}

describe('SaldoInicialScreen: registrar (tarea 7.4, D1, D5)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('un cliente con "Nos debe" envía SALDO_INICIAL_REGISTRAR con el importe como string y vuelve a la cuenta', async () => {
    apiFetchMock.mockResolvedValueOnce(respuesta(201, ACEPTADO))
    const usuarioEvento = userEvent.setup()
    renderFormulario()

    await usuarioEvento.type(screen.getByLabelText('Importe'), '150000.00')
    await usuarioEvento.click(screen.getByLabelText('Nos debe'))
    await usuarioEvento.click(screen.getByRole('button', { name: 'Registrar saldo inicial' }))

    expect(await screen.findByText('Estado de cuenta')).toBeInTheDocument()
    expect(apiFetchMock).toHaveBeenCalledTimes(1)
    const [ruta, opciones] = apiFetchMock.mock.calls[0] as [string, RequestInit]
    expect(ruta).toBe('/cuentas-corrientes/saldos-iniciales')
    expect(opciones.method).toBe('POST')
    expect(operationIdDeLaLlamada(0)).toBeTruthy()
    expect(cuerpoDeLaLlamada(0)).toEqual({
      cuenta_tipo: 'CLIENTE',
      entidad_id: ENTIDAD_ID,
      importe: '150000.00',
      sentido: 'AUMENTA',
    })
  })

  it('un cliente con saldo a favor envía REDUCE', async () => {
    apiFetchMock.mockResolvedValueOnce(respuesta(201, ACEPTADO))
    const usuarioEvento = userEvent.setup()
    renderFormulario()

    await usuarioEvento.type(screen.getByLabelText('Importe'), '2500.5')
    await usuarioEvento.click(screen.getByLabelText('Saldo a favor del cliente'))
    await usuarioEvento.click(screen.getByRole('button', { name: 'Registrar saldo inicial' }))

    await screen.findByText('Estado de cuenta')
    expect(cuerpoDeLaLlamada(0)).toMatchObject({ importe: '2500.5', sentido: 'REDUCE' })
  })

  it('un proveedor usa sus rótulos y su tipo de cuenta', async () => {
    apiFetchMock.mockResolvedValueOnce(respuesta(201, ACEPTADO))
    const usuarioEvento = userEvent.setup()
    renderFormulario('PROVEEDOR')

    expect(screen.queryByLabelText('Nos debe')).not.toBeInTheDocument()
    await usuarioEvento.type(screen.getByLabelText('Importe'), '9000')
    await usuarioEvento.click(screen.getByLabelText('Saldo a favor nuestro'))
    await usuarioEvento.click(screen.getByRole('button', { name: 'Registrar saldo inicial' }))

    await screen.findByText('Estado de cuenta')
    expect(screen.queryByLabelText('Le debemos')).not.toBeInTheDocument()
    expect(cuerpoDeLaLlamada(0)).toEqual({
      cuenta_tipo: 'PROVEEDOR',
      entidad_id: ENTIDAD_ID,
      importe: '9000',
      sentido: 'REDUCE',
    })
  })

  it('un proveedor puede elegir "Le debemos"', () => {
    renderFormulario('PROVEEDOR')

    expect(screen.getByLabelText('Le debemos')).toBeChecked()
  })

  it('un importe inválido se rechaza junto al campo y no envía nada', async () => {
    const usuarioEvento = userEvent.setup()
    renderFormulario()

    await usuarioEvento.type(screen.getByLabelText('Importe'), '0')
    await usuarioEvento.click(screen.getByRole('button', { name: 'Registrar saldo inicial' }))

    expect(await screen.findByText('Ingresá un importe mayor a cero, con hasta dos decimales.')).toBeInTheDocument()
    expect(apiFetchMock).not.toHaveBeenCalled()
  })

  it('avisa que requiere conexión y que no se encola', () => {
    renderFormulario()

    expect(screen.getByText(/requiere conexión/i)).toBeInTheDocument()
    expect(screen.getByText(/no se guarda para enviar después/i)).toBeInTheDocument()
  })
})

describe('SaldoInicialScreen: reintento y rechazo (tarea 7.4, INV-06, TR-07)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('tras un corte de red avisa la falta de conexión y el reintento del mismo dato reutiliza el operation_id', async () => {
    apiFetchMock.mockRejectedValue(new TypeError('Failed to fetch'))
    const usuarioEvento = userEvent.setup()
    renderFormulario()

    await usuarioEvento.type(screen.getByLabelText('Importe'), '150000.00')
    await usuarioEvento.click(screen.getByRole('button', { name: 'Registrar saldo inicial' }))

    expect(await screen.findByText(AVISO_SIN_CONEXION)).toBeInTheDocument()
    const llamadasDelPrimerEnvio = apiFetchMock.mock.calls.length
    const idDelPrimerEnvio = operationIdDeLaLlamada(0)
    expect(idDelPrimerEnvio).toBeTruthy()

    apiFetchMock.mockReset()
    apiFetchMock.mockResolvedValueOnce(respuesta(201, ACEPTADO))
    await usuarioEvento.click(screen.getByRole('button', { name: 'Registrar saldo inicial' }))

    await screen.findByText('Estado de cuenta')
    expect(llamadasDelPrimerEnvio).toBeGreaterThanOrEqual(1)
    expect(apiFetchMock).toHaveBeenCalledTimes(1)
    expect(operationIdDeLaLlamada(0)).toBe(idDelPrimerEnvio)
  })

  it('si el usuario cambia el importe después del corte, el envío lleva un operation_id nuevo', async () => {
    apiFetchMock.mockRejectedValue(new TypeError('Failed to fetch'))
    const usuarioEvento = userEvent.setup()
    renderFormulario()

    await usuarioEvento.type(screen.getByLabelText('Importe'), '150000.00')
    await usuarioEvento.click(screen.getByRole('button', { name: 'Registrar saldo inicial' }))
    await screen.findByText(AVISO_SIN_CONEXION)
    const idDelPrimerEnvio = operationIdDeLaLlamada(0)

    apiFetchMock.mockReset()
    apiFetchMock.mockResolvedValueOnce(respuesta(201, ACEPTADO))
    const importe = screen.getByLabelText('Importe')
    await usuarioEvento.clear(importe)
    await usuarioEvento.type(importe, '99.00')
    await usuarioEvento.click(screen.getByRole('button', { name: 'Registrar saldo inicial' }))

    await screen.findByText('Estado de cuenta')
    expect(operationIdDeLaLlamada(0)).toBeTruthy()
    expect(operationIdDeLaLlamada(0)).not.toBe(idDelPrimerEnvio)
  })

  it('un rechazo del servidor muestra su mensaje, conserva lo cargado y no reintenta', async () => {
    apiFetchMock.mockResolvedValue(
      respuesta(409, {
        title: 'La cuenta ya tiene operaciones: no admite un saldo inicial.',
        codigo: 'CUENTA_CON_OPERACIONES',
      }),
    )
    const usuarioEvento = userEvent.setup()
    renderFormulario()

    await usuarioEvento.type(screen.getByLabelText('Importe'), '150000.00')
    await usuarioEvento.click(screen.getByRole('button', { name: 'Registrar saldo inicial' }))

    expect(
      await screen.findByText('La cuenta ya tiene operaciones: no admite un saldo inicial.'),
    ).toBeInTheDocument()
    expect(apiFetchMock).toHaveBeenCalledTimes(1)
    expect(screen.getByLabelText('Importe')).toHaveValue('150000.00')
    expect(screen.queryByText('Estado de cuenta')).not.toBeInTheDocument()
  })

  it('tras un rechazo del servidor, reenviar lo mismo es una operación nueva', async () => {
    apiFetchMock.mockResolvedValue(
      respuesta(409, { title: 'La cuenta ya tiene operaciones.', codigo: 'CUENTA_CON_OPERACIONES' }),
    )
    const usuarioEvento = userEvent.setup()
    renderFormulario()

    await usuarioEvento.type(screen.getByLabelText('Importe'), '150000.00')
    await usuarioEvento.click(screen.getByRole('button', { name: 'Registrar saldo inicial' }))
    await screen.findByText('La cuenta ya tiene operaciones.')
    await usuarioEvento.click(screen.getByRole('button', { name: 'Registrar saldo inicial' }))
    await waitFor(() => expect(apiFetchMock).toHaveBeenCalledTimes(2))

    expect(operationIdDeLaLlamada(1)).not.toBe(operationIdDeLaLlamada(0))
  })
})

describe('SaldoInicialScreen: permiso (tarea 7.4, D1, ADR-027)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
  })

  it('sin IMPORTAR_DATOS avisa la falta de permiso, no monta el formulario y no envía nada', async () => {
    renderFormulario('CLIENTE', queryClientConYo('GES'))

    expect(await screen.findByText(SIN_PERMISO)).toBeInTheDocument()
    expect(screen.queryByLabelText('Importe')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Registrar saldo inicial' })).not.toBeInTheDocument()
    expect(apiFetchMock).not.toHaveBeenCalled()
  })

  it('un rol de solo lectura de la cuenta tampoco lo ve', async () => {
    renderFormulario('PROVEEDOR', queryClientConYo('SUP'))

    expect(await screen.findByText(SIN_PERMISO)).toBeInTheDocument()
  })
})
