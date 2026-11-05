import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }))
vi.mock('../../../../../src/lib/api/httpClient', () => ({ apiFetch: apiFetchMock }))

import StockArea from '../../../../../src/areas/admin/stock/StockArea'
import { enrutar, llamadas, type ReglaDeApi } from '../../../utils/enrutarApi'
import { queryClientConYo, type RolDePrueba } from '../../../utils/permisosDePrueba'

/**
 * Change 24, tarea 12.1 (D2, D9, D11; cita RUT-05, RUT-06, CAT-08, INV-04, INV-06):
 * `/admin/stock/jornadas/:id/rendicion`. Esperado en cajas y unidades, contado, diferencia al
 * escribir, «Agregar producto», observación, confirmación con y sin diferencias, `ESPERADO_DIFIERE`
 * que recarga y marca, `CONTEO_INCOMPLETO` con los productos y el mismo `operation_id` al reintentar.
 */
const CAMIONETA_1 = '22222222-2222-4222-8222-222222222221'
const JORNADA = '33333333-3333-4333-8333-333333333333'
const JUAN = '44444444-4444-4444-8444-444444444444'
const DISPOSITIVO = '55555555-5555-4555-8555-555555555555'
const VINO = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1'
const GASEOSA = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa2'
const ACEITE = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa3'
const VIEJO = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa4'

function detalle(estado: string, entregada: boolean) {
  return {
    id: JORNADA,
    ubicacion_id: CAMIONETA_1,
    ubicacion_nombre: 'Camioneta 1',
    usuario_id: JUAN,
    usuario_nombre: 'Juan',
    dispositivo_id: DISPOSITIVO,
    estado,
    abierta_en: '2026-04-10T11:00:00Z',
    entregada_en: entregada ? '2026-04-10T19:30:00Z' : null,
    rendida_en: null,
    rendida_por_id: null,
    rendida_por_nombre: null,
    cerrada_en: null,
    cerrada_por_id: null,
    cerrada_por_nombre: null,
    liberada_en: null,
    liberada_por_id: null,
    liberada_por_nombre: null,
    motivo_liberacion_id: null,
    motivo_liberacion_nombre: null,
    observacion_liberacion: null,
  }
}

const DINERO_VACIO = {
  ventas: { cantidad: 0, total: '0.00' },
  anuladas: { cantidad: 0, total: '0.00' },
  cobranzas: { cantidad: 0, total: '0.00', por_medio: [] },
  cobranzas_anuladas: { cantidad: 0, total: '0.00', por_medio: [] },
}

function linea(productoId: string, esperado: number) {
  return { producto_id: productoId, al_abrir: esperado, ingresos: 0, ventas: 0, anulaciones: 0, otros: 0, esperado, contado: null, diferencia: null }
}

function resumen(esperadoVino: number) {
  return {
    jornada_id: JORNADA,
    estado: 'ABIERTA',
    con_conteo: false,
    rendida_en: null,
    lineas: [linea(VINO, esperadoVino), linea(GASEOSA, 12)],
    dinero: DINERO_VACIO,
    despues_de_la_rendicion: null,
  }
}

const PRODUCTOS = {
  items: [
    { id: VINO, codigo: 'V1', nombre: 'Vino A', activo: true },
    { id: GASEOSA, codigo: 'G1', nombre: 'Gaseosa', activo: true },
    { id: ACEITE, codigo: 'A1', nombre: 'Aceite', activo: true },
    { id: VIEJO, codigo: 'X1', nombre: 'Producto viejo', activo: false },
  ],
  cursor_siguiente: null,
}

const SALDOS = {
  items: [
    { producto_id: VINO, producto_codigo: 'V1', producto_nombre: 'Vino A', cantidad_base: 40, unidades_referencia: 6, nombre_referencia: 'Caja x6' },
    { producto_id: GASEOSA, producto_codigo: 'G1', producto_nombre: 'Gaseosa', cantidad_base: 12, unidades_referencia: null, nombre_referencia: null },
  ],
  cursor_siguiente: null,
}

