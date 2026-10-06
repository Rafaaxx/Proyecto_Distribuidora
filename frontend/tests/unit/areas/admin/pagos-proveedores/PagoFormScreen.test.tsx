import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }))
vi.mock('../../../../../src/lib/api/httpClient', () => ({ apiFetch: apiFetchMock }))

import { PagoFormScreen } from '../../../../../src/areas/admin/pagos-proveedores/PagoFormScreen'
import { llamadas, type ReglaDeApi } from '../../../utils/enrutarApi'
import { queryClientConYo } from '../../../utils/permisosDePrueba'
import {
  EFECTIVO_ID,
  PAGO_ID,
  PAGO_REGISTRADO,
  PROVEEDOR_ID,
  PROVEEDOR_NORTE_ID,
  TRANSFERENCIA_ID,
  fechaDeHoyParaPruebas,
  montarApi,
} from './pagosDePrueba'

function renderPantalla(rol: 'GES' | 'VEN' = 'GES', ruta = '/admin/pagos-proveedores/nuevo', permisos?: string[]) {
  const cliente = permisos ? queryClientConYo(rol, { permisos } as never) : queryClientConYo(rol)
  return render(
    <QueryClientProvider client={cliente}>
      <MemoryRouter initialEntries={[ruta]}>
        <Routes>
          <Route path="/admin/pagos-proveedores/nuevo" element={<PagoFormScreen />} />
          <Route path="/admin/pagos-proveedores" element={<p>Listado de pagos</p>} />
          <Route path="/admin/pagos-proveedores/:pagoId" element={<p>Detalle del pago</p>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

type Usuario = ReturnType<typeof userEvent.setup>

async function elegirProveedor(usuario: Usuario) {
  await screen.findByRole('option', { name: 'Bodega Sur' })
  await usuario.selectOptions(screen.getByLabelText(/^proveedor$/i), PROVEEDOR_ID)
}

async function tipearImporte(usuario: Usuario, importe: string) {
  await usuario.clear(screen.getByLabelText(/^importe$/i))
  await usuario.type(screen.getByLabelText(/^importe$/i), importe)
}

/** Carga el primer medio: efectivo por `importe`. */
async function cargarEfectivo(usuario: Usuario, importe: string) {
  await screen.findByRole('option', { name: 'Efectivo' })
  await usuario.selectOptions(screen.getAllByLabelText(/^medio de pago$/i)[0] as HTMLElement, EFECTIVO_ID)
  await usuario.clear(screen.getAllByLabelText(/^importe del medio$/i)[0] as HTMLElement)
  await usuario.type(screen.getAllByLabelText(/^importe del medio$/i)[0] as HTMLElement, importe)
}

function cuerpoDelPost(indice = 0): Record<string, unknown> {
  const llamada = llamadas(apiFetchMock, 'POST', '/pagos-proveedores')[indice]
  return JSON.parse(String(llamada?.init.body)) as Record<string, unknown>
}

describe('PagoFormScreen (tarea 9.1)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
  })
  afterEach(() => {
    vi.clearAllMocks()
  })

  it('sin REGISTRAR_PAGO_PROVEEDOR muestra la falta de permiso y no pide nada', async () => {
    montarApi(apiFetchMock)
    renderPantalla('VEN')

    expect(await screen.findByText(/no ten[eé]s permiso para registrar pagos/i)).toBeInTheDocument()
    expect(llamadas(apiFetchMock, 'GET', '/proveedores/opciones')).toHaveLength(0)
  })

  it('con solo ANULAR_PAGO_PROVEEDOR tampoco se puede registrar', async () => {
    montarApi(apiFetchMock)
    renderPantalla('GES', '/admin/pagos-proveedores/nuevo', ['ANULAR_PAGO_PROVEEDOR'])

    expect(await screen.findByText(/no ten[eé]s permiso para registrar pagos/i)).toBeInTheDocument()
  })

  it('la fecha viene con hoy por defecto y avisa que hace falta conexión', async () => {
    montarApi(apiFetchMock)
    renderPantalla()

    expect(await screen.findByLabelText(/fecha del pago/i)).toHaveValue(fechaDeHoyParaPruebas())
    expect(screen.getByText(/requiere conexi[oó]n/i)).toBeInTheDocument()
  })

  it('muestra el saldo actual y el resultante al tipear el importe (PAG-02)', async () => {
    montarApi(apiFetchMock)
    const usuario = userEvent.setup()
    renderPantalla()

    await elegirProveedor(usuario)
    expect(await screen.findByTestId('saldo-actual')).toHaveTextContent('Le debemos $ 153.720,00')
    await tipearImporte(usuario, '100000')

    expect(screen.getByTestId('saldo-resultante')).toHaveTextContent('Saldo después del pago: Le debemos $ 53.720,00')
  })

  it('un proveedor con saldo a nuestro favor lo rotula "Saldo a nuestro favor"', async () => {
    montarApi(apiFetchMock, [], '-1000.00')
    const usuario = userEvent.setup()
    renderPantalla()

    await elegirProveedor(usuario)

    expect(await screen.findByTestId('saldo-actual')).toHaveTextContent('Saldo a nuestro favor $ 1.000,00')
  })

  it('con faltante de medios muestra "Faltan" y deja el botón deshabilitado; al completar se habilita', async () => {
    montarApi(apiFetchMock)
    const usuario = userEvent.setup()
    renderPantalla()
    await elegirProveedor(usuario)
    await tipearImporte(usuario, '152460')

    await cargarEfectivo(usuario, '100000')

    expect(screen.getByTestId('diferencia-medios')).toHaveTextContent('Faltan $ 52.460,00')
    expect(screen.getByRole('button', { name: /confirmar pago/i })).toBeDisabled()

    await usuario.clear(screen.getAllByLabelText(/^importe del medio$/i)[0] as HTMLElement)
    await usuario.type(screen.getAllByLabelText(/^importe del medio$/i)[0] as HTMLElement, '152460')

    expect(screen.getByTestId('diferencia-medios')).toHaveTextContent('Los medios suman el importe.')
    expect(screen.getByRole('button', { name: /confirmar pago/i })).toBeEnabled()
  })

  it('con sobrante muestra "Sobran" y no deja confirmar', async () => {
    montarApi(apiFetchMock)
    const usuario = userEvent.setup()
    renderPantalla()
    await elegirProveedor(usuario)
    await tipearImporte(usuario, '152460')

    await cargarEfectivo(usuario, '152640')

    expect(screen.getByTestId('diferencia-medios')).toHaveTextContent('Sobran $ 180,00')
    expect(screen.getByRole('button', { name: /confirmar pago/i })).toBeDisabled()
  })

  it('Transferencia exige referencia: el campo aparece obligatorio y hasta completarlo no se confirma', async () => {
    montarApi(apiFetchMock)
    const usuario = userEvent.setup()
    renderPantalla()
    await elegirProveedor(usuario)
    await tipearImporte(usuario, '100000')
    await screen.findByRole('option', { name: 'Transferencia' })
    await usuario.selectOptions(screen.getAllByLabelText(/^medio de pago$/i)[0] as HTMLElement, TRANSFERENCIA_ID)
    await usuario.type(screen.getAllByLabelText(/^importe del medio$/i)[0] as HTMLElement, '100000')

    const referencia = screen.getByLabelText(/^referencia/i)
    expect(referencia).toBeRequired()
    expect(screen.getByRole('button', { name: /confirmar pago/i })).toBeDisabled()

    await usuario.type(referencia, '0042')

    expect(screen.getByRole('button', { name: /confirmar pago/i })).toBeEnabled()
  })

  it('el campo de referencia no aparece en un medio que no la exige', async () => {
    montarApi(apiFetchMock)
    const usuario = userEvent.setup()
    renderPantalla()
    await cargarEfectivo(usuario, '10')

    expect(screen.queryByLabelText(/^referencia/i)).not.toBeInTheDocument()
  })

  it('un pago que deja saldo a nuestro favor pide confirmación explícita y solo se envía si la acepta', async () => {
    montarApi(apiFetchMock, [
      { metodo: 'POST', ruta: '/pagos-proveedores', responder: () => ({ status: 201, cuerpo: { ...PAGO_REGISTRADO, importe: '160000.00', saldo: '-6280.00' } }) },
    ])
    const usuario = userEvent.setup()
    renderPantalla()
    await elegirProveedor(usuario)
    await screen.findByTestId('saldo-actual')
    await tipearImporte(usuario, '160000')
    await cargarEfectivo(usuario, '160000')

    await usuario.click(screen.getByRole('button', { name: /confirmar pago/i }))

    const dialogo = await screen.findByRole('dialog')
    expect(within(dialogo).getByText('Queda saldo a nuestro favor de $ 6.280,00')).toBeInTheDocument()
    expect(llamadas(apiFetchMock, 'POST', '/pagos-proveedores')).toHaveLength(0)

    await usuario.click(within(dialogo).getByRole('button', { name: /cancelar/i }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(llamadas(apiFetchMock, 'POST', '/pagos-proveedores')).toHaveLength(0)

    await usuario.click(screen.getByRole('button', { name: /confirmar pago/i }))
    await usuario.click(within(await screen.findByRole('dialog')).getByRole('button', { name: /aceptar y registrar/i }))

    await waitFor(() => expect(llamadas(apiFetchMock, 'POST', '/pagos-proveedores')).toHaveLength(1))
    expect(await screen.findByText(/pago registrado/i)).toBeInTheDocument()
    expect(screen.getByTestId('saldo-final')).toHaveTextContent('Saldo a nuestro favor $ 6.280,00')
  })

  describe('saldo del proveedor que no se puede leer (PAG-02, D3)', () => {
    const AVISO = /no pudimos leer el saldo del proveedor; no podemos avisarte si este pago supera la deuda/i
    const saldoCaido = (status: number): ReglaDeApi => ({
      metodo: 'GET',
      ruta: `/proveedores/${PROVEEDOR_ID}/saldo`,
      responder: () => ({ status, cuerpo: { title: 'No disponible', codigo: 'ERROR' } }),
    })
    const registrarOk: ReglaDeApi = {
      metodo: 'POST',
      ruta: '/pagos-proveedores',
      responder: () => ({ status: 201, cuerpo: PAGO_REGISTRADO }),
    }

    async function cargarPagoDe(usuario: Usuario, importe: string) {
      await elegirProveedor(usuario)
      await tipearImporte(usuario, importe)
      await cargarEfectivo(usuario, importe)
    }

    it.each([500, 403])('con un error %i muestra el aviso, pide confirmación y solo envía si se acepta', async (status) => {
      montarApi(apiFetchMock, [saldoCaido(status), registrarOk])
      const usuario = userEvent.setup()
      renderPantalla()
      await cargarPagoDe(usuario, '100000')

      expect(await screen.findByText(AVISO)).toBeInTheDocument()
      await usuario.click(screen.getByRole('button', { name: /confirmar pago/i }))

      const dialogo = await screen.findByRole('dialog')
      expect(within(dialogo).getByText(AVISO)).toBeInTheDocument()
      expect(within(dialogo).queryByText(/queda saldo a nuestro favor/i)).not.toBeInTheDocument()
      expect(llamadas(apiFetchMock, 'POST', '/pagos-proveedores')).toHaveLength(0)

      await usuario.click(within(dialogo).getByRole('button', { name: /cancelar/i }))
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
      expect(llamadas(apiFetchMock, 'POST', '/pagos-proveedores')).toHaveLength(0)

      await usuario.click(screen.getByRole('button', { name: /confirmar pago/i }))
      await usuario.click(within(await screen.findByRole('dialog')).getByRole('button', { name: /aceptar y registrar/i }))

      expect(await screen.findByText(/pago registrado/i)).toBeInTheDocument()
      expect(llamadas(apiFetchMock, 'POST', '/pagos-proveedores')).toHaveLength(1)
    })

    it('al cancelar y aceptar después el envío lleva el Operation-Id del contenido', async () => {
      montarApi(apiFetchMock, [saldoCaido(500), registrarOk])
      const usuario = userEvent.setup()
      renderPantalla()
      await cargarPagoDe(usuario, '100000')
      await screen.findByText(AVISO)

      await usuario.click(screen.getByRole('button', { name: /confirmar pago/i }))
      await usuario.click(within(await screen.findByRole('dialog')).getByRole('button', { name: /aceptar y registrar/i }))
      await screen.findByText(/pago registrado/i)

      const id = new Headers(llamadas(apiFetchMock, 'POST', '/pagos-proveedores')[0]?.init.headers).get('Operation-Id')
      expect(id).toMatch(/^[0-9a-f-]{36}$/i)
    })

    it('mientras el saldo carga no se puede enviar', async () => {
      montarApi(apiFetchMock, [registrarOk])
      const previo = apiFetchMock.getMockImplementation() as (ruta: string, init?: RequestInit) => Promise<unknown>
      apiFetchMock.mockImplementation((ruta: string, init?: RequestInit) =>
        ruta.includes('/saldo') ? new Promise(() => undefined) : previo(ruta, init),
      )
      const usuario = userEvent.setup()
      renderPantalla()
      await cargarPagoDe(usuario, '100000')

      expect(await screen.findByText(/cargando saldo/i)).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /confirmar pago/i })).toBeDisabled()
      expect(screen.queryByText(AVISO)).not.toBeInTheDocument()
    })

    it('con el saldo leído y sin exceso no muestra el aviso ni pide confirmación', async () => {
      montarApi(apiFetchMock, [registrarOk])
      const usuario = userEvent.setup()
      renderPantalla()
      await elegirProveedor(usuario)
      await screen.findByTestId('saldo-actual')
      await tipearImporte(usuario, '100000')
      await cargarEfectivo(usuario, '100000')

      expect(screen.queryByText(AVISO)).not.toBeInTheDocument()
      await usuario.click(screen.getByRole('button', { name: /confirmar pago/i }))

      expect(await screen.findByText(/pago registrado/i)).toBeInTheDocument()
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    })

    it('con el saldo leído y exceso sigue la confirmación de saldo a favor, sin el aviso de saldo ilegible', async () => {
      montarApi(apiFetchMock, [registrarOk])
      const usuario = userEvent.setup()
      renderPantalla()
      await elegirProveedor(usuario)
      await screen.findByTestId('saldo-actual')
      await tipearImporte(usuario, '160000')
      await cargarEfectivo(usuario, '160000')

      await usuario.click(screen.getByRole('button', { name: /confirmar pago/i }))

      const dialogo = await screen.findByRole('dialog')
      expect(within(dialogo).getByText('Queda saldo a nuestro favor de $ 6.280,00')).toBeInTheDocument()
      expect(screen.queryByText(AVISO)).not.toBeInTheDocument()
    })
  })

  it('un pago que no deja saldo a favor se envía sin diálogo, con el cuerpo esperado y un Operation-Id', async () => {
    montarApi(apiFetchMock, [
      { metodo: 'POST', ruta: '/pagos-proveedores', responder: () => ({ status: 201, cuerpo: PAGO_REGISTRADO }) },
    ])
    const usuario = userEvent.setup()
    renderPantalla()
    await elegirProveedor(usuario)
    await screen.findByTestId('saldo-actual')
    await tipearImporte(usuario, '100000')
    await cargarEfectivo(usuario, '100000')
    await usuario.type(screen.getByLabelText(/observaci[oó]n/i), 'Paga facturas 0001-123')

    await usuario.click(screen.getByRole('button', { name: /confirmar pago/i }))

    expect(await screen.findByText(/pago registrado/i)).toBeInTheDocument()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(cuerpoDelPost()).toEqual({
      proveedor_id: PROVEEDOR_ID,
      fecha: fechaDeHoyParaPruebas(),
      importe: '100000.00',
      observacion: 'Paga facturas 0001-123',
      medios: [{ medio_pago_id: EFECTIVO_ID, importe: '100000.00', referencia: null }],
    })
    const idDeOperacion = new Headers(llamadas(apiFetchMock, 'POST', '/pagos-proveedores')[0]?.init.headers).get('Operation-Id')
    expect(idDeOperacion).toBeTruthy()
    expect(screen.getByRole('link', { name: /ver el pago/i })).toHaveAttribute('href', `/admin/pagos-proveedores/${PAGO_ID}`)
  })

  it('un error del servidor sobre el segundo medio se muestra junto a ese medio y conserva lo cargado', async () => {
    montarApi(apiFetchMock, [
      {
        metodo: 'POST',
        ruta: '/pagos-proveedores',
        responder: () => ({ status: 422, cuerpo: { title: 'Medio 2: el medio de pago está inactivo', codigo: 'MEDIO_PAGO_INACTIVO', medio: 1 } }),
      },
    ])
    const usuario = userEvent.setup()
    renderPantalla()
    await elegirProveedor(usuario)
    await tipearImporte(usuario, '100000')
    await cargarEfectivo(usuario, '60000')
    await usuario.click(screen.getByRole('button', { name: /agregar medio/i }))
    await usuario.selectOptions(screen.getAllByLabelText(/^medio de pago$/i)[1] as HTMLElement, TRANSFERENCIA_ID)
    await usuario.type(screen.getAllByLabelText(/^importe del medio$/i)[1] as HTMLElement, '40000')
    await usuario.type(screen.getByLabelText(/^referencia/i), '0042')

    await usuario.click(screen.getByRole('button', { name: /confirmar pago/i }))

    const medio2 = await screen.findByTestId('medio-1')
    expect(await within(medio2).findByText('Medio 2: el medio de pago está inactivo')).toBeInTheDocument()
    expect(within(screen.getByTestId('medio-0')).queryByRole('alert')).not.toBeInTheDocument()
    expect(screen.getByLabelText(/^importe$/i)).toHaveValue('100000')
    expect(screen.getAllByLabelText(/^importe del medio$/i)[0]).toHaveValue('60000')
    expect(screen.getByLabelText(/^referencia/i)).toHaveValue('0042')
  })

  it('un error sin medio se muestra como alerta general', async () => {
    montarApi(apiFetchMock, [
      { metodo: 'POST', ruta: '/pagos-proveedores', responder: () => ({ status: 422, cuerpo: { title: 'La fecha no puede ser futura', codigo: 'FECHA_INVALIDA' } }) },
    ])
    const usuario = userEvent.setup()
    renderPantalla()
    await elegirProveedor(usuario)
    await tipearImporte(usuario, '100')
    await cargarEfectivo(usuario, '100')

    await usuario.click(screen.getByRole('button', { name: /confirmar pago/i }))

    expect(await screen.findByText('La fecha no puede ser futura')).toBeInTheDocument()
  })

  it('tras un error de red el reintento reenvía el mismo Operation-Id; si cambia el contenido, uno nuevo', async () => {
    let intento = 0
    montarApi(apiFetchMock, [
      {
        metodo: 'POST',
        ruta: '/pagos-proveedores',
        responder: () => {
          intento += 1
          if (intento <= 3) throw new TypeError('Failed to fetch')
          return { status: 201, cuerpo: PAGO_REGISTRADO }
        },
      },
    ])
    const usuario = userEvent.setup()
    renderPantalla()
    await elegirProveedor(usuario)
    await screen.findByTestId('saldo-actual')
    await tipearImporte(usuario, '100000')
    await cargarEfectivo(usuario, '100000')

    await usuario.click(screen.getByRole('button', { name: /confirmar pago/i }))
    await waitFor(() => expect(llamadas(apiFetchMock, 'POST', '/pagos-proveedores').length).toBeGreaterThanOrEqual(3))
    expect(await screen.findByText(/requiere conexi[oó]n/i)).toBeInTheDocument()
    await screen.findByRole('alert')
    const ids = llamadas(apiFetchMock, 'POST', '/pagos-proveedores').map((l) => new Headers(l.init.headers).get('Operation-Id'))
    expect(new Set(ids).size).toBe(1)

    await usuario.type(screen.getByLabelText(/observaci[oó]n/i), 'otro contenido')
    await usuario.click(screen.getByRole('button', { name: /confirmar pago/i }))

    await waitFor(() => expect(llamadas(apiFetchMock, 'POST', '/pagos-proveedores').length).toBeGreaterThan(ids.length))
    const todos = llamadas(apiFetchMock, 'POST', '/pagos-proveedores').map((l) => new Headers(l.init.headers).get('Operation-Id'))
    expect(todos[todos.length - 1]).not.toBe(ids[0])
  })

  it('precarga el proveedor de la cuenta corriente y su saldo, también si está inactivo (D5)', async () => {
    montarApi(
      apiFetchMock,
      [
        {
          metodo: 'GET',
          ruta: '/proveedores/opciones',
          responder: () => ({ status: 200, cuerpo: { items: [{ id: PROVEEDOR_ID, nombre: 'Bodega Sur' }], cursor_siguiente: null } }),
        },
        {
          metodo: 'GET',
          ruta: `/proveedores/${PROVEEDOR_NORTE_ID}`,
          responder: () => ({ status: 200, cuerpo: { id: PROVEEDOR_NORTE_ID, nombre: 'Bodega Norte', activo: false } }),
        },
        { metodo: 'GET', ruta: `/proveedores/${PROVEEDOR_NORTE_ID}/saldo`, responder: () => ({ status: 200, cuerpo: { saldo: '80000.00' } }) },
      ],
    )
    renderPantalla('GES', `/admin/pagos-proveedores/nuevo?proveedor=${PROVEEDOR_NORTE_ID}`)

    expect(await screen.findByTestId('saldo-actual')).toHaveTextContent('Le debemos $ 80.000,00')
    await waitFor(() => expect(screen.getByLabelText(/^proveedor$/i)).toHaveValue(PROVEEDOR_NORTE_ID))
    expect(screen.getByRole('option', { name: /bodega norte/i })).toBeInTheDocument()
  })

  it('precarga un proveedor activo de la lista de opciones', async () => {
    montarApi(apiFetchMock)
    renderPantalla('GES', `/admin/pagos-proveedores/nuevo?proveedor=${PROVEEDOR_ID}`)

    await waitFor(() => expect(screen.getByLabelText(/^proveedor$/i)).toHaveValue(PROVEEDOR_ID))
    expect(await screen.findByTestId('saldo-actual')).toHaveTextContent('Le debemos $ 153.720,00')
  })

  it('no permite una fecha posterior a hoy', async () => {
    montarApi(apiFetchMock)
    const usuario = userEvent.setup()
    renderPantalla()
    await elegirProveedor(usuario)
    await tipearImporte(usuario, '100')
    await cargarEfectivo(usuario, '100')
    expect(screen.getByRole('button', { name: /confirmar pago/i })).toBeEnabled()

    const futuro = new Date()
    futuro.setDate(futuro.getDate() + 2)
    const texto = `${String(futuro.getFullYear())}-${String(futuro.getMonth() + 1).padStart(2, '0')}-${String(futuro.getDate()).padStart(2, '0')}`
    await usuario.clear(screen.getByLabelText(/fecha del pago/i))
    await usuario.type(screen.getByLabelText(/fecha del pago/i), texto)

    expect(screen.getByRole('button', { name: /confirmar pago/i })).toBeDisabled()
  })
})
