import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }))
vi.mock('../../../../../src/lib/api/httpClient', () => ({ apiFetch: apiFetchMock }))

import { AjusteDetalleScreen } from '../../../../../src/areas/admin/stock/AjusteDetalleScreen'
import { AjusteFormScreen } from '../../../../../src/areas/admin/stock/AjusteFormScreen'
import { AjustesListScreen } from '../../../../../src/areas/admin/stock/AjustesListScreen'
import type { CodigoPermiso } from '../../../../../src/domain/identidad/permisos'
import { enrutar, llamadas, type ReglaDeApi } from '../../../utils/enrutarApi'
import { PERMISOS_POR_ROL, queryClientConYo, type RolDePrueba } from '../../../utils/permisosDePrueba'

const DEPOSITO = '11111111-1111-4111-8111-111111111111'
const VINO = '33333333-3333-4333-8333-333333333333'
const SIN_COMPRAS = '44444444-4444-4444-8444-444444444444'
const AJUSTE = '66666666-6666-4666-8666-666666666666'
const ROTURA = '77777777-7777-4777-8777-777777777777'
const ERROR_DE_CARGA = '88888888-8888-4888-8888-888888888888'
const YO = 'usuario-de-prueba'

const UBICACIONES = {
  items: [
    { id: DEPOSITO, nombre: 'Depósito', tipo: 'DEPOSITO', requiere_toma: false, activo: true, actualizado_en: '2026-01-01T00:00:00Z' },
  ],
  cursor_siguiente: null,
}
const PRODUCTOS = [
  { id: VINO, codigo: 'COD-1', nombre: 'Vino A', activo: true },
  { id: SIN_COMPRAS, codigo: 'COD-9', nombre: 'Nuevo producto', activo: true },
]

function detalleDeProducto(id: string) {
  return {
    ...(PRODUCTOS.find((p) => p.id === id) ?? {}),
    presentaciones: [{ id: `${id}-p`, producto_id: id, nombre: 'Caja x6', unidades_base: 6, es_referencia: true }],
  }
}

function saldoDeVino(cantidad: number) {
  return {
    producto_id: VINO,
    producto_codigo: 'COD-1',
    producto_nombre: 'Vino A',
    cantidad_base: cantidad,
    unidades_referencia: 6,
    nombre_referencia: 'Caja x6',
  }
}

function detalle(estado: 'CONFIRMADA' | 'ANULADA', usuarioId = 'otro-usuario') {
  return {
    id: AJUSTE,
    estado,
    ubicacion_id: DEPOSITO,
    ubicacion_nombre: 'Depósito',
    motivo_id: ROTURA,
    motivo_nombre: 'Rotura',
    observacion: 'Se cayó la tarima',
    usuario_id: usuarioId,
    usuario_nombre: 'Gestora Gómez',
    occurred_at: '2026-04-10T15:00:00Z',
    registered_at: '2026-04-10T15:00:00Z',
    lineas: [
      {
        orden: 1,
        producto_id: VINO,
        producto_codigo: 'COD-1',
        producto_nombre: 'Vino A',
        cantidad_base: -6,
        unidades_referencia: 6,
        nombre_referencia: 'Caja x6',
        costo_unitario: '1050.000000',
      },
    ],
    anulacion:
      estado === 'ANULADA'
        ? {
            motivo_id: ERROR_DE_CARGA,
            motivo_nombre: 'Error de carga',
            anulado_en: '2026-04-11T15:00:00Z',
            anulado_por_id: YO,
            anulado_por_nombre: 'Administradora Díaz',
          }
        : null,
  }
}

function UbicacionActual() {
  const { pathname } = useLocation()
  return <p data-testid="ruta">{pathname}</p>
}

