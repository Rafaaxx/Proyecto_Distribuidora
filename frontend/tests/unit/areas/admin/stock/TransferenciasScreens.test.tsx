import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }))
vi.mock('../../../../../src/lib/api/httpClient', () => ({ apiFetch: apiFetchMock }))

import { TransferenciaDetalleScreen } from '../../../../../src/areas/admin/stock/TransferenciaDetalleScreen'
import { TransferenciaFormScreen } from '../../../../../src/areas/admin/stock/TransferenciaFormScreen'
import { TransferenciasListScreen } from '../../../../../src/areas/admin/stock/TransferenciasListScreen'
import { enrutar, llamadas } from '../../../utils/enrutarApi'
import { queryClientConYo, type RolDePrueba } from '../../../utils/permisosDePrueba'

const DEPOSITO = '11111111-1111-4111-8111-111111111111'
const CAMIONETA = '22222222-2222-4222-8222-222222222222'
const VINO = '33333333-3333-4333-8333-333333333333'
const CERVEZA = '55555555-5555-4555-8555-555555555555'
const TRANSFERENCIA = '66666666-6666-4666-8666-666666666666'
const MOTIVO = '77777777-7777-4777-8777-777777777777'
const YO = 'usuario-de-prueba'

const UBICACIONES = {
  items: [
    { id: DEPOSITO, nombre: 'Depósito', tipo: 'DEPOSITO', requiere_toma: false, activo: true, actualizado_en: '2026-01-01T00:00:00Z' },
    { id: CAMIONETA, nombre: 'Camioneta 1', tipo: 'VEHICULO', requiere_toma: true, activo: true, actualizado_en: '2026-01-01T00:00:00Z' },
  ],
  cursor_siguiente: null,
}

function saldo(productoId: string, codigo: string, nombre: string, cantidad: number) {
  return {
    producto_id: productoId,
    producto_codigo: codigo,
    producto_nombre: nombre,
    cantidad_base: cantidad,
    unidades_referencia: 6,
    nombre_referencia: 'Caja x6',
  }
}

function detalle(estado: 'CONFIRMADA' | 'ANULADA', usuarioId = YO) {
  return {
    id: TRANSFERENCIA,
    estado,
    ubicacion_origen_id: DEPOSITO,
    ubicacion_origen_nombre: 'Depósito',
    ubicacion_destino_id: CAMIONETA,
    ubicacion_destino_nombre: 'Camioneta 1',
    observacion: 'Carga del lunes',
    usuario_id: usuarioId,
    usuario_nombre: 'Vendedora Vera',
    occurred_at: '2026-04-10T15:00:00Z',
    registered_at: '2026-04-10T15:00:00Z',
    lineas: [
      {
        orden: 1,
        producto_id: VINO,
        producto_codigo: 'COD-1',
        producto_nombre: 'Vino A',
        cantidad_base: 48,
        unidades_referencia: 6,
        nombre_referencia: 'Caja x6',
      },
    ],
    anulacion:
      estado === 'ANULADA'
        ? {
            motivo_id: MOTIVO,
            motivo_nombre: 'Error de carga',
            anulada_en: '2026-04-11T15:00:00Z',
            anulada_por_id: YO,
            anulada_por_nombre: 'Vendedora Vera',
          }
        : null,
  }
}

function UbicacionActual() {
  const { pathname } = useLocation()
  return <p data-testid="ruta">{pathname}</p>
}

