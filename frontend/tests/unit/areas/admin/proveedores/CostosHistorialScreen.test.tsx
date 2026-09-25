import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }))
vi.mock('../../../../../src/lib/api/httpClient', () => ({ apiFetch: apiFetchMock }))

import { CostosHistorialScreen } from '../../../../../src/areas/admin/proveedores/CostosHistorialScreen'

function respuesta(status: number, cuerpo: unknown) {
  return { ok: status >= 200 && status < 300, status, json: async () => cuerpo }
}

const PRODUCTO_ID = '11111111-1111-4111-8111-111111111111'

const COSTO_VIGENTE = {
  id: 'a1',
  proveedor_id: 'p1',
  producto_id: PRODUCTO_ID,
  presentacion_id: 'pr1',
  valor: '18000.00',
  incluye_iva: false,
  bonificacion: '0',
  alicuota_aplicada: '0.210000',
  costo_base: '1500.000000',
  vigencia_desde: '2026-09-01',
  observacion: null,
  usuario_id: 'u1',
  operation_id: 'o1',
  creado_en: '2026-09-01T08:05:00Z',
  proveedor_nombre: 'Cervecería Central',
  presentacion_nombre: 'Caja x12',
  usuario_nombre: 'Ana Pérez',
}

const COSTO_PROGRAMADO = {
  ...COSTO_VIGENTE,
  id: 'a2',
  costo_base: '1350.000000',
  bonificacion: '0.100000',
  vigencia_desde: '2026-10-01',
  creado_en: '2026-09-10T10:30:00Z',
  usuario_nombre: 'Beto Gómez',
}

// Tarea 14.6 (corrección de la verificación manual 13.5, opción B): el
// último costo informado por presentación (P11) para una segunda
// presentación (`Botella`) del mismo producto -- distinta de la
// presentación del costo vigente (`Caja x12`, `COSTO_VIGENTE`).
const COSTO_POR_PRESENTACION_BOTELLA = {
  ...COSTO_VIGENTE,
  id: 'a3',
  presentacion_id: 'pr2',
  presentacion_nombre: 'Botella',
  valor: '1000.00',
  costo_base: '1000.000000',
  vigencia_desde: '2026-08-01',
  usuario_nombre: 'Carla Ruiz',
}

function mockApi() {
  apiFetchMock.mockImplementation((ruta: string) => {
    if (ruta.includes('/vigente')) {
      return Promise.resolve(
        respuesta(200, {
          fecha: '2026-09-15',
          costo: COSTO_VIGENTE,
          por_presentacion: [COSTO_POR_PRESENTACION_BOTELLA, COSTO_VIGENTE],
        }),
      )
    }
    if (ruta.includes('/historial')) {
      // De la vigencia más reciente a la más antigua (CST-03).
      return Promise.resolve(respuesta(200, { items: [COSTO_PROGRAMADO, COSTO_VIGENTE], cursor_siguiente: null }))
    }
    return Promise.resolve(respuesta(200, { items: [], cursor_siguiente: null }))
  })
}

/**
 * Filas del cuerpo de la tabla de "Historial" (sin encabezado), acotadas
 * a esa sección -- necesario desde la tarea 14.6: la pantalla ahora tiene
 * una segunda tabla ("Último costo informado por presentación"), así que
 * `screen.findAllByRole('row')` sin acotar mezclaría filas de ambas.
 */
async function filasDeHistorial(): Promise<HTMLElement[]> {
  const encabezado = await screen.findByRole('heading', { name: 'Historial' })
  const seccion = encabezado.closest('section') as HTMLElement
  return (await within(seccion).findAllByRole('row')).slice(1)
}

