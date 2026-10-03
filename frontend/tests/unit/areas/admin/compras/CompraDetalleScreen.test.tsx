import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }))
vi.mock('../../../../../src/lib/api/httpClient', () => ({ apiFetch: apiFetchMock }))

import { CompraDetalleScreen } from '../../../../../src/areas/admin/compras/CompraDetalleScreen'
import { enrutar, llamadas, type ReglaDeApi } from '../../../utils/enrutarApi'
import { queryClientConYo, type RolDePrueba } from '../../../utils/permisosDePrueba'
import { COMPRA_ID, EFECTIVO_ID, MOTIVO_ID, PROVEEDOR_ID, UBICACION_ID, VINO_A_ID, CAJA_X12_ID } from './comprasDePrueba'

function detalle(sobrescribir: Record<string, unknown> = {}) {
  return {
    id: COMPRA_ID,
    fecha: '2026-05-10',
    proveedor_id: PROVEEDOR_ID,
    proveedor_nombre: 'Bodega Sur',
    condicion: 'CREDITO',
    total_neto: '14876.03',
    total_factura: '18000.00',
    estado: 'CONFIRMADA',
    numero_comprobante: 'A-0001',
    ubicacion_id: UBICACION_ID,
    observacion: null,
    lineas: [
      {
        orden: 1,
        producto_id: VINO_A_ID,
        producto_codigo: 'VIN-A',
        producto_nombre: 'Vino A',
        presentacion_id: CAJA_X12_ID,
        presentacion_nombre: 'Botella',
        unidades_presentacion: 1,
        unidades_referencia: 6,
        nombre_referencia: 'Caja x6',
        cantidad: '31',
        cantidad_base: 31,
        valor_presentacion: '1000.00',
        incluye_iva: false,
        bonificacion: '0.000000',
        alicuota_aplicada: '0.210000',
        costo_base: '1000.000000',
        importe_neto: '31000.00',
      },
    ],
    pago: null,
    anulacion: null,
    ...sobrescribir,
  }
}

const PAGO = {
  id: 'p1',
  fecha: '2026-05-10',
  importe: '18000.00',
  estado: 'CONFIRMADO',
  anulado_en: null,
  medios: [{ medio_pago_id: EFECTIVO_ID, medio_nombre: 'Efectivo', importe: '18000.00', referencia: null }],
}

function reglas(compra: unknown, extra: ReglaDeApi[] = []): ReglaDeApi[] {
  return [
    ...extra,
    { metodo: 'GET', ruta: `/compras/${COMPRA_ID}`, responder: () => ({ status: 200, cuerpo: compra }) },
    { metodo: 'GET', ruta: '/configuracion/motivos', responder: () => ({ status: 200, cuerpo: { items: [{ id: MOTIVO_ID, nombre: 'Error de carga' }] } }) },
  ]
}

