import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }))
vi.mock('../../../../../src/lib/api/httpClient', () => ({ apiFetch: apiFetchMock }))

import { PagoDetalleScreen } from '../../../../../src/areas/admin/pagos-proveedores/PagoDetalleScreen'
import { llamadas, type ReglaDeApi } from '../../../utils/enrutarApi'
import { queryClientConYo } from '../../../utils/permisosDePrueba'
import {
  ANULACION_DE_PAGO,
  COMPRA_DEL_PAGO_ID,
  MOTIVO_PAGO_ID,
  PAGO_DE_COMPRA_ID,
  PAGO_ID,
  PROVEEDOR_ID,
  montarApi,
  pagoDetalle,
  reglaSaldo,
} from './pagosDePrueba'

function renderPantalla(pagoId = PAGO_ID, permisos?: string[]) {
  const cliente = permisos ? queryClientConYo('GES', { permisos } as never) : queryClientConYo('GES')
  return render(
    <QueryClientProvider client={cliente}>
      <MemoryRouter initialEntries={[`/admin/pagos-proveedores/${pagoId}`]}>
        <Routes>
          <Route path="/admin/pagos-proveedores/:pagoId" element={<PagoDetalleScreen />} />
          <Route path="/admin/pagos-proveedores" element={<p>Listado de pagos</p>} />
          <Route path="/admin/compras/:compraId" element={<p>Detalle de la compra</p>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

function reglaDetalle(pago: () => unknown, id = PAGO_ID): ReglaDeApi {
  return { metodo: 'GET', ruta: `/pagos-proveedores/${id}`, responder: () => ({ status: 200, cuerpo: pago() }) }
}

const IMPORTE_52460 = { importe: '52460.00' }

describe('PagoDetalleScreen (tarea 9.2)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
  })
  afterEach(() => {
    vi.clearAllMocks()
  })

  it('muestra el proveedor, el importe, el estado, la observación y los medios con su referencia', async () => {
    montarApi(apiFetchMock, [reglaDetalle(() => pagoDetalle())])
    renderPantalla()

    expect(await screen.findByText(/paga facturas 0001-123/i)).toBeInTheDocument()
    expect(screen.getByText(/bodega sur/i)).toBeInTheDocument()
    expect(screen.getByText('Confirmado')).toBeInTheDocument()
    expect(screen.getByTestId('importe-del-pago')).toHaveTextContent('100.000,00')
    const medios = screen.getAllByTestId('medio-del-pago')
    expect(medios).toHaveLength(2)
    expect(medios[0]).toHaveTextContent('Efectivo: 60.000,00')
    expect(medios[1]).toHaveTextContent('Transferencia: 40.000,00 (ref. 0042)')
  })

  it('el pago de origen COMPRA enlaza a la compra', async () => {
    montarApi(apiFetchMock, [
      reglaDetalle(() => pagoDetalle({ pago_id: PAGO_DE_COMPRA_ID, origen: 'COMPRA', compra_id: COMPRA_DEL_PAGO_ID, compra_estado: 'CONFIRMADA' }), PAGO_DE_COMPRA_ID),
    ])
    renderPantalla(PAGO_DE_COMPRA_ID)

    expect(await screen.findByRole('link', { name: /ver la compra/i })).toHaveAttribute('href', `/admin/compras/${COMPRA_DEL_PAGO_ID}`)
  })

  it('un pago anulado muestra el motivo, el usuario y el momento y no ofrece "Anular"', async () => {
    montarApi(apiFetchMock, [reglaDetalle(() => pagoDetalle({ estado: 'ANULADA', anulacion: ANULACION_DE_PAGO }))])
    renderPantalla()

    expect(await screen.findByText('Anulado')).toBeInTheDocument()
    const bloque = screen.getByTestId('anulacion-del-pago')
    expect(bloque).toHaveTextContent('Pago rechazado o devuelto')
    expect(bloque).toHaveTextContent('Marta Anuladora')
    expect(bloque).not.toHaveTextContent('a1a1a1a1-a1a1-41a1-81a1-a1a1a1a1a1a1')
    expect(bloque).toHaveTextContent(/2026/)
    expect(screen.queryByRole('button', { name: /anular pago/i })).not.toBeInTheDocument()
  })

  it('el usuario que anuló se muestra por su nombre, sea cual sea', async () => {
    montarApi(apiFetchMock, [
      reglaDetalle(() =>
        pagoDetalle({
          estado: 'ANULADA',
          anulacion: { ...ANULACION_DE_PAGO, anulado_por_id: 'b2b2b2b2-b2b2-42b2-82b2-b2b2b2b2b2b2', anulado_por_nombre: 'Carlos Contador' },
        }),
      ),
    ])
    renderPantalla()

    await screen.findByText('Anulado')
    const bloque = screen.getByTestId('anulacion-del-pago')
    expect(bloque).toHaveTextContent('Usuario: Carlos Contador')
    expect(bloque).not.toHaveTextContent('b2b2b2b2')
  })

  it('con ANULAR_PAGO_PROVEEDOR ofrece "Anular pago" sobre un pago independiente confirmado', async () => {
    montarApi(apiFetchMock, [reglaDetalle(() => pagoDetalle())])
    renderPantalla()

    expect(await screen.findByRole('button', { name: /anular pago/i })).toBeInTheDocument()
  })

  it('sin ANULAR_PAGO_PROVEEDOR no ofrece "Anular pago"', async () => {
    montarApi(apiFetchMock, [reglaDetalle(() => pagoDetalle())])
    renderPantalla(PAGO_ID, ['REGISTRAR_PAGO_PROVEEDOR'])

    await screen.findByText(/paga facturas 0001-123/i)
    expect(screen.queryByRole('button', { name: /anular pago/i })).not.toBeInTheDocument()
  })

  it('en el pago de una compra vigente no hay "Anular" y se indica que se anula anulando la compra', async () => {
    montarApi(apiFetchMock, [
      reglaDetalle(() => pagoDetalle({ pago_id: PAGO_DE_COMPRA_ID, origen: 'COMPRA', compra_id: COMPRA_DEL_PAGO_ID, compra_estado: 'CONFIRMADA' }), PAGO_DE_COMPRA_ID),
    ])
    renderPantalla(PAGO_DE_COMPRA_ID)

    expect(await screen.findByText(/se anula anulando la compra/i)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /anular pago/i })).not.toBeInTheDocument()
    expect(screen.getAllByRole('link', { name: /compra/i })[0]).toHaveAttribute('href', `/admin/compras/${COMPRA_DEL_PAGO_ID}`)
  })

  it('el pago de una compra ya anulada (sin devolución) sí se puede anular', async () => {
    montarApi(apiFetchMock, [
      reglaDetalle(() => pagoDetalle({ pago_id: PAGO_DE_COMPRA_ID, origen: 'COMPRA', compra_id: COMPRA_DEL_PAGO_ID, compra_estado: 'ANULADA' }), PAGO_DE_COMPRA_ID),
    ])
    renderPantalla(PAGO_DE_COMPRA_ID)

    expect(await screen.findByRole('button', { name: /anular pago/i })).toBeInTheDocument()
    expect(screen.queryByText(/se anula anulando la compra/i)).not.toBeInTheDocument()
  })

  it('anula con un motivo de ANULACION_PAGO, muestra el saldo resultante y envía PAGO_PROVEEDOR_ANULAR', async () => {
    let anulado = false
    montarApi(
      apiFetchMock,
      [
        reglaDetalle(() => (anulado ? pagoDetalle({ ...IMPORTE_52460, estado: 'ANULADA', anulacion: ANULACION_DE_PAGO }) : pagoDetalle(IMPORTE_52460))),
        reglaSaldo('100000.00'),
        {
          metodo: 'POST',
          ruta: `/pagos-proveedores/${PAGO_ID}/anulacion`,
          responder: () => {
            anulado = true
            return { status: 200, cuerpo: { pago_id: PAGO_ID, estado: 'ANULADA', saldo: '152460.00' } }
          },
        },
      ],
    )
    const usuario = userEvent.setup()
    renderPantalla()

    await usuario.click(await screen.findByRole('button', { name: /anular pago/i }))
    const dialogo = await screen.findByRole('dialog')
    expect(llamadas(apiFetchMock, 'GET', '/configuracion/motivos').at(-1)?.url.searchParams.get('ambito')).toBe('ANULACION_PAGO')
    const confirmar = within(dialogo).getByRole('button', { name: /confirmar anulaci[oó]n/i })
    expect(confirmar).toBeDisabled()

    await within(dialogo).findByRole('option', { name: 'Pago rechazado o devuelto' })
    await usuario.selectOptions(within(dialogo).getByLabelText(/^motivo$/i), MOTIVO_PAGO_ID)
    expect(await within(dialogo).findByTestId('saldo-tras-anular')).toHaveTextContent('Saldo después de anular: Le debemos $ 152.460,00')
    await usuario.click(confirmar)

    await waitFor(() => expect(llamadas(apiFetchMock, 'POST', `/pagos-proveedores/${PAGO_ID}/anulacion`)).toHaveLength(1))
    const envio = llamadas(apiFetchMock, 'POST', `/pagos-proveedores/${PAGO_ID}/anulacion`)[0]
    expect(JSON.parse(String(envio?.init.body))).toEqual({ motivo_id: MOTIVO_PAGO_ID })
    expect(new Headers(envio?.init.headers).get('Operation-Id')).toBeTruthy()
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    expect(await screen.findByTestId('anulacion-del-pago')).toHaveTextContent('Pago rechazado o devuelto')
    expect(screen.queryByRole('button', { name: /anular pago/i })).not.toBeInTheDocument()
  })

  it('si el saldo no se puede leer, el diálogo no muestra el saldo resultante pero deja anular', async () => {
    montarApi(apiFetchMock, [
      reglaDetalle(() => pagoDetalle(IMPORTE_52460)),
      { metodo: 'GET', ruta: `/proveedores/${PROVEEDOR_ID}/saldo`, responder: () => ({ status: 403, cuerpo: { title: 'Falta permiso', codigo: 'PERMISO_REQUERIDO' } }) },
    ])
    const usuario = userEvent.setup()
    renderPantalla()

    await usuario.click(await screen.findByRole('button', { name: /anular pago/i }))
    const dialogo = await screen.findByRole('dialog')
    await within(dialogo).findByRole('option', { name: 'Pago rechazado o devuelto' })
    await usuario.selectOptions(within(dialogo).getByLabelText(/^motivo$/i), MOTIVO_PAGO_ID)

    expect(within(dialogo).queryByTestId('saldo-tras-anular')).not.toBeInTheDocument()
    expect(within(dialogo).getByRole('button', { name: /confirmar anulaci[oó]n/i })).toBeEnabled()
  })

  it('PAGO_YA_ANULADO muestra el mensaje y recarga el detalle, que ya figura anulado', async () => {
    let anulado = false
    montarApi(apiFetchMock, [
      reglaDetalle(() => (anulado ? pagoDetalle({ estado: 'ANULADA', anulacion: ANULACION_DE_PAGO }) : pagoDetalle())),
      {
        metodo: 'POST',
        ruta: `/pagos-proveedores/${PAGO_ID}/anulacion`,
        responder: () => {
          anulado = true
          return { status: 409, cuerpo: { title: 'El pago ya está anulado', codigo: 'PAGO_YA_ANULADO' } }
        },
      },
    ])
    const usuario = userEvent.setup()
    renderPantalla()
    await usuario.click(await screen.findByRole('button', { name: /anular pago/i }))
    const dialogo = await screen.findByRole('dialog')
    await within(dialogo).findByRole('option', { name: 'Error de carga' })
    await usuario.selectOptions(within(dialogo).getByLabelText(/^motivo$/i), MOTIVO_PAGO_ID)

    await usuario.click(within(dialogo).getByRole('button', { name: /confirmar anulaci[oó]n/i }))

    expect(await screen.findByText('El pago ya está anulado')).toBeInTheDocument()
    expect(await screen.findByTestId('anulacion-del-pago')).toBeInTheDocument()
    expect(screen.getByText('Anulado')).toBeInTheDocument()
  })

  it('PAGO_DE_COMPRA_VIGENTE del servidor se muestra en el diálogo', async () => {
    montarApi(apiFetchMock, [
      reglaDetalle(() => pagoDetalle()),
      {
        metodo: 'POST',
        ruta: `/pagos-proveedores/${PAGO_ID}/anulacion`,
        responder: () => ({ status: 409, cuerpo: { title: 'Ese pago se anula anulando su compra', codigo: 'PAGO_DE_COMPRA_VIGENTE' } }),
      },
    ])
    const usuario = userEvent.setup()
    renderPantalla()
    await usuario.click(await screen.findByRole('button', { name: /anular pago/i }))
    const dialogo = await screen.findByRole('dialog')
    await within(dialogo).findByRole('option', { name: 'Error de carga' })
    await usuario.selectOptions(within(dialogo).getByLabelText(/^motivo$/i), MOTIVO_PAGO_ID)

    await usuario.click(within(dialogo).getByRole('button', { name: /confirmar anulaci[oó]n/i }))

    expect(await within(dialogo).findByText('Ese pago se anula anulando su compra')).toBeInTheDocument()
  })

  it('un 404 muestra que no se encontró el pago y un 403 la falta de permiso', async () => {
    montarApi(apiFetchMock, [
      { metodo: 'GET', ruta: `/pagos-proveedores/${PAGO_ID}`, responder: () => ({ status: 404, cuerpo: { title: 'No existe', codigo: 'RECURSO_NO_ENCONTRADO' } }) },
    ])
    const primero = renderPantalla()
    expect(await screen.findByText(/no se encontr[oó] el pago/i)).toBeInTheDocument()
    primero.unmount()

    montarApi(apiFetchMock, [
      { metodo: 'GET', ruta: `/pagos-proveedores/${PAGO_ID}`, responder: () => ({ status: 403, cuerpo: { title: 'Falta permiso', codigo: 'PERMISO_REQUERIDO' } }) },
    ])
    renderPantalla()
    expect(await screen.findByText(/no ten[eé]s permiso para ver los pagos a proveedores/i)).toBeInTheDocument()
  })
})