function renderEn(ruta: string, rol: RolDePrueba) {
  return render(
    <QueryClientProvider client={queryClientConYo(rol)}>
      <MemoryRouter initialEntries={[ruta]}>
        <UbicacionActual />
        <Routes>
          <Route path="/admin/stock/transferencias" element={<TransferenciasListScreen />} />
          <Route path="/admin/stock/transferencias/nueva" element={<TransferenciaFormScreen />} />
          <Route path="/admin/stock/transferencias/:transferenciaId" element={<TransferenciaDetalleScreen />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

function reglasBase(saldosDeposito = [saldo(VINO, 'COD-1', 'Vino A', 120)]) {
  return [
    { ruta: '/stock/ubicaciones', responder: () => ({ status: 200, cuerpo: UBICACIONES }) },
    {
      ruta: `/stock/ubicaciones/${DEPOSITO}/saldos`,
      responder: () => ({ status: 200, cuerpo: { items: saldosDeposito, cursor_siguiente: null } }),
    },
    {
      ruta: `/stock/ubicaciones/${CAMIONETA}/saldos`,
      responder: () => ({ status: 200, cuerpo: { items: [], cursor_siguiente: null } }),
    },
  ]
}

async function cargarFormulario(usuario: ReturnType<typeof userEvent.setup>) {
  await screen.findByLabelText('Origen')
  await usuario.selectOptions(screen.getByLabelText('Origen'), DEPOSITO)
  await usuario.selectOptions(screen.getByLabelText('Destino'), CAMIONETA)
}

async function elegirProducto(usuario: ReturnType<typeof userEvent.setup>, productoId: string) {
  const selector = await screen.findByLabelText('Producto')
  await waitFor(() => expect(selector.querySelector(`option[value="${productoId}"]`)).not.toBeNull())
  await usuario.selectOptions(selector, productoId)
}

beforeEach(() => {
  apiFetchMock.mockReset()
})
afterEach(() => {
  vi.clearAllMocks()
})

describe('alta de transferencia (tarea 13.1; STK-07, TR-07, D7)', () => {
  it('Vendedor carga la camioneta: ve el saldo resultante, envía cantidad_base 48 y llega al detalle', async () => {
    enrutar(apiFetchMock, [
      ...reglasBase(),
      {
        metodo: 'POST',
        ruta: '/stock/transferencias',
        responder: () => ({ status: 201, cuerpo: { id: TRANSFERENCIA, estado: 'CONFIRMADA' } }),
      },
    ])
    const usuario = userEvent.setup()
    renderEn('/admin/stock/transferencias/nueva', 'VEN')

    await cargarFormulario(usuario)
    await elegirProducto(usuario, VINO)
    await usuario.type(await screen.findByLabelText('Caja x6'), '8')

    expect(await screen.findByText('Depósito: 72 unidades (12 Caja x6)')).toBeInTheDocument()
    expect(screen.getByText('Camioneta 1: 48 unidades (8 Caja x6)')).toBeInTheDocument()

    await usuario.click(screen.getByRole('button', { name: 'Registrar transferencia' }))

    await waitFor(() => expect(screen.getByTestId('ruta')).toHaveTextContent(`/admin/stock/transferencias/${TRANSFERENCIA}`))
    const envios = llamadas(apiFetchMock, 'POST', '/stock/transferencias')
    expect(envios).toHaveLength(1)
    expect(JSON.parse(String(envios[0]?.init.body))).toEqual({
      ubicacion_origen_id: DEPOSITO,
      ubicacion_destino_id: CAMIONETA,
      lineas: [{ producto_id: VINO, cantidad_base: 48 }],
    })
    expect(new Headers(envios[0]?.init.headers).get('Operation-Id')).toBeTruthy()
  })

  it('avisa que requiere conexión y no se guarda para enviar después', async () => {
    enrutar(apiFetchMock, reglasBase())
    renderEn('/admin/stock/transferencias/nueva', 'VEN')

    expect(await screen.findByText(/requiere conexión con el servidor/)).toBeInTheDocument()
  })

  it('precarga el origen desde "Transferir desde acá"', async () => {
    enrutar(apiFetchMock, reglasBase())
    renderEn(`/admin/stock/transferencias/nueva?origen=${DEPOSITO}`, 'VEN')

    await screen.findByLabelText('Origen')
    await waitFor(() => expect(screen.getByLabelText('Origen')).toHaveValue(DEPOSITO))
  })

  it('el selector ofrece solo productos con stock en el origen, también a quien puede dejar stock negativo (D7)', async () => {
    enrutar(apiFetchMock, [
      ...reglasBase([
        saldo(VINO, 'COD-1', 'Vino A', 48),
        saldo(CERVEZA, 'COD-3', 'Cerveza C', 0),
      ]),
    ])
    const usuario = userEvent.setup()
    renderEn('/admin/stock/transferencias/nueva', 'ADM')

    await cargarFormulario(usuario)
    const selector = await screen.findByLabelText('Producto')
    await within(selector).findByRole('option', { name: 'COD-1 · Vino A' })

    expect(within(selector).queryByRole('option', { name: /Agua 500/ })).not.toBeInTheDocument()
    expect(within(selector).queryByRole('option', { name: /Cerveza C/ })).not.toBeInTheDocument()
  })

  it('un resultado negativo (60 de 48) se muestra marcado', async () => {
    enrutar(apiFetchMock, reglasBase([saldo(VINO, 'COD-1', 'Vino A', 48)]))
    const usuario = userEvent.setup()
    renderEn('/admin/stock/transferencias/nueva', 'ADM')

    await cargarFormulario(usuario)
    await elegirProducto(usuario, VINO)
    await usuario.type(await screen.findByLabelText('Unidades'), '60')

    const origen = await screen.findByText(/^Depósito: -12 unidades/)
    expect(origen).toHaveTextContent('stock negativo')
    expect(origen).toHaveAttribute('data-negativo', 'true')
  })

  it('el rechazo STOCK_INSUFICIENTE se muestra junto a la línea y conserva lo cargado', async () => {
    enrutar(apiFetchMock, [
      ...reglasBase(),
      {
        metodo: 'POST',
        ruta: '/stock/transferencias',
        responder: () => ({
          status: 409,
          cuerpo: { title: 'El saldo es 120', codigo: 'STOCK_INSUFICIENTE', linea: 0 },
        }),
      },
    ])
    const usuario = userEvent.setup()
    renderEn('/admin/stock/transferencias/nueva', 'SUP')

    await cargarFormulario(usuario)
    await elegirProducto(usuario, VINO)
    await usuario.type(await screen.findByLabelText('Caja x6'), '30')
    await usuario.click(screen.getByRole('button', { name: 'Registrar transferencia' }))

    const linea = await screen.findByRole('group', { name: 'Línea 1' })
    expect(await within(linea).findByRole('alert')).toHaveTextContent(
      'No hay stock suficiente en el origen para transferir esa cantidad.',
    )
    expect(screen.getByLabelText('Caja x6')).toHaveValue('30')
    expect(screen.getByLabelText('Origen')).toHaveValue(DEPOSITO)
  })

  it('valida en el cliente: origen igual a destino no se envía', async () => {
    enrutar(apiFetchMock, reglasBase())
    const usuario = userEvent.setup()
    renderEn('/admin/stock/transferencias/nueva', 'VEN')

    await screen.findByLabelText('Origen')
    await usuario.selectOptions(screen.getByLabelText('Origen'), DEPOSITO)
    await usuario.selectOptions(screen.getByLabelText('Destino'), DEPOSITO)
    await elegirProducto(usuario, VINO)
    await usuario.type(await screen.findByLabelText('Caja x6'), '1')
    await usuario.click(screen.getByRole('button', { name: 'Registrar transferencia' }))

    expect(await screen.findByText('El origen y el destino tienen que ser distintos.')).toBeInTheDocument()
    expect(llamadas(apiFetchMock, 'POST', '/stock/transferencias')).toHaveLength(0)
  })

  it('reintenta con el mismo operation_id tras un corte de red y con otro si cambia una cantidad', async () => {
    let intentos = 0
    enrutar(apiFetchMock, [
      ...reglasBase(),
      {
        metodo: 'POST',
        ruta: '/stock/transferencias',
        responder: () => {
          intentos += 1
          if (intentos <= 6) throw new TypeError('Failed to fetch')
          return { status: 201, cuerpo: { id: TRANSFERENCIA, estado: 'CONFIRMADA' } }
        },
      },
    ])
    const usuario = userEvent.setup()
    renderEn('/admin/stock/transferencias/nueva', 'VEN')

    await cargarFormulario(usuario)
    await elegirProducto(usuario, VINO)
    await usuario.type(await screen.findByLabelText('Caja x6'), '8')

    await usuario.click(screen.getByRole('button', { name: 'Registrar transferencia' }))
    expect(await screen.findByText(/Se necesita conexión/)).toBeInTheDocument()
    await usuario.click(screen.getByRole('button', { name: 'Registrar transferencia' }))
    await waitFor(() => expect(llamadas(apiFetchMock, 'POST', '/stock/transferencias')).toHaveLength(6))

    const ids = () =>
      llamadas(apiFetchMock, 'POST', '/stock/transferencias').map(({ init }) =>
        new Headers(init.headers).get('Operation-Id'),
      )
    expect(new Set(ids()).size).toBe(1)

    await usuario.type(screen.getByLabelText('Unidades'), '1')
    await usuario.click(screen.getByRole('button', { name: 'Registrar transferencia' }))
    await waitFor(() => expect(llamadas(apiFetchMock, 'POST', '/stock/transferencias').length).toBeGreaterThan(6))
    expect(new Set(ids()).size).toBe(2)
  })
})

describe('listado de transferencias (tarea 13.1)', () => {
  const FILA = {
    id: TRANSFERENCIA,
    estado: 'CONFIRMADA',
    ubicacion_origen_id: DEPOSITO,
    ubicacion_origen_nombre: 'Depósito',
    ubicacion_destino_id: CAMIONETA,
    ubicacion_destino_nombre: 'Camioneta 1',
    observacion: null,
    usuario_id: YO,
    usuario_nombre: 'Vendedora Vera',
    occurred_at: '2026-04-10T15:00:00Z',
    cantidad_de_lineas: 2,
  }

  it('muestra cada transferencia con su estado y enlaza a su detalle', async () => {
    enrutar(apiFetchMock, [
      { ruta: '/stock/ubicaciones', responder: () => ({ status: 200, cuerpo: UBICACIONES }) },
      {
        ruta: '/stock/transferencias',
        responder: () => ({
          status: 200,
          cuerpo: { items: [FILA, { ...FILA, id: 'otra', estado: 'ANULADA' }], cursor_siguiente: null },
        }),
      },
    ])
    renderEn('/admin/stock/transferencias', 'VEN')

    const filas = await screen.findAllByRole('row')
    expect(within(filas[1] as HTMLElement).getByText('Confirmada')).toBeInTheDocument()
    expect(within(filas[2] as HTMLElement).getByText('Anulada')).toBeInTheDocument()
    expect(within(filas[1] as HTMLElement).getByText('Camioneta 1')).toBeInTheDocument()
    expect(screen.getAllByRole('link', { name: 'Ver detalle' })[0]).toHaveAttribute(
      'href',
      `/admin/stock/transferencias/${TRANSFERENCIA}`,
    )
    expect(screen.getByRole('link', { name: 'Nueva transferencia' })).toBeInTheDocument()
  })

  it('filtra por ubicación y fechas', async () => {
    enrutar(apiFetchMock, [
      { ruta: '/stock/ubicaciones', responder: () => ({ status: 200, cuerpo: UBICACIONES }) },
      { ruta: '/stock/transferencias', responder: () => ({ status: 200, cuerpo: { items: [], cursor_siguiente: null } }) },
    ])
    const usuario = userEvent.setup()
    renderEn('/admin/stock/transferencias', 'VEN')

    await screen.findByRole('option', { name: 'Camioneta 1' })
    await usuario.selectOptions(screen.getByLabelText('Ubicación'), CAMIONETA)
    await usuario.type(screen.getByLabelText('Desde'), '2026-04-01')
    await usuario.type(screen.getByLabelText('Hasta'), '2026-04-30')

    await waitFor(() => {
      const ultima = llamadas(apiFetchMock, 'GET', '/stock/transferencias').at(-1)
      expect(ultima?.url.searchParams.get('ubicacion_id')).toBe(CAMIONETA)
      expect(ultima?.url.searchParams.get('desde')).toBe('2026-04-01')
      expect(ultima?.url.searchParams.get('hasta')).toBe('2026-04-30')
    })
    expect(await screen.findByText('No hay transferencias para mostrar.')).toBeInTheDocument()
  })

  it('un usuario sin TRANSFERIR_STOCK no ve el listado', async () => {
    enrutar(apiFetchMock, [])
    renderEn('/admin/stock/transferencias', 'CON')

    expect(await screen.findByText(/No tenés permiso/)).toBeInTheDocument()
    expect(apiFetchMock).not.toHaveBeenCalled()
  })
})

describe('detalle y anulación de una transferencia (tarea 13.1 y 13.3; TR-06, D5)', () => {
  function reglasDeDetalle(opciones: { creador?: string; anulacion?: { status: number; cuerpo: unknown } | 'red' } = {}) {
    let anulada = false
    return [
      {
        ruta: `/stock/transferencias/${TRANSFERENCIA}`,
        responder: () => ({ status: 200, cuerpo: detalle(anulada ? 'ANULADA' : 'CONFIRMADA', opciones.creador ?? YO) }),
      },
      {
        ruta: '/configuracion/motivos',
        responder: () => ({ status: 200, cuerpo: { items: [{ id: MOTIVO, nombre: 'Error de carga' }] } }),
      },
      {
        metodo: 'POST',
        ruta: `/stock/transferencias/${TRANSFERENCIA}/anulacion`,
        responder: () => {
          if (opciones.anulacion === 'red') throw new TypeError('Failed to fetch')
          if (opciones.anulacion) return opciones.anulacion
          anulada = true
          return { status: 200, cuerpo: { id: TRANSFERENCIA, estado: 'ANULADA' } }
        },
      },
    ]
  }

  it('muestra las líneas en cajas + unidades, el estado y la observación', async () => {
    enrutar(apiFetchMock, reglasDeDetalle())
    renderEn(`/admin/stock/transferencias/${TRANSFERENCIA}`, 'VEN')

    const fila = (await screen.findByText('Vino A')).closest('tr') as HTMLElement
    expect(within(fila).getByText('48 unidades (8 Caja x6)')).toBeInTheDocument()
    expect(screen.getByText('Confirmada')).toBeInTheDocument()
    expect(screen.getByText(/Carga del lunes/)).toBeInTheDocument()
    expect(screen.getByText(/Depósito/)).toBeInTheDocument()
  })

  it('la Vendedora anula su transferencia: el detalle pasa a Anulada con motivo, usuario y momento, y el botón desaparece', async () => {
    enrutar(apiFetchMock, reglasDeDetalle())
    const usuario = userEvent.setup()
    renderEn(`/admin/stock/transferencias/${TRANSFERENCIA}`, 'VEN')

    await usuario.click(await screen.findByRole('button', { name: 'Anular' }))
    const dialogo = await screen.findByRole('dialog')
    expect(within(dialogo).getByText(/requiere conexión/)).toBeInTheDocument()
    await usuario.selectOptions(await within(dialogo).findByLabelText('Motivo'), MOTIVO)
    await usuario.click(within(dialogo).getByRole('button', { name: 'Confirmar anulación' }))

    const anulacion = await screen.findByTestId('anulacion')
    expect(anulacion).toHaveTextContent('Error de carga')
    expect(anulacion).toHaveTextContent('Vendedora Vera')
    expect(screen.getByText('Anulada')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Anular' })).not.toBeInTheDocument()
    const envio = llamadas(apiFetchMock, 'POST', `/stock/transferencias/${TRANSFERENCIA}/anulacion`)[0]
    expect(JSON.parse(String(envio?.init.body))).toEqual({ motivo_id: MOTIVO })
    const ambitos = llamadas(apiFetchMock, 'GET', '/configuracion/motivos').map((c) => c.url.searchParams.get('ambito'))
    expect(ambitos).toContain('ANULACION_TRANSFERENCIA')
  })

  it('"Anular" en una transferencia ajena: el Vendedor no lo ve y Administración (ANULAR_TRANSFERENCIA) sí', async () => {
    enrutar(apiFetchMock, reglasDeDetalle({ creador: 'otro-usuario' }))
    const vendedor = renderEn(`/admin/stock/transferencias/${TRANSFERENCIA}`, 'VEN')
    await screen.findByText('Vino A')
    expect(screen.queryByRole('button', { name: 'Anular' })).not.toBeInTheDocument()
    vendedor.unmount()

    apiFetchMock.mockReset()
    enrutar(apiFetchMock, reglasDeDetalle({ creador: 'otro-usuario' }))
    renderEn(`/admin/stock/transferencias/${TRANSFERENCIA}`, 'GES')
    expect(await screen.findByRole('button', { name: 'Anular' })).toBeInTheDocument()
  })

  it('una anulada no ofrece "Anular" ni siquiera a quien tiene todos los permisos', async () => {
    enrutar(apiFetchMock, [
      {
        ruta: `/stock/transferencias/${TRANSFERENCIA}`,
        responder: () => ({ status: 200, cuerpo: detalle('ANULADA') }),
      },
    ])
    renderEn(`/admin/stock/transferencias/${TRANSFERENCIA}`, 'ADM')

    expect(await screen.findByText('Anulada')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Anular' })).not.toBeInTheDocument()
  })

  it('el rechazo por stock insuficiente se muestra en el diálogo y la transferencia sigue Confirmada', async () => {
    enrutar(
      apiFetchMock,
      reglasDeDetalle({ anulacion: { status: 409, cuerpo: { title: 'x', codigo: 'STOCK_INSUFICIENTE' } } }),
    )
    const usuario = userEvent.setup()
    renderEn(`/admin/stock/transferencias/${TRANSFERENCIA}`, 'VEN')

    await usuario.click(await screen.findByRole('button', { name: 'Anular' }))
    const dialogo = await screen.findByRole('dialog')
    await usuario.selectOptions(await within(dialogo).findByLabelText('Motivo'), MOTIVO)
    await usuario.click(within(dialogo).getByRole('button', { name: 'Confirmar anulación' }))

    expect(await within(dialogo).findByRole('alert')).toHaveTextContent('No se puede anular: el stock actual')
    expect(screen.getByText('Confirmada')).toBeInTheDocument()
    expect(screen.queryByTestId('anulacion')).not.toBeInTheDocument()
  })

  it('el motivo es obligatorio para confirmar la anulación', async () => {
    enrutar(apiFetchMock, reglasDeDetalle())
    const usuario = userEvent.setup()
    renderEn(`/admin/stock/transferencias/${TRANSFERENCIA}`, 'VEN')

    await usuario.click(await screen.findByRole('button', { name: 'Anular' }))
    const dialogo = await screen.findByRole('dialog')

    expect(within(dialogo).getByRole('button', { name: 'Confirmar anulación' })).toBeDisabled()
  })

  it('reintenta la anulación con el mismo operation_id tras un corte de red', async () => {
    enrutar(apiFetchMock, reglasDeDetalle({ anulacion: 'red' }))
    const usuario = userEvent.setup()
    renderEn(`/admin/stock/transferencias/${TRANSFERENCIA}`, 'VEN')

    await usuario.click(await screen.findByRole('button', { name: 'Anular' }))
    const dialogo = await screen.findByRole('dialog')
    await usuario.selectOptions(await within(dialogo).findByLabelText('Motivo'), MOTIVO)
    await usuario.click(within(dialogo).getByRole('button', { name: 'Confirmar anulación' }))
    expect(await within(dialogo).findByRole('alert')).toHaveTextContent('Se necesita conexión')
    await usuario.click(within(dialogo).getByRole('button', { name: 'Confirmar anulación' }))
    await waitFor(() =>
      expect(llamadas(apiFetchMock, 'POST', `/stock/transferencias/${TRANSFERENCIA}/anulacion`)).toHaveLength(6),
    )

    const ids = llamadas(apiFetchMock, 'POST', `/stock/transferencias/${TRANSFERENCIA}/anulacion`).map(({ init }) =>
      new Headers(init.headers).get('Operation-Id'),
    )
    expect(new Set(ids).size).toBe(1)
  })
})
