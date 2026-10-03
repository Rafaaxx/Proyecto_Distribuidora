import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }))
vi.mock('../../../../../src/lib/api/httpClient', () => ({ apiFetch: apiFetchMock }))

import { CompraFormScreen } from '../../../../../src/areas/admin/compras/CompraFormScreen'
import { llamadas } from '../../../utils/enrutarApi'
import { queryClientConYo } from '../../../utils/permisosDePrueba'
import {
  BOTELLA_ID,
  CAJA_X12_ID,
  CERVEZA_B_ID,
  COMPRA_CONFIRMADA,
  EFECTIVO_ID,
  PROVEEDOR_ID,
  UBICACION_ID,
  VINO_A_ID,
  montarApi,
  reglaFiscal,
} from './comprasDePrueba'

function renderPantalla(rol: 'GES' | 'VEN' = 'GES') {
  return render(
    <QueryClientProvider client={queryClientConYo(rol)}>
      <MemoryRouter initialEntries={['/admin/compras/nueva']}>
        <Routes>
          <Route path="/admin/compras/nueva" element={<CompraFormScreen />} />
          <Route path="/admin/compras" element={<p>Listado de compras</p>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

async function elegirCabecera(usuario: ReturnType<typeof userEvent.setup>) {
  await screen.findByRole('option', { name: 'Bodega Sur' })
  await usuario.selectOptions(screen.getByLabelText(/^proveedor$/i), PROVEEDOR_ID)
  await screen.findByRole('option', { name: 'Depósito central' })
  await usuario.selectOptions(screen.getByLabelText(/ubicaci[oó]n de destino/i), UBICACION_ID)
}

async function cargarCajaX12ConIva(usuario: ReturnType<typeof userEvent.setup>) {
  await screen.findByRole('option', { name: 'Cerveza B' })
  await usuario.selectOptions(screen.getByLabelText(/^producto$/i), CERVEZA_B_ID)
  await screen.findByRole('option', { name: 'Caja x12' })
  await usuario.selectOptions(screen.getByLabelText(/^presentaci[oó]n$/i), CAJA_X12_ID)
  await usuario.type(screen.getByLabelText(/^cantidad$/i), '1')
  await usuario.type(screen.getByLabelText(/^valor$/i), '18000')
  await usuario.click(screen.getByLabelText(/incluye iva/i))
}

function cuerpoDelPost(indice = 0): Record<string, unknown> {
  const llamada = llamadas(apiFetchMock, 'POST', '/compras')[indice]
  return JSON.parse(String(llamada?.init.body)) as Record<string, unknown>
}

describe('CompraFormScreen (tarea 12.1)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
  })
  afterEach(() => {
    vi.clearAllMocks()
  })

  it('sin REGISTRAR_COMPRA muestra la falta de permiso y no pide nada', async () => {
    montarApi(apiFetchMock)
    renderPantalla('VEN')

    expect(await screen.findByText(/no ten[eé]s permiso para registrar compras/i)).toBeInTheDocument()
    expect(llamadas(apiFetchMock, 'GET', '/proveedores/opciones')).toHaveLength(0)
  })

  it('ofrece proveedores activos y, al elegir uno, pide al servidor los productos de ese proveedor', async () => {
    montarApi(apiFetchMock)
    const usuario = userEvent.setup()
    renderPantalla()

    await screen.findByRole('option', { name: 'Bodega Sur' })
    await usuario.selectOptions(screen.getByLabelText(/^proveedor$/i), PROVEEDOR_ID)

    await screen.findByRole('option', { name: 'Cerveza B' })
    const pedidos = llamadas(apiFetchMock, 'GET', '/catalogo/productos')
    expect(pedidos.length).toBeGreaterThan(0)
    expect(pedidos.every((p) => p.url.searchParams.get('proveedor_id') === PROVEEDOR_ID)).toBe(true)
    expect(pedidos.every((p) => p.url.searchParams.get('activo') === 'true')).toBe(true)
  })

  it('solo ofrece presentaciones de compra: Vino A muestra Botella y no Caja x6', async () => {
    montarApi(apiFetchMock)
    const usuario = userEvent.setup()
    renderPantalla()
    await elegirCabecera(usuario)

    await screen.findByRole('option', { name: 'Vino A' })
    await usuario.selectOptions(screen.getByLabelText(/^producto$/i), VINO_A_ID)

    const select = await screen.findByLabelText(/^presentaci[oó]n$/i)
    await waitFor(() =>
      expect(within(select).getAllByRole('option').map((o) => o.textContent)).toEqual(['Elegí una presentación', 'Botella']),
    )
  })

  it('vista previa de Caja x12 con IVA: costo base 1.239,669421 e importe neto 14.876,03; total prellenado 18000.00', async () => {
    montarApi(apiFetchMock)
    const usuario = userEvent.setup()
    renderPantalla()
    await elegirCabecera(usuario)

    await cargarCajaX12ConIva(usuario)

    const vista = await screen.findByTestId('linea-0-vista-previa')
    await waitFor(() => expect(vista).toHaveTextContent('1.239,669421'))
    expect(vista).toHaveTextContent('14.876,03')
    expect(vista).toHaveTextContent('12 unidades (1 Caja x12)')
    expect(screen.getByTestId('total-neto')).toHaveTextContent('14.876,03')
    expect(screen.getByTestId('iva-sugerido')).toHaveTextContent('3.123,97')
    expect(screen.getByLabelText(/total de factura/i)).toHaveValue('18000.00')
  })

  it('el total de factura es editable y lo editado se envía; el neto no cambia', async () => {
    montarApi(apiFetchMock, [
      { metodo: 'POST', ruta: '/compras', responder: () => ({ status: 201, cuerpo: COMPRA_CONFIRMADA }) },
    ])
    const usuario = userEvent.setup()
    renderPantalla()
    await elegirCabecera(usuario)
    await cargarCajaX12ConIva(usuario)
    await waitFor(() => expect(screen.getByLabelText(/total de factura/i)).toHaveValue('18000.00'))

    const total = screen.getByLabelText(/total de factura/i)
    await usuario.clear(total)
    await usuario.type(total, '18000.50')
    expect(screen.getByTestId('total-neto')).toHaveTextContent('14.876,03')
    await usuario.click(screen.getByRole('button', { name: /confirmar compra/i }))

    await waitFor(() => expect(llamadas(apiFetchMock, 'POST', '/compras')).toHaveLength(1))
    const cuerpo = cuerpoDelPost()
    expect(cuerpo.total_factura).toBe('18000.50')
    expect(cuerpo.proveedor_id).toBe(PROVEEDOR_ID)
    expect(cuerpo.ubicacion_id).toBe(UBICACION_ID)
    expect(cuerpo.condicion).toBe('CREDITO')
    expect(cuerpo.lineas).toEqual([
      { producto_id: CERVEZA_B_ID, presentacion_id: CAJA_X12_ID, cantidad: '1', valor: '18000.00', incluye_iva: true, bonificacion: '0.000000' },
    ])
  })

  it('de contado con medios que no suman el total: confirmar queda deshabilitado y se ve el faltante', async () => {
    montarApi(apiFetchMock)
    const usuario = userEvent.setup()
    renderPantalla()
    await elegirCabecera(usuario)
    await cargarCajaX12ConIva(usuario)
    await waitFor(() => expect(screen.getByLabelText(/total de factura/i)).toHaveValue('18000.00'))

    await usuario.selectOptions(screen.getByLabelText(/condici[oó]n/i), 'CONTADO')
    await usuario.click(screen.getByRole('button', { name: /agregar medio/i }))
    await screen.findByRole('option', { name: 'Efectivo' })
    await usuario.selectOptions(screen.getByLabelText(/^medio de pago$/i), EFECTIVO_ID)
    await usuario.type(screen.getByLabelText(/^importe del medio$/i), '10000')

    expect(screen.getByTestId('faltante-medios')).toHaveTextContent(/faltan\s+8\.000,00/i)
    expect(screen.getByRole('button', { name: /confirmar compra/i })).toBeDisabled()

    await usuario.clear(screen.getByLabelText(/^importe del medio$/i))
    await usuario.type(screen.getByLabelText(/^importe del medio$/i), '18000')

    await waitFor(() => expect(screen.getByRole('button', { name: /confirmar compra/i })).toBeEnabled())
  })

  it('un error del servidor en la línea 2 se muestra junto a esa línea y conserva el formulario', async () => {
    montarApi(apiFetchMock, [
      {
        metodo: 'POST',
        ruta: '/compras',
        responder: () => ({ status: 422, cuerpo: { title: 'La cantidad no es válida.', codigo: 'CANTIDAD_INVALIDA', linea: 1 } }),
      },
    ])
    const usuario = userEvent.setup()
    renderPantalla()
    await elegirCabecera(usuario)
    await cargarCajaX12ConIva(usuario)
    await usuario.click(screen.getByRole('button', { name: /agregar l[ií]nea/i }))
    const productos = screen.getAllByLabelText(/^producto$/i)
    await usuario.selectOptions(productos[1] as HTMLSelectElement, VINO_A_ID)
    await waitFor(() => expect(within(screen.getAllByLabelText(/^presentaci[oó]n$/i)[1] as HTMLSelectElement).queryByRole('option', { name: 'Botella' })).not.toBeNull())
    await usuario.selectOptions(screen.getAllByLabelText(/^presentaci[oó]n$/i)[1] as HTMLSelectElement, BOTELLA_ID)
    await usuario.type(screen.getAllByLabelText(/^cantidad$/i)[1] as HTMLInputElement, '3')
    await usuario.type(screen.getAllByLabelText(/^valor$/i)[1] as HTMLInputElement, '1000')
    await waitFor(() => expect(screen.getByRole('button', { name: /confirmar compra/i })).toBeEnabled())

    await usuario.click(screen.getByRole('button', { name: /confirmar compra/i }))

    const linea2 = await screen.findByTestId('linea-1')
    expect(await within(linea2).findByText('La cantidad no es válida.')).toBeInTheDocument()
    expect(within(screen.getByTestId('linea-0')).queryByText('La cantidad no es válida.')).not.toBeInTheDocument()
    expect(screen.getAllByLabelText(/^valor$/i)[0]).toHaveValue('18000')
    expect(screen.getAllByLabelText(/^cantidad$/i)[1]).toHaveValue('3')
  })

  it('tras un error de red el reintento reenvía el mismo Operation-Id; si cambia el contenido, uno nuevo', async () => {
    let intento = 0
    montarApi(apiFetchMock, [
      {
        metodo: 'POST',
        ruta: '/compras',
        responder: () => {
          intento += 1
          if (intento <= 3) throw new TypeError('Failed to fetch')
          return { status: 201, cuerpo: COMPRA_CONFIRMADA }
        },
      },
    ])
    const usuario = userEvent.setup()
    renderPantalla()
    await elegirCabecera(usuario)
    await cargarCajaX12ConIva(usuario)
    await waitFor(() => expect(screen.getByRole('button', { name: /confirmar compra/i })).toBeEnabled())

    await usuario.click(screen.getByRole('button', { name: /confirmar compra/i }))
    await waitFor(() => expect(llamadas(apiFetchMock, 'POST', '/compras').length).toBeGreaterThanOrEqual(3))
    await screen.findByRole('alert')
    const ids = llamadas(apiFetchMock, 'POST', '/compras').map((l) => new Headers(l.init.headers).get('Operation-Id'))
    expect(new Set(ids).size).toBe(1)

    await usuario.type(screen.getByLabelText(/n[uú]mero de comprobante/i), 'A-0001')
    await waitFor(() => expect(screen.getByRole('button', { name: /confirmar compra/i })).toBeEnabled())
    await usuario.click(screen.getByRole('button', { name: /confirmar compra/i }))

    await waitFor(() => expect(llamadas(apiFetchMock, 'POST', '/compras').length).toBeGreaterThan(ids.length))
    const todos = llamadas(apiFetchMock, 'POST', '/compras').map((l) => new Headers(l.init.headers).get('Operation-Id'))
    expect(todos[todos.length - 1]).not.toBe(ids[0])
  })

  describe('organización que no computa crédito fiscal (11b, tarea 7.2, CST-06)', () => {
    async function cargarCajaX12ValorPagado(usuario: ReturnType<typeof userEvent.setup>) {
      await screen.findByRole('option', { name: 'Cerveza B' })
      await usuario.selectOptions(screen.getByLabelText(/^producto$/i), CERVEZA_B_ID)
      await screen.findByRole('option', { name: 'Caja x12' })
      await usuario.selectOptions(screen.getByLabelText(/^presentaci[oó]n$/i), CAJA_X12_ID)
      await usuario.type(screen.getByLabelText(/^cantidad$/i), '1')
      await usuario.type(screen.getByLabelText(/^valor pagado$/i), '21780')
    }

    it('un monotributista no ve "Incluye IVA" ni "IVA sugerido" y ve "Valor pagado"', async () => {
      montarApi(apiFetchMock, [reglaFiscal('MONOTRIBUTO')])
      const usuario = userEvent.setup()
      renderPantalla()
      await elegirCabecera(usuario)

      await screen.findByLabelText(/^valor pagado$/i)
      expect(screen.queryByLabelText(/incluye iva/i)).not.toBeInTheDocument()
      expect(screen.queryByText(/iva sugerido/i)).not.toBeInTheDocument()
      expect(screen.queryByLabelText(/^valor$/i)).not.toBeInTheDocument()
    })

    it('Caja x12 a 21.780: costo base 1.815,000000, neto y total de factura prellenado 21.780,00; envía incluye_iva = false', async () => {
      montarApi(apiFetchMock, [
        reglaFiscal('MONOTRIBUTO'),
        { metodo: 'POST', ruta: '/compras', responder: () => ({ status: 201, cuerpo: COMPRA_CONFIRMADA }) },
      ])
      const usuario = userEvent.setup()
      renderPantalla()
      await elegirCabecera(usuario)

      await cargarCajaX12ValorPagado(usuario)

      const vista = await screen.findByTestId('linea-0-vista-previa')
      await waitFor(() => expect(vista).toHaveTextContent('1.815,000000'))
      expect(screen.getByTestId('total-neto')).toHaveTextContent('21.780,00')
      expect(screen.getByLabelText(/total de factura/i)).toHaveValue('21780.00')
      expect(screen.getByTestId('total-neto').parentElement).toHaveTextContent(/^Total:\s*21\.780,00$/)

      await usuario.click(screen.getByRole('button', { name: /confirmar compra/i }))
      await waitFor(() => expect(llamadas(apiFetchMock, 'POST', '/compras')).toHaveLength(1))
      const cuerpo = cuerpoDelPost()
      expect(cuerpo.total_factura).toBe('21780.00')
      expect(cuerpo.lineas).toEqual([
        { producto_id: CERVEZA_B_ID, presentacion_id: CAJA_X12_ID, cantidad: '1', valor: '21780.00', incluye_iva: false, bonificacion: '0.000000' },
      ])
    })

    it('un exento tampoco ve la casilla de IVA', async () => {
      montarApi(apiFetchMock, [reglaFiscal('EXENTO')])
      renderPantalla()

      await screen.findByLabelText(/^valor pagado$/i)
      expect(screen.queryByLabelText(/incluye iva/i)).not.toBeInTheDocument()
    })

    it('un inscripto sigue viendo "Incluye IVA", "IVA sugerido" y "Valor" (TR-06)', async () => {
      montarApi(apiFetchMock, [reglaFiscal('RESPONSABLE_INSCRIPTO')])
      renderPantalla()

      expect(await screen.findByLabelText(/incluye iva/i)).toBeInTheDocument()
      expect(screen.getByText(/iva sugerido/i)).toBeInTheDocument()
      expect(screen.getByText(/total neto:/i)).toBeInTheDocument()
      expect(screen.getByLabelText(/^valor$/i)).toBeInTheDocument()
      expect(screen.queryByLabelText(/^valor pagado$/i)).not.toBeInTheDocument()
    })

    it('INCLUYE_IVA_NO_APLICA del servidor se muestra junto a la línea', async () => {
      montarApi(apiFetchMock, [
        reglaFiscal('MONOTRIBUTO'),
        {
          metodo: 'POST',
          ruta: '/compras',
          responder: () => ({
            status: 422,
            cuerpo: { title: 'Una organización que no computa crédito fiscal no informa IVA incluido.', codigo: 'INCLUYE_IVA_NO_APLICA', linea: 0 },
          }),
        },
      ])
      const usuario = userEvent.setup()
      renderPantalla()
      await elegirCabecera(usuario)
      await cargarCajaX12ValorPagado(usuario)
      await waitFor(() => expect(screen.getByRole('button', { name: /confirmar compra/i })).toBeEnabled())

      await usuario.click(screen.getByRole('button', { name: /confirmar compra/i }))

      const linea = await screen.findByTestId('linea-0')
      expect(await within(linea).findByText(/no computa crédito fiscal/i)).toBeInTheDocument()
    })

    it('mientras la condición no llega no se puede confirmar', async () => {
      montarApi(apiFetchMock, [
        { metodo: 'GET', ruta: '/configuracion/fiscal', responder: () => ({ status: 500, cuerpo: { title: 'Falló' } }) },
      ])
      const usuario = userEvent.setup()
      renderPantalla()
      await elegirCabecera(usuario)

      expect(screen.getByRole('button', { name: /confirmar compra/i })).toBeDisabled()
      expect(await screen.findByText(/no se pudo leer la condici[oó]n frente al iva/i)).toBeInTheDocument()
    })
  })
})