function reglasBase(opciones: { estado?: string; entregada?: boolean; esperadoVino?: () => number } = {}): ReglaDeApi[] {
  const esperadoVino = opciones.esperadoVino ?? (() => 40)
  return [
    { ruta: `/stock/jornadas/${JORNADA}`, responder: () => ({ status: 200, cuerpo: detalle(opciones.estado ?? 'ABIERTA', opciones.entregada ?? true) }) },
    { ruta: `/stock/jornadas/${JORNADA}/resumen`, responder: () => ({ status: 200, cuerpo: resumen(esperadoVino()) }) },
    { ruta: '/catalogo/productos', responder: () => ({ status: 200, cuerpo: PRODUCTOS }) },
    { ruta: `/stock/ubicaciones/${CAMIONETA_1}/saldos`, responder: () => ({ status: 200, cuerpo: SALDOS }) },
    { metodo: 'POST', ruta: `/stock/jornadas/${JORNADA}/rendicion`, responder: () => ({ status: 200, cuerpo: { id: JORNADA, estado: 'EN_RENDICION' } }) },
  ]
}

function UbicacionActual() {
  const { pathname } = useLocation()
  return <p data-testid="ruta">{pathname}</p>
}

function renderEn(rol: RolDePrueba) {
  return render(
    <QueryClientProvider client={queryClientConYo(rol)}>
      <MemoryRouter initialEntries={[`/admin/stock/jornadas/${JORNADA}/rendicion`]}>
        <UbicacionActual />
        <Routes>
          <Route path="/admin/stock/*" element={<StockArea />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

const cuerpoDe = (i: number) => JSON.parse(String(llamadas(apiFetchMock, 'POST', `/stock/jornadas/${JORNADA}/rendicion`)[i]?.init.body)) as Record<string, unknown>

beforeEach(() => {
  apiFetchMock.mockReset()
})
afterEach(() => {
  vi.clearAllMocks()
})

describe('RendicionScreen: el conteo (tarea 12.1; RUT-06, CAT-08)', () => {
  it('muestra «Rendición de {ubicación}», el esperado en cajas y unidades y las ayudas', async () => {
    enrutar(apiFetchMock, reglasBase())
    renderEn('SUP')

    expect(await screen.findByRole('heading', { name: 'Rendición de Camioneta 1' })).toBeInTheDocument()
    const filaVino = (await screen.findByText('Vino A')).closest('tr') as HTMLElement
    expect(within(filaVino).getByText('40 unidades (6 Caja x6 + 4 un.)')).toBeInTheDocument()
    const filaGaseosa = screen.getByText('Gaseosa').closest('tr') as HTMLElement
    expect(within(filaGaseosa).getByText('12 unidades')).toBeInTheDocument()
    for (const columna of ['Producto', 'Esperado', 'Contado', 'Diferencia']) {
      expect(screen.getByRole('columnheader', { name: new RegExp(columna) })).toBeInTheDocument()
    }
    for (const ayuda of ['Rendición', 'Esperado', 'Diferencia']) {
      expect(screen.getByRole('button', { name: `Ayuda: ${ayuda}` })).toBeInTheDocument()
    }
  })

  it('la diferencia se calcula al escribir, en cajas y unidades, con signo (RUT-06, INV-04)', async () => {
    enrutar(apiFetchMock, reglasBase())
    const usuario = userEvent.setup()
    renderEn('SUP')

    await usuario.type(await screen.findByLabelText('Cajas de Vino A'), '6')
    await usuario.type(screen.getByLabelText('Unidades de Vino A'), '1')
    await usuario.type(screen.getByLabelText('Unidades de Gaseosa'), '15')

    const filaVino = screen.getByText('Vino A').closest('tr') as HTMLElement
    expect(within(filaVino).getByText('-3 unidades')).toBeInTheDocument()
    const filaGaseosa = screen.getByText('Gaseosa').closest('tr') as HTMLElement
    expect(within(filaGaseosa).getByText('3 unidades')).toBeInTheDocument()
  })

  it('con diferencias confirma «con {N} diferencias» y envía el conteo con lo contado y el esperado que vio', async () => {
    enrutar(apiFetchMock, reglasBase())
    const usuario = userEvent.setup()
    renderEn('SUP')

    await usuario.type(await screen.findByLabelText('Cajas de Vino A'), '6')
    await usuario.type(screen.getByLabelText('Unidades de Vino A'), '1')
    await usuario.type(screen.getByLabelText('Unidades de Gaseosa'), '15')
    await usuario.type(screen.getByLabelText('Observación'), 'Se rompió una botella')
    await usuario.click(screen.getByRole('button', { name: 'Registrar rendición' }))

    const dialogo = await screen.findByRole('dialog')
    expect(within(dialogo).getByText('¿Registrar la rendición con 2 diferencias?')).toBeInTheDocument()
    expect(llamadas(apiFetchMock, 'POST', `/stock/jornadas/${JORNADA}/rendicion`)).toHaveLength(0)
    await usuario.click(within(dialogo).getByRole('button', { name: 'Confirmar' }))

    await waitFor(() => expect(screen.getByTestId('ruta')).toHaveTextContent(`/admin/stock/jornadas/${JORNADA}`))
    expect(cuerpoDe(0)).toEqual({
      lineas: [
        { producto_id: VINO, cantidad_contada: 37, cantidad_esperada: 40 },
        { producto_id: GASEOSA, cantidad_contada: 15, cantidad_esperada: 12 },
      ],
      observacion: 'Se rompió una botella',
    })
  })

  it('sin diferencias confirma «sin diferencias» y no manda observación vacía', async () => {
    enrutar(apiFetchMock, reglasBase())
    const usuario = userEvent.setup()
    renderEn('SUP')

    await usuario.type(await screen.findByLabelText('Unidades de Vino A'), '40')
    await usuario.type(screen.getByLabelText('Unidades de Gaseosa'), '12')
    await usuario.click(screen.getByRole('button', { name: 'Registrar rendición' }))

    const dialogo = await screen.findByRole('dialog')
    expect(within(dialogo).getByText('¿Registrar la rendición sin diferencias?')).toBeInTheDocument()
    await usuario.click(within(dialogo).getByRole('button', { name: 'Confirmar' }))

    await waitFor(() => expect(llamadas(apiFetchMock, 'POST', `/stock/jornadas/${JORNADA}/rendicion`)).toHaveLength(1))
    expect(cuerpoDe(0)).not.toHaveProperty('observacion')
  })

  it('con un producto sin contar no abre la confirmación y dice «Falta contar: {productos}.» (D2)', async () => {
    enrutar(apiFetchMock, reglasBase())
    const usuario = userEvent.setup()
    renderEn('SUP')

    await usuario.type(await screen.findByLabelText('Unidades de Vino A'), '40')
    await usuario.click(screen.getByRole('button', { name: 'Registrar rendición' }))

    expect(await screen.findByText('Falta contar: Gaseosa.')).toBeInTheDocument()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(llamadas(apiFetchMock, 'POST', `/stock/jornadas/${JORNADA}/rendicion`)).toHaveLength(0)
  })

  it('un valor que no es un entero se marca en su fila y no se envía', async () => {
    enrutar(apiFetchMock, reglasBase())
    const usuario = userEvent.setup()
    renderEn('SUP')

    await usuario.type(await screen.findByLabelText('Unidades de Vino A'), '2,5')
    await usuario.type(screen.getByLabelText('Unidades de Gaseosa'), '12')
    await usuario.click(screen.getByRole('button', { name: 'Registrar rendición' }))

    expect(await screen.findByText(/entero mayor o igual a cero/)).toBeInTheDocument()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })
})

describe('RendicionScreen: «Agregar producto» (tarea 12.1; D2, D9)', () => {
  it('ofrece solo productos activos que no están en el conteo y el sobrante entra con esperado 0, en unidades', async () => {
    enrutar(apiFetchMock, reglasBase())
    const usuario = userEvent.setup()
    renderEn('SUP')

    await usuario.type(await screen.findByLabelText('Unidades de Vino A'), '40')
    await usuario.type(screen.getByLabelText('Unidades de Gaseosa'), '12')
    await usuario.click(screen.getByRole('button', { name: 'Agregar producto' }))
    const selector = await screen.findByLabelText('Agregar producto')
    const opciones = within(selector).getAllByRole('option').map((o) => o.textContent)
    expect(opciones).toContain('A1 · Aceite')
    expect(opciones.join('|')).not.toMatch(/Producto viejo|Vino A|Gaseosa/)
    await usuario.selectOptions(selector, ACEITE)

    const filaAceite = (await screen.findByLabelText('Unidades de Aceite')).closest('tr') as HTMLElement
    expect(within(filaAceite).getByText('0 unidades')).toBeInTheDocument()
    await usuario.type(screen.getByLabelText('Unidades de Aceite'), '2')
    expect(within(filaAceite).getByText('2 unidades')).toBeInTheDocument()
    await usuario.click(screen.getByRole('button', { name: 'Registrar rendición' }))
    await usuario.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Confirmar' }))

    await waitFor(() => expect(llamadas(apiFetchMock, 'POST', `/stock/jornadas/${JORNADA}/rendicion`)).toHaveLength(1))
    expect(cuerpoDe(0).lineas).toContainEqual({ producto_id: ACEITE, cantidad_contada: 2, cantidad_esperada: 0 })
  })

  it('un producto agregado sin cantidad cuenta como sin contar', async () => {
    enrutar(apiFetchMock, reglasBase())
    const usuario = userEvent.setup()
    renderEn('SUP')

    await usuario.type(await screen.findByLabelText('Unidades de Vino A'), '40')
    await usuario.type(screen.getByLabelText('Unidades de Gaseosa'), '12')
    await usuario.click(screen.getByRole('button', { name: 'Agregar producto' }))
    await usuario.selectOptions(await screen.findByLabelText('Agregar producto'), ACEITE)
    await usuario.click(screen.getByRole('button', { name: 'Registrar rendición' }))

    expect(await screen.findByText('Falta contar: Aceite.')).toBeInTheDocument()
  })
})

describe('RendicionScreen: rechazos del servidor (tarea 12.1; D2, D11, INV-06)', () => {
  it('ESPERADO_DIFIERE recarga los esperados, marca los que cambiaron y conserva lo contado', async () => {
    let esperado = 40
    const reglas = reglasBase({ esperadoVino: () => esperado }).map((r) =>
      r.metodo === 'POST'
        ? {
            ...r,
            responder: () => {
              esperado = 38
              return {
                status: 409,
                cuerpo: { title: 'Cambió', codigo: 'ESPERADO_DIFIERE', distintos: [VINO], esperados: { [VINO]: 38, [GASEOSA]: 12 } },
              }
            },
          }
        : r,
    )
    enrutar(apiFetchMock, reglas)
    const usuario = userEvent.setup()
    renderEn('SUP')

    await usuario.type(await screen.findByLabelText('Unidades de Vino A'), '37')
    await usuario.type(screen.getByLabelText('Unidades de Gaseosa'), '12')
    await usuario.click(screen.getByRole('button', { name: 'Registrar rendición' }))
    await usuario.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Confirmar' }))

    expect(
      await screen.findByText('El stock del vehículo cambió mientras contabas. Revisá los esperados marcados y volvé a confirmar.'),
    ).toBeInTheDocument()
    const filaVino = (await screen.findByText('Vino A')).closest('tr') as HTMLElement
    await waitFor(() => expect(within(filaVino).getByText('38 unidades (6 Caja x6 + 2 un.)')).toBeInTheDocument())
    expect(within(filaVino).getByText('Esperado actualizado')).toBeInTheDocument()
    const filaGaseosa = screen.getByText('Gaseosa').closest('tr') as HTMLElement
    expect(within(filaGaseosa).queryByText('Esperado actualizado')).not.toBeInTheDocument()
    expect(screen.getByLabelText('Unidades de Vino A')).toHaveValue('37')

    // Vuelve a confirmar con el esperado nuevo.
    await usuario.click(screen.getByRole('button', { name: 'Registrar rendición' }))
    await usuario.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Confirmar' }))
    await waitFor(() => expect(llamadas(apiFetchMock, 'POST', `/stock/jornadas/${JORNADA}/rendicion`)).toHaveLength(2))
    expect(cuerpoDe(1).lineas).toContainEqual({ producto_id: VINO, cantidad_contada: 37, cantidad_esperada: 38 })
  })

  it('CONTEO_INCOMPLETO nombra los productos que faltan y vuelve a leer el conjunto', async () => {
    const reglas = reglasBase().map((r) =>
      r.metodo === 'POST'
        ? { ...r, responder: () => ({ status: 422, cuerpo: { title: 'Falta', codigo: 'CONTEO_INCOMPLETO', productos: [GASEOSA, VINO] } }) }
        : r,
    )
    enrutar(apiFetchMock, reglas)
    const usuario = userEvent.setup()
    renderEn('SUP')

    await usuario.type(await screen.findByLabelText('Unidades de Vino A'), '40')
    await usuario.type(screen.getByLabelText('Unidades de Gaseosa'), '12')
    await usuario.click(screen.getByRole('button', { name: 'Registrar rendición' }))
    await usuario.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Confirmar' }))

    expect(await screen.findByText('Falta contar: Gaseosa, Vino A.')).toBeInTheDocument()
    expect(llamadas(apiFetchMock, 'GET', `/stock/jornadas/${JORNADA}/resumen`).length).toBeGreaterThanOrEqual(2)
  })

  it('JORNADA_SIN_ENTREGA se muestra con su texto aprobado', async () => {
    const reglas = reglasBase().map((r) =>
      r.metodo === 'POST' ? { ...r, responder: () => ({ status: 409, cuerpo: { title: 'x', codigo: 'JORNADA_SIN_ENTREGA' } }) } : r,
    )
    enrutar(apiFetchMock, reglas)
    const usuario = userEvent.setup()
    renderEn('SUP')

    await usuario.type(await screen.findByLabelText('Unidades de Vino A'), '40')
    await usuario.type(screen.getByLabelText('Unidades de Gaseosa'), '12')
    await usuario.click(screen.getByRole('button', { name: 'Registrar rendición' }))
    await usuario.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Confirmar' }))

    expect(await screen.findByText('El vendedor todavía no terminó el día en el teléfono.')).toBeInTheDocument()
  })

  it('el reintento tras un corte de red reenvía el mismo Operation-Id y no duplica la rendición (INV-06)', async () => {
    let intento = 0
    const reglas = reglasBase().map((r) =>
      r.metodo === 'POST'
        ? {
            ...r,
            responder: () => {
              intento += 1
              if (intento === 1) throw new TypeError('Failed to fetch')
              return { status: 200, cuerpo: { id: JORNADA, estado: 'EN_RENDICION' } }
            },
          }
        : r,
    )
    enrutar(apiFetchMock, reglas)
    const usuario = userEvent.setup()
    renderEn('SUP')

    await usuario.type(await screen.findByLabelText('Unidades de Vino A'), '40')
    await usuario.type(screen.getByLabelText('Unidades de Gaseosa'), '12')
    await usuario.click(screen.getByRole('button', { name: 'Registrar rendición' }))
    await usuario.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Confirmar' }))

    // El corte de red se reintenta solo con el mismo Operation-Id; la segunda respuesta es la aceptada.
    await waitFor(() => expect(llamadas(apiFetchMock, 'POST', `/stock/jornadas/${JORNADA}/rendicion`)).toHaveLength(2))
    const [primera, segunda] = llamadas(apiFetchMock, 'POST', `/stock/jornadas/${JORNADA}/rendicion`)
    expect(new Headers(segunda?.init.headers).get('Operation-Id')).toBe(new Headers(primera?.init.headers).get('Operation-Id'))
  })
})

describe('RendicionScreen: cuándo se puede rendir (tarea 12.1; RUT-05)', () => {
  it('sin la entrega del vendedor no muestra el formulario y dice por qué', async () => {
    enrutar(apiFetchMock, reglasBase({ entregada: false }))
    renderEn('SUP')

    expect(await screen.findByText('El vendedor todavía no terminó el día en el teléfono.')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Registrar rendición' })).not.toBeInTheDocument()
  })

  it('una jornada que ya no está abierta no se rinde', async () => {
    enrutar(apiFetchMock, reglasBase({ estado: 'EN_RENDICION' }))
    renderEn('SUP')

    expect(await screen.findByText(/La jornada ya cambió de estado/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Registrar rendición' })).not.toBeInTheDocument()
  })

  it('sin RENDIR_JORNADA no se pide nada (SEG-06)', async () => {
    enrutar(apiFetchMock, reglasBase())
    renderEn('VEN')

    expect(await screen.findByText('No tenés permiso para rendir jornadas.')).toBeInTheDocument()
    expect(llamadas(apiFetchMock, 'GET', `/stock/jornadas/${JORNADA}/resumen`)).toHaveLength(0)
  })
})