function renderEn(ruta: string, rol: RolDePrueba, permisos?: CodigoPermiso[]) {
  return render(
    <QueryClientProvider client={queryClientConYo(rol, permisos ? { permisos } : {})}>
      <MemoryRouter initialEntries={[ruta]}>
        <UbicacionActual />
        <Routes>
          <Route path="/admin/stock/ajustes" element={<AjustesListScreen />} />
          <Route path="/admin/stock/ajustes/nueva" element={<AjusteFormScreen />} />
          <Route path="/admin/stock/ajustes/:ajusteId" element={<AjusteDetalleScreen />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

function reglasBase(saldoInicial = 120): ReglaDeApi[] {
  return [
    { ruta: '/stock/ubicaciones', responder: () => ({ status: 200, cuerpo: UBICACIONES }) },
    {
      ruta: `/stock/ubicaciones/${DEPOSITO}/saldos`,
      responder: () => ({ status: 200, cuerpo: { items: [saldoDeVino(saldoInicial)], cursor_siguiente: null } }),
    },
    { ruta: '/catalogo/productos', responder: () => ({ status: 200, cuerpo: { items: PRODUCTOS, cursor_siguiente: null } }) },
    { ruta: `/catalogo/productos/${VINO}`, responder: () => ({ status: 200, cuerpo: detalleDeProducto(VINO) }) },
    { ruta: `/catalogo/productos/${SIN_COMPRAS}`, responder: () => ({ status: 200, cuerpo: detalleDeProducto(SIN_COMPRAS) }) },
    {
      ruta: '/configuracion/motivos',
      responder: () => ({ status: 200, cuerpo: { items: [{ id: ROTURA, nombre: 'Rotura' }] } }),
    },
  ]
}

async function elegirProducto(usuario: ReturnType<typeof userEvent.setup>, productoId: string) {
  const selector = await screen.findByLabelText('Producto')
  await waitFor(() => expect(selector.querySelector(`option[value="${productoId}"]`)).not.toBeNull())
  await usuario.selectOptions(selector, productoId)
}

async function elegirUbicacionYMotivo(usuario: ReturnType<typeof userEvent.setup>) {
  await usuario.selectOptions(await screen.findByLabelText('Ubicación'), DEPOSITO)
  const motivo = screen.getByLabelText('Motivo')
  await waitFor(() => expect(motivo.querySelector(`option[value="${ROTURA}"]`)).not.toBeNull())
  await usuario.selectOptions(motivo, ROTURA)
}

beforeEach(() => {
  apiFetchMock.mockReset()
})
afterEach(() => {
  vi.clearAllMocks()
})

describe('alta de ajuste (tarea 13.2; STK-08, D1, D2, D3)', () => {
  it('registrar una rotura: ve 19 cajas como resultado, envía −6 y llega al detalle', async () => {
    enrutar(apiFetchMock, [
      ...reglasBase(),
      { metodo: 'POST', ruta: '/stock/ajustes', responder: () => ({ status: 201, cuerpo: { id: AJUSTE, estado: 'CONFIRMADA' } }) },
    ])
    const usuario = userEvent.setup()
    renderEn('/admin/stock/ajustes/nueva', 'ADM')

    await elegirUbicacionYMotivo(usuario)
    await elegirProducto(usuario, VINO)
    await usuario.selectOptions(screen.getByLabelText('Tipo de ajuste'), 'NEGATIVO')
    await usuario.type(await screen.findByLabelText('Caja x6'), '1')

    expect(await screen.findByText('Depósito: 114 unidades (19 Caja x6)')).toBeInTheDocument()
    await usuario.type(screen.getByLabelText('Observación'), 'Se cayó la tarima')
    await usuario.click(screen.getByRole('button', { name: 'Registrar ajuste' }))

    await waitFor(() => expect(screen.getByTestId('ruta')).toHaveTextContent(`/admin/stock/ajustes/${AJUSTE}`))
    const envio = llamadas(apiFetchMock, 'POST', '/stock/ajustes')[0]
    expect(JSON.parse(String(envio?.init.body))).toEqual({
      ubicacion_id: DEPOSITO,
      motivo_id: ROTURA,
      observacion: 'Se cayó la tarima',
      lineas: [{ producto_id: VINO, cantidad_base: -6 }],
    })
    expect(new Headers(envio?.init.headers).get('Operation-Id')).toBeTruthy()
    const ambitos = llamadas(apiFetchMock, 'GET', '/configuracion/motivos').map((c) => c.url.searchParams.get('ambito'))
    expect(ambitos).toContain('AJUSTE_STOCK')
  })

  it('un sobrante manda la cantidad positiva', async () => {
    enrutar(apiFetchMock, [
      ...reglasBase(),
      { metodo: 'POST', ruta: '/stock/ajustes', responder: () => ({ status: 201, cuerpo: { id: AJUSTE, estado: 'CONFIRMADA' } }) },
    ])
    const usuario = userEvent.setup()
    renderEn('/admin/stock/ajustes/nueva', 'GES')

    await elegirUbicacionYMotivo(usuario)
    await elegirProducto(usuario, VINO)
    await usuario.type(await screen.findByLabelText('Unidades'), '24')
    await usuario.click(screen.getByRole('button', { name: 'Registrar ajuste' }))

    await waitFor(() => expect(llamadas(apiFetchMock, 'POST', '/stock/ajustes')).toHaveLength(1))
    const envio = llamadas(apiFetchMock, 'POST', '/stock/ajustes')[0]
    expect(JSON.parse(String(envio?.init.body)).lineas).toEqual([{ producto_id: VINO, cantidad_base: 24 }])
  })

  it('el motivo es obligatorio y no se envía sin él', async () => {
    enrutar(apiFetchMock, reglasBase())
    const usuario = userEvent.setup()
    renderEn('/admin/stock/ajustes/nueva', 'ADM')

    await usuario.selectOptions(await screen.findByLabelText('Ubicación'), DEPOSITO)
    await elegirProducto(usuario, VINO)
    await usuario.type(await screen.findByLabelText('Unidades'), '3')
    await usuario.click(screen.getByRole('button', { name: 'Registrar ajuste' }))

    expect(await screen.findByText('Elegí un motivo.')).toBeInTheDocument()
    expect(llamadas(apiFetchMock, 'POST', '/stock/ajustes')).toHaveLength(0)
  })

  it('un Vendedor sin AJUSTAR_STOCK no ve el alta ni se piden datos', async () => {
    enrutar(apiFetchMock, reglasBase())
    renderEn('/admin/stock/ajustes/nueva', 'VEN')

    expect(await screen.findByText(/No tenés permiso/)).toBeInTheDocument()
    expect(apiFetchMock).not.toHaveBeenCalled()
  })

  it('ajuste positivo de un producto sin costo: explica que se carga con stock inicial o con una compra', async () => {
    enrutar(apiFetchMock, [
      ...reglasBase(),
      {
        metodo: 'POST',
        ruta: '/stock/ajustes',
        responder: () => ({ status: 409, cuerpo: { title: 'sin costo', codigo: 'PRODUCTO_SIN_COSTO', linea: 0 } }),
      },
    ])
    const usuario = userEvent.setup()
    renderEn('/admin/stock/ajustes/nueva', 'ADM')

    await elegirUbicacionYMotivo(usuario)
    await elegirProducto(usuario, SIN_COMPRAS)
    await usuario.type(await screen.findByLabelText('Unidades'), '24')
    await usuario.click(screen.getByRole('button', { name: 'Registrar ajuste' }))

    const linea = await screen.findByRole('group', { name: 'Línea 1' })
    const alerta = await within(linea).findByRole('alert')
    expect(alerta).toHaveTextContent('stock inicial')
    expect(alerta).toHaveTextContent('compra')
  })

  it('un ajuste que dejaría el saldo negativo se marca y, rechazado, muestra el motivo junto a la línea y conserva lo cargado', async () => {
    enrutar(apiFetchMock, [
      ...reglasBase(10),
      {
        metodo: 'POST',
        ruta: '/stock/ajustes',
        responder: () => ({ status: 409, cuerpo: { title: 'x', codigo: 'STOCK_INSUFICIENTE', linea: 0 } }),
      },
    ])
    const usuario = userEvent.setup()
    renderEn('/admin/stock/ajustes/nueva', 'ADM')

    await elegirUbicacionYMotivo(usuario)
    await elegirProducto(usuario, VINO)
    await usuario.selectOptions(screen.getByLabelText('Tipo de ajuste'), 'NEGATIVO')
    await usuario.type(await screen.findByLabelText('Unidades'), '11')

    const resultado = await screen.findByText(/^Depósito: -1 unidad/)
    expect(resultado).toHaveAttribute('data-negativo', 'true')

    await usuario.click(screen.getByRole('button', { name: 'Registrar ajuste' }))
    const linea = await screen.findByRole('group', { name: 'Línea 1' })
    expect(await within(linea).findByRole('alert')).toHaveTextContent('Un ajuste no puede dejar stock negativo.')
    expect(screen.getByLabelText('Unidades')).toHaveValue('11')
  })

  it('regularizar un saldo negativo: abre con la ubicación, el producto y +12 precargados y el resultado en 0', async () => {
    enrutar(apiFetchMock, reglasBase(-12))
    renderEn(`/admin/stock/ajustes/nueva?ubicacion=${DEPOSITO}&producto=${VINO}&cantidad=12`, 'ADM')

    expect(await screen.findByLabelText('Ubicación')).toHaveValue(DEPOSITO)
    expect(await screen.findByLabelText('Producto')).toHaveValue(VINO)
    expect(screen.getByLabelText('Tipo de ajuste')).toHaveValue('POSITIVO')
    expect(screen.getByLabelText('Unidades')).toHaveValue('12')
    expect(await screen.findByText('Depósito: 0 unidades')).toBeInTheDocument()
    expect(screen.getByText(/Saldo actual en Depósito: -12 unidades/)).toBeInTheDocument()
  })

  it('reintenta con el mismo operation_id tras un corte de red', async () => {
    enrutar(apiFetchMock, [
      ...reglasBase(),
      {
        metodo: 'POST',
        ruta: '/stock/ajustes',
        responder: () => {
          throw new TypeError('Failed to fetch')
        },
      },
    ])
    const usuario = userEvent.setup()
    renderEn('/admin/stock/ajustes/nueva', 'ADM')

    await elegirUbicacionYMotivo(usuario)
    await elegirProducto(usuario, VINO)
    await usuario.type(await screen.findByLabelText('Unidades'), '3')
    await usuario.click(screen.getByRole('button', { name: 'Registrar ajuste' }))
    expect(await screen.findByText(/Se necesita conexión/)).toBeInTheDocument()
    await usuario.click(screen.getByRole('button', { name: 'Registrar ajuste' }))
    await waitFor(() => expect(llamadas(apiFetchMock, 'POST', '/stock/ajustes')).toHaveLength(6))

    const ids = llamadas(apiFetchMock, 'POST', '/stock/ajustes').map(({ init }) =>
      new Headers(init.headers).get('Operation-Id'),
    )
    expect(new Set(ids).size).toBe(1)
  })
})

describe('listado de ajustes (tarea 13.2)', () => {
  const FILA = {
    id: AJUSTE,
    estado: 'CONFIRMADA',
    ubicacion_id: DEPOSITO,
    ubicacion_nombre: 'Depósito',
    motivo_id: ROTURA,
    motivo_nombre: 'Rotura',
    observacion: null,
    usuario_id: YO,
    usuario_nombre: 'Gestora Gómez',
    occurred_at: '2026-04-10T15:00:00Z',
    cantidad_de_lineas: 1,
  }

  it('muestra motivo y estado de cada ajuste y enlaza a su detalle', async () => {
    enrutar(apiFetchMock, [
      ...reglasBase(),
      {
        ruta: '/stock/ajustes',
        responder: () => ({
          status: 200,
          cuerpo: { items: [FILA, { ...FILA, id: 'otro', estado: 'ANULADA' }], cursor_siguiente: null },
        }),
      },
    ])
    renderEn('/admin/stock/ajustes', 'ADM')

    const filas = await screen.findAllByRole('row')
    expect(within(filas[1] as HTMLElement).getByText('Rotura')).toBeInTheDocument()
    expect(within(filas[1] as HTMLElement).getByText('Confirmada')).toBeInTheDocument()
    expect(within(filas[2] as HTMLElement).getByText('Anulada')).toBeInTheDocument()
    expect(screen.getAllByRole('link', { name: 'Ver detalle' })[0]).toHaveAttribute('href', `/admin/stock/ajustes/${AJUSTE}`)
    expect(screen.getByRole('link', { name: 'Nuevo ajuste' })).toBeInTheDocument()
  })

  it('filtra por ubicación, motivo y fechas', async () => {
    enrutar(apiFetchMock, [
      ...reglasBase(),
      { ruta: '/stock/ajustes', responder: () => ({ status: 200, cuerpo: { items: [], cursor_siguiente: null } }) },
    ])
    const usuario = userEvent.setup()
    renderEn('/admin/stock/ajustes', 'ADM')

    await screen.findByRole('option', { name: 'Depósito' })
    await usuario.selectOptions(screen.getByLabelText('Ubicación'), DEPOSITO)
    await waitFor(() => expect(screen.getByLabelText('Motivo').querySelector(`option[value="${ROTURA}"]`)).not.toBeNull())
    await usuario.selectOptions(screen.getByLabelText('Motivo'), ROTURA)
    await usuario.type(screen.getByLabelText('Desde'), '2026-04-01')

    await waitFor(() => {
      const ultima = llamadas(apiFetchMock, 'GET', '/stock/ajustes').at(-1)
      expect(ultima?.url.searchParams.get('ubicacion_id')).toBe(DEPOSITO)
      expect(ultima?.url.searchParams.get('motivo_id')).toBe(ROTURA)
      expect(ultima?.url.searchParams.get('desde')).toBe('2026-04-01')
    })
    expect(await screen.findByText('No hay ajustes para mostrar.')).toBeInTheDocument()
  })

  it('"Ajustes" no se ofrece a un Vendedor: la pantalla no pide nada', async () => {
    enrutar(apiFetchMock, [])
    renderEn('/admin/stock/ajustes', 'VEN')

    expect(await screen.findByText(/No tenés permiso/)).toBeInTheDocument()
    expect(apiFetchMock).not.toHaveBeenCalled()
  })
})

describe('detalle y anulación de un ajuste (tarea 13.2 y 13.3; TR-06, D5)', () => {
  function reglasDeDetalle(opciones: { anulacion?: { status: number; cuerpo: unknown } } = {}): ReglaDeApi[] {
    let anulado = false
    return [
      { ruta: `/stock/ajustes/${AJUSTE}`, responder: () => ({ status: 200, cuerpo: detalle(anulado ? 'ANULADA' : 'CONFIRMADA') }) },
      {
        ruta: '/configuracion/motivos',
        responder: () => ({ status: 200, cuerpo: { items: [{ id: ERROR_DE_CARGA, nombre: 'Error de carga' }] } }),
      },
      {
        metodo: 'POST',
        ruta: `/stock/ajustes/${AJUSTE}/anulacion`,
        responder: () => {
          if (opciones.anulacion) return opciones.anulacion
          anulado = true
          return { status: 200, cuerpo: { id: AJUSTE, estado: 'ANULADA' } }
        },
      },
    ]
  }

  it('muestra motivo, estado, observación y la cantidad con signo en cajas + unidades', async () => {
    enrutar(apiFetchMock, reglasDeDetalle())
    renderEn(`/admin/stock/ajustes/${AJUSTE}`, 'ADM')

    const fila = (await screen.findByText('Vino A')).closest('tr') as HTMLElement
    expect(within(fila).getByText('-6 unidades (-1 Caja x6)')).toBeInTheDocument()
    expect(screen.getByText('Confirmada')).toBeInTheDocument()
    expect(screen.getByText(/Motivo: Rotura/)).toBeInTheDocument()
    expect(screen.getByText(/Se cayó la tarima/)).toBeInTheDocument()
  })

  it('el costo se ve solo con VER_COSTOS', async () => {
    enrutar(apiFetchMock, reglasDeDetalle())
    const con = renderEn(`/admin/stock/ajustes/${AJUSTE}`, 'ADM')
    await screen.findByText('Vino A')
    expect(screen.getByRole('columnheader', { name: 'Costo unitario' })).toBeInTheDocument()
    expect(screen.getByText('$ 1.050,000000')).toBeInTheDocument()
    con.unmount()

    apiFetchMock.mockReset()
    enrutar(apiFetchMock, reglasDeDetalle())
    const sinCostos = PERMISOS_POR_ROL.GES.filter((p) => p !== 'VER_COSTOS')
    renderEn(`/admin/stock/ajustes/${AJUSTE}`, 'GES', sinCostos)
    await screen.findByText('Vino A')
    expect(screen.queryByRole('columnheader', { name: 'Costo unitario' })).not.toBeInTheDocument()
    expect(screen.queryByText('$ 1.050,000000')).not.toBeInTheDocument()
  })

  it('un usuario de Administración anula un ajuste cargado por otro: pasa a Anulada y el botón desaparece', async () => {
    enrutar(apiFetchMock, reglasDeDetalle())
    const usuario = userEvent.setup()
    renderEn(`/admin/stock/ajustes/${AJUSTE}`, 'GES')

    await usuario.click(await screen.findByRole('button', { name: 'Anular' }))
    const dialogo = await screen.findByRole('dialog')
    expect(within(dialogo).getByText(/requiere conexión/)).toBeInTheDocument()
    await usuario.selectOptions(await within(dialogo).findByLabelText('Motivo'), ERROR_DE_CARGA)
    await usuario.click(within(dialogo).getByRole('button', { name: 'Confirmar anulación' }))

    const anulacion = await screen.findByTestId('anulacion')
    expect(anulacion).toHaveTextContent('Error de carga')
    expect(anulacion).toHaveTextContent('Administradora Díaz')
    expect(screen.getByText('Anulada')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Anular' })).not.toBeInTheDocument()
    const envio = llamadas(apiFetchMock, 'POST', `/stock/ajustes/${AJUSTE}/anulacion`)[0]
    expect(JSON.parse(String(envio?.init.body))).toEqual({ motivo_id: ERROR_DE_CARGA })
    const ambitos = llamadas(apiFetchMock, 'GET', '/configuracion/motivos').map((c) => c.url.searchParams.get('ambito'))
    expect(ambitos).toContain('ANULACION_AJUSTE')
  })

  it('sin AJUSTAR_STOCK no se ve el ajuste ni "Anular", ni siquiera con ANULAR_TRANSFERENCIA', async () => {
    enrutar(apiFetchMock, reglasDeDetalle())
    renderEn(`/admin/stock/ajustes/${AJUSTE}`, 'VEN', ['TRANSFERIR_STOCK', 'ANULAR_TRANSFERENCIA'])

    expect(await screen.findByText(/No tenés permiso/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Anular' })).not.toBeInTheDocument()
  })

  it('un ajuste anulado no ofrece "Anular"', async () => {
    enrutar(apiFetchMock, [{ ruta: `/stock/ajustes/${AJUSTE}`, responder: () => ({ status: 200, cuerpo: detalle('ANULADA') }) }])
    renderEn(`/admin/stock/ajustes/${AJUSTE}`, 'ADM')

    expect(await screen.findByText('Anulada')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Anular' })).not.toBeInTheDocument()
  })

  it('el rechazo de la anulación (producto inactivo) se muestra en el diálogo y el ajuste sigue Confirmado', async () => {
    enrutar(
      apiFetchMock,
      reglasDeDetalle({ anulacion: { status: 409, cuerpo: { title: 'x', codigo: 'PRODUCTO_INACTIVO' } } }),
    )
    const usuario = userEvent.setup()
    renderEn(`/admin/stock/ajustes/${AJUSTE}`, 'ADM')

    await usuario.click(await screen.findByRole('button', { name: 'Anular' }))
    const dialogo = await screen.findByRole('dialog')
    await usuario.selectOptions(await within(dialogo).findByLabelText('Motivo'), ERROR_DE_CARGA)
    await usuario.click(within(dialogo).getByRole('button', { name: 'Confirmar anulación' }))

    expect(await within(dialogo).findByRole('alert')).toHaveTextContent('producto inactivo')
    expect(screen.getByText('Confirmada')).toBeInTheDocument()
  })
})