function renderPantalla() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[`/admin/proveedores/productos/${PRODUCTO_ID}/historial`]}>
        <Routes>
          <Route path="/admin/proveedores/productos/:productoId/historial" element={<CostosHistorialScreen />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

/**
 * Tarea 11.5 y 14.5 (corrección de la verificación manual 13.5), spec
 * `administracion-de-proveedores`, escenario "Historial con vigente
 * resaltado": con vigencias `2026-09-01` y `2026-10-01` y hoy `2026-09-15`
 * (fecha de negocio de la organización, TR-04), el de `2026-10-01` se
 * marca como programado y el vigente es `1.500,000000`, con la fila
 * resaltada (badge "Vigente", no solo color) y todos los datos del
 * requisito: lo informado, la alícuota, el usuario y el momento de
 * registro.
 */
describe('CostosHistorialScreen (tareas 11.5 y 14.5)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('muestra el costo vigente y el historial con la vigencia futura marcada como programada', async () => {
    mockApi()
    renderPantalla()

    const seccionVigente = (await screen.findByText('Costo vigente')).closest('section') as HTMLElement
    expect(await within(seccionVigente).findByText('1.500,000000')).toBeInTheDocument()

    const filas = await filasDeHistorial()
    expect(filas).toHaveLength(2)

    const filaFutura = within(filas[0] as HTMLElement)
    expect(filaFutura.getByText('2026-10-01')).toBeInTheDocument()
    expect(filaFutura.getByText('Programado')).toBeInTheDocument()

    const filaVigente = within(filas[1] as HTMLElement)
    expect(filaVigente.getByText('2026-09-01')).toBeInTheDocument()
    expect(filaVigente.queryByText('Programado')).not.toBeInTheDocument()
  })

  it('sin costo vigente muestra "Sin costo vigente" en vez de un importe', async () => {
    apiFetchMock.mockImplementation((ruta: string) => {
      if (ruta.includes('/vigente')) {
        return Promise.resolve(
          respuesta(200, { fecha: '2026-09-15', costo: null, por_presentacion: [] }),
        )
      }
      return Promise.resolve(respuesta(200, { items: [], cursor_siguiente: null }))
    })

    renderPantalla()

    expect(await screen.findByText('Sin costo vigente')).toBeInTheDocument()
  })

  it('resalta la fila del costo vigente con una insignia "Vigente" y no la marca en la programada', async () => {
    mockApi()
    renderPantalla()

    const filas = await filasDeHistorial()
    const filaFutura = within(filas[0] as HTMLElement)
    const filaVigente = within(filas[1] as HTMLElement)

    expect(await filaVigente.findByText('Vigente')).toBeInTheDocument()
    expect(filaFutura.queryByText('Vigente')).not.toBeInTheDocument()
  })

  it('muestra lo informado (importe y con/sin IVA) y la bonificación como porcentaje', async () => {
    mockApi()
    renderPantalla()

    const filas = await filasDeHistorial()
    const filaFutura = within(filas[0] as HTMLElement)
    const filaVigente = within(filas[1] as HTMLElement)

    // COSTO_VIGENTE: valor "18000.00", incluye_iva=false, bonificación 0.
    // `formatearImporte` (`lib/money.ts`) es de dos decimales fijos, sin
    // agrupar miles -- distinto de `formatearCosto`.
    expect(filaVigente.getByText('18000.00')).toBeInTheDocument()
    expect(filaVigente.getByText(/sin IVA/i)).toBeInTheDocument()
    expect(filaVigente.getByText('0 %')).toBeInTheDocument()

    // COSTO_PROGRAMADO: bonificación 0.100000 -> "10 %".
    expect(filaFutura.getByText('10 %')).toBeInTheDocument()
  })

  it('muestra la alícuota aplicada como porcentaje, no como fracción', async () => {
    mockApi()
    renderPantalla()

    const filas = await filasDeHistorial()
    for (const fila of filas) {
      expect(within(fila as HTMLElement).getByText('21 %')).toBeInTheDocument()
      expect(within(fila as HTMLElement).queryByText('0,210000')).not.toBeInTheDocument()
    }
  })

  it('muestra quién registró cada costo y cuándo', async () => {
    mockApi()
    renderPantalla()

    const filas = await filasDeHistorial()
    const filaFutura = within(filas[0] as HTMLElement)
    const filaVigente = within(filas[1] as HTMLElement)

    expect(filaVigente.getByText('Ana Pérez')).toBeInTheDocument()
    expect(filaFutura.getByText('Beto Gómez')).toBeInTheDocument()
    // `creado_en` formateado dd/mm/aaaa hh:mm en la hora local del entorno
    // de prueba (`America/Buenos_Aires`, UTC-3): "2026-09-01T08:05:00Z" ->
    // "01/09/2026 05:05".
    expect(filaVigente.getByText('01/09/2026 05:05')).toBeInTheDocument()
  })

  it('el box de costo vigente muestra de dónde viene: presentación, proveedor y vigencia desde', async () => {
    mockApi()
    renderPantalla()

    const seccionVigente = (await screen.findByText('Costo vigente')).closest('section') as HTMLElement
    const dentro = within(seccionVigente)

    expect(await dentro.findByText('1.500,000000')).toBeInTheDocument()
    expect(dentro.getByText('Caja x12')).toBeInTheDocument()
    expect(dentro.getByText('Cervecería Central')).toBeInTheDocument()
    expect(dentro.getByText('2026-09-01')).toBeInTheDocument()
    expect(dentro.getByText('18000.00')).toBeInTheDocument()
    expect(dentro.getByText(/sin IVA/i)).toBeInTheDocument()
  })

  /**
   * Tarea 14.6 (corrección de la verificación manual 13.5, opción B):
   * `GET .../vigente` suma `por_presentacion` (P11) -- el último costo
   * informado de cada presentación con costo a la fecha, puramente
   * informativo (el precio se calcula solo con el costo vigente del
   * producto, PRC-11).
   */
  it('muestra el último costo informado por presentación, con la fila del costo vigente marcada', async () => {
    mockApi()
    renderPantalla()

    const titulo = await screen.findByText('Último costo informado por presentación')
    const seccion = titulo.closest('section') as HTMLElement
    const dentro = within(seccion)

    const filas = (await dentro.findAllByRole('row')).slice(1) // sin encabezado
    expect(filas).toHaveLength(2)

    const filaBotella = within(
      filas.find((fila) => within(fila as HTMLElement).queryByText('Botella')) as HTMLElement,
    )
    expect(filaBotella.getByText('Cervecería Central')).toBeInTheDocument()
    expect(filaBotella.getByText('2026-08-01')).toBeInTheDocument()
    expect(filaBotella.getByText('1000.00')).toBeInTheDocument()
    expect(filaBotella.getByText('1.000,000000')).toBeInTheDocument()
    expect(filaBotella.queryByText('Vigente')).not.toBeInTheDocument()

    const filaCaja = within(
      filas.find((fila) => within(fila as HTMLElement).queryByText('Caja x12')) as HTMLElement,
    )
    expect(filaCaja.getByText('1.500,000000')).toBeInTheDocument()
    expect(filaCaja.getByText('Vigente')).toBeInTheDocument()

    expect(
      dentro.getByText(
        'Informativo: el precio se calcula solo con el costo vigente del producto.',
      ),
    ).toBeInTheDocument()
  })

  it('sin costos por presentación, no muestra la sección', async () => {
    apiFetchMock.mockImplementation((ruta: string) => {
      if (ruta.includes('/vigente')) {
        return Promise.resolve(
          respuesta(200, { fecha: '2026-09-15', costo: COSTO_VIGENTE, por_presentacion: [] }),
        )
      }
      if (ruta.includes('/historial')) {
        return Promise.resolve(respuesta(200, { items: [COSTO_VIGENTE], cursor_siguiente: null }))
      }
      return Promise.resolve(respuesta(200, { items: [], cursor_siguiente: null }))
    })
    renderPantalla()

    await screen.findByText('Costo vigente')
    expect(screen.queryByText('Último costo informado por presentación')).not.toBeInTheDocument()
  })
})