function renderDetalle(rol: RolDePrueba = 'GES', permisos?: string[]) {
  const cliente = permisos ? queryClientConYo(rol, { permisos } as never) : queryClientConYo(rol)
  return render(
    <QueryClientProvider client={cliente}>
      <MemoryRouter initialEntries={[`/admin/compras/${COMPRA_ID}`]}>
        <Routes>
          <Route path="/admin/compras/:compraId" element={<CompraDetalleScreen />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('CompraDetalleScreen (tarea 12.3)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
  })
  afterEach(() => {
    vi.clearAllMocks()
  })

  it('muestra unidades base y la equivalencia en la referencia (CAT-08): 31 unidades con referencia de 6 son 31 unidades (5 Caja x6 + 1 un.)', async () => {
    enrutar(apiFetchMock, reglas(detalle()))
    renderDetalle()

    expect(await screen.findByText('Vino A')).toBeInTheDocument()
    expect(screen.getByText('31 unidades (5 Caja x6 + 1 un.)')).toBeInTheDocument()
    expect(screen.getByText('31.000,00')).toBeInTheDocument()
  })

  it('una línea sin presentación de referencia muestra solo unidades', async () => {
    const compra = detalle()
    ;(compra.lineas[0] as Record<string, unknown>).unidades_referencia = null
    ;(compra.lineas[0] as Record<string, unknown>).nombre_referencia = null
    enrutar(apiFetchMock, reglas(compra))
    renderDetalle()

    expect(await screen.findByText('31 unidades')).toBeInTheDocument()
    expect(screen.queryByText(/cajas/)).not.toBeInTheDocument()
  })

  it('muestra el pago de contado con sus medios', async () => {
    enrutar(apiFetchMock, reglas(detalle({ condicion: 'CONTADO', pago: PAGO })))
    renderDetalle()

    expect(await screen.findByText('Efectivo')).toBeInTheDocument()
  })

  it('una compra anulada muestra motivo y fecha de anulación y no ofrece "Anular"', async () => {
    enrutar(
      apiFetchMock,
      reglas(
        detalle({
          estado: 'ANULADA',
          anulacion: { motivo_id: MOTIVO_ID, motivo_nombre: 'Error de carga', anulada_en: '2026-05-11T15:30:00Z', anulada_por_id: 'u1' },
        }),
      ),
    )
    renderDetalle()

    expect(await screen.findByText(/error de carga/i)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /^anular/i })).not.toBeInTheDocument()
  })

  it('sin ANULAR_COMPRA no ofrece "Anular" aunque la compra esté confirmada', async () => {
    enrutar(apiFetchMock, reglas(detalle()))
    renderDetalle('GES', ['REGISTRAR_COMPRA'])

    await screen.findByText('Vino A')
    expect(screen.queryByRole('button', { name: /^anular/i })).not.toBeInTheDocument()
  })

  it('anular una compra a crédito pide motivo, no pregunta por la devolución y envía solo el motivo', async () => {
    enrutar(
      apiFetchMock,
      reglas(detalle(), [
        {
          metodo: 'POST',
          ruta: `/compras/${COMPRA_ID}/anulacion`,
          responder: () => ({ status: 200, cuerpo: { compra_id: COMPRA_ID, estado: 'ANULADA', pago_anulado: false, observaciones: [] } }),
        },
      ]),
    )
    const usuario = userEvent.setup()
    renderDetalle()
    await screen.findByText('Vino A')

    await usuario.click(screen.getByRole('button', { name: /^anular compra$/i }))
    const dialogo = await screen.findByRole('dialog')
    expect(within(dialogo).queryByText(/devuelve el dinero/i)).not.toBeInTheDocument()
    await within(dialogo).findByRole('option', { name: 'Error de carga' })
    await usuario.selectOptions(within(dialogo).getByLabelText(/motivo/i), MOTIVO_ID)
    await usuario.click(within(dialogo).getByRole('button', { name: /confirmar anulaci[oó]n/i }))

    await waitFor(() => expect(llamadas(apiFetchMock, 'POST', `/compras/${COMPRA_ID}/anulacion`)).toHaveLength(1))
    const llamada = llamadas(apiFetchMock, 'POST', `/compras/${COMPRA_ID}/anulacion`)[0]
    expect(JSON.parse(String(llamada?.init.body))).toEqual({ motivo_id: MOTIVO_ID })
    expect(new Headers(llamada?.init.headers).get('Operation-Id')).toBeTruthy()
  })

  it('anular una compra de contado exige decidir si el proveedor devuelve el dinero y lo envía', async () => {
    enrutar(
      apiFetchMock,
      reglas(detalle({ condicion: 'CONTADO', pago: PAGO }), [
        {
          metodo: 'POST',
          ruta: `/compras/${COMPRA_ID}/anulacion`,
          responder: () => ({ status: 200, cuerpo: { compra_id: COMPRA_ID, estado: 'ANULADA', pago_anulado: true, observaciones: [] } }),
        },
      ]),
    )
    const usuario = userEvent.setup()
    renderDetalle()
    await screen.findByText('Efectivo')

    await usuario.click(screen.getByRole('button', { name: /^anular compra$/i }))
    const dialogo = await screen.findByRole('dialog')
    await within(dialogo).findByRole('option', { name: 'Error de carga' })
    await usuario.selectOptions(within(dialogo).getByLabelText(/motivo/i), MOTIVO_ID)
    expect(within(dialogo).getByRole('button', { name: /confirmar anulaci[oó]n/i })).toBeDisabled()

    await usuario.click(within(dialogo).getByLabelText(/el proveedor devuelve el dinero/i))
    await usuario.click(within(dialogo).getByRole('button', { name: /confirmar anulaci[oó]n/i }))

    await waitFor(() => expect(llamadas(apiFetchMock, 'POST', `/compras/${COMPRA_ID}/anulacion`)).toHaveLength(1))
    const llamada = llamadas(apiFetchMock, 'POST', `/compras/${COMPRA_ID}/anulacion`)[0]
    expect(JSON.parse(String(llamada?.init.body))).toEqual({ motivo_id: MOTIVO_ID, devuelve_pago: true })
  })

  it('"no devuelve" también es una decisión válida y viaja como false', async () => {
    enrutar(
      apiFetchMock,
      reglas(detalle({ condicion: 'CONTADO', pago: PAGO }), [
        {
          metodo: 'POST',
          ruta: `/compras/${COMPRA_ID}/anulacion`,
          responder: () => ({ status: 200, cuerpo: { compra_id: COMPRA_ID, estado: 'ANULADA', pago_anulado: false, observaciones: [] } }),
        },
      ]),
    )
    const usuario = userEvent.setup()
    renderDetalle()
    await screen.findByText('Efectivo')

    await usuario.click(screen.getByRole('button', { name: /^anular compra$/i }))
    const dialogo = await screen.findByRole('dialog')
    await within(dialogo).findByRole('option', { name: 'Error de carga' })
    await usuario.selectOptions(within(dialogo).getByLabelText(/motivo/i), MOTIVO_ID)
    await usuario.click(within(dialogo).getByLabelText(/el proveedor no devuelve el dinero/i))
    await usuario.click(within(dialogo).getByRole('button', { name: /confirmar anulaci[oó]n/i }))

    await waitFor(() => expect(llamadas(apiFetchMock, 'POST', `/compras/${COMPRA_ID}/anulacion`)).toHaveLength(1))
    const llamada = llamadas(apiFetchMock, 'POST', `/compras/${COMPRA_ID}/anulacion`)[0]
    expect(JSON.parse(String(llamada?.init.body))).toEqual({ motivo_id: MOTIVO_ID, devuelve_pago: false })
  })

  it('una observación del servidor se muestra como aviso: el costo promedio no se recalculó', async () => {
    let anulada = false
    enrutar(apiFetchMock, [
      {
        metodo: 'POST',
        ruta: `/compras/${COMPRA_ID}/anulacion`,
        responder: () => {
          anulada = true
          return {
            status: 200,
            cuerpo: { compra_id: COMPRA_ID, estado: 'ANULADA', pago_anulado: false, observaciones: ['ANULACION_COMPRA_SIN_RECALCULO'] },
          }
        },
      },
      {
        metodo: 'GET',
        ruta: `/compras/${COMPRA_ID}`,
        responder: () => ({
          status: 200,
          cuerpo: anulada
            ? detalle({ estado: 'ANULADA', anulacion: { motivo_id: MOTIVO_ID, motivo_nombre: 'Error de carga', anulada_en: '2026-05-11T15:30:00Z', anulada_por_id: 'u1' } })
            : detalle(),
        }),
      },
      { metodo: 'GET', ruta: '/configuracion/motivos', responder: () => ({ status: 200, cuerpo: { items: [{ id: MOTIVO_ID, nombre: 'Error de carga' }] } }) },
    ])
    const usuario = userEvent.setup()
    renderDetalle()
    await screen.findByText('Vino A')

    await usuario.click(screen.getByRole('button', { name: /^anular compra$/i }))
    const dialogo = await screen.findByRole('dialog')
    await within(dialogo).findByRole('option', { name: 'Error de carga' })
    await usuario.selectOptions(within(dialogo).getByLabelText(/motivo/i), MOTIVO_ID)
    await usuario.click(within(dialogo).getByRole('button', { name: /confirmar anulaci[oó]n/i }))

    expect(await screen.findByText(/el costo promedio no se recalcul[oó]/i)).toBeInTheDocument()
    expect(await screen.findByText('Anulada')).toBeInTheDocument()
  })

  it('un rechazo del servidor (COMPRA_YA_ANULADA) se muestra en el diálogo', async () => {
    enrutar(
      apiFetchMock,
      reglas(detalle(), [
        {
          metodo: 'POST',
          ruta: `/compras/${COMPRA_ID}/anulacion`,
          responder: () => ({ status: 409, cuerpo: { title: 'La compra ya está anulada.', codigo: 'COMPRA_YA_ANULADA' } }),
        },
      ]),
    )
    const usuario = userEvent.setup()
    renderDetalle()
    await screen.findByText('Vino A')

    await usuario.click(screen.getByRole('button', { name: /^anular compra$/i }))
    const dialogo = await screen.findByRole('dialog')
    await within(dialogo).findByRole('option', { name: 'Error de carga' })
    await usuario.selectOptions(within(dialogo).getByLabelText(/motivo/i), MOTIVO_ID)
    await usuario.click(within(dialogo).getByRole('button', { name: /confirmar anulaci[oó]n/i }))

    expect(await within(dialogo).findByText('La compra ya está anulada.')).toBeInTheDocument()
  })

  it('un usuario sin permisos de compra ve el aviso y no se pide la compra', async () => {
    enrutar(apiFetchMock, reglas(detalle()))
    renderDetalle('VEN')

    expect(await screen.findByText(/no ten[eé]s permiso para ver las compras/i)).toBeInTheDocument()
    expect(llamadas(apiFetchMock, 'GET', `/compras/${COMPRA_ID}`)).toHaveLength(0)
  })

  it('una compra inexistente o ajena (404) se informa como no encontrada', async () => {
    enrutar(apiFetchMock, [
      { metodo: 'GET', ruta: `/compras/${COMPRA_ID}`, responder: () => ({ status: 404, cuerpo: { title: 'No existe', codigo: 'RECURSO_NO_ENCONTRADO' } }) },
    ])
    renderDetalle()

    expect(await screen.findByText(/no se encontr[oó] la compra/i)).toBeInTheDocument()
  })
})
