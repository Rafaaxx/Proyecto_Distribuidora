import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }))
vi.mock('../../../../../src/lib/api/httpClient', () => ({ apiFetch: apiFetchMock }))

import { ResumenDeJornada } from '../../../../../src/areas/admin/stock/ResumenDeJornada'
import { enrutar, llamadas, type ReglaDeApi } from '../../../utils/enrutarApi'
import { queryClientConYo, type RolDePrueba } from '../../../utils/permisosDePrueba'

/**
 * Change 24, tarea 13.1 (D4, D8, D9; cita RUT-07, STK-04, INV-03, `01` §19): el resumen de la
 * jornada con sus columnas, el dinero por medio de pago, lo que llegó después de la rendición
 * aparte, «Esta jornada no tiene conteo.» y el valor de la diferencia solo con `VER_COSTOS`.
 * Los importes se muestran tal como vienen (string), sin calcularlos en el frontend.
 */
const JORNADA = '33333333-3333-4333-8333-333333333333'
const CAMIONETA_1 = '22222222-2222-4222-8222-222222222221'
const VINO = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1'
const GASEOSA = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa2'
const EFECTIVO = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbb1'
const TRANSFERENCIA = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbb2'

const SIN_DINERO = { cantidad: 0, total: '0.00' }
const SIN_COBRANZAS = { cantidad: 0, total: '0.00', por_medio: [] }

function resumenBase(cambios: Record<string, unknown> = {}) {
  return {
    jornada_id: JORNADA,
    estado: 'EN_RENDICION',
    con_conteo: true,
    rendida_en: '2026-04-10T20:00:00Z',
    lineas: [
      { producto_id: VINO, al_abrir: 10, ingresos: 36, ventas: 8, anulaciones: 2, otros: 0, esperado: 40, contado: 37, diferencia: -3 },
      { producto_id: GASEOSA, al_abrir: 0, ingresos: 12, ventas: 0, anulaciones: 0, otros: 0, esperado: 12, contado: 12, diferencia: 0 },
    ],
    dinero: {
      ventas: { cantidad: 4, total: '31250.00' },
      anuladas: { cantidad: 1, total: '8000.00' },
      cobranzas: {
        cantidad: 3,
        total: '25000.00',
        por_medio: [
          { medio_pago_id: EFECTIVO, nombre: 'Efectivo', total: '20000.00' },
          { medio_pago_id: TRANSFERENCIA, nombre: 'Transferencia', total: '5000.00' },
        ],
      },
      cobranzas_anuladas: { cantidad: 1, total: '1500.00', por_medio: [{ medio_pago_id: EFECTIVO, nombre: 'Efectivo', total: '1500.00' }] },
    },
    despues_de_la_rendicion: null,
    ...cambios,
  }
}

const PRODUCTOS = {
  items: [
    { id: VINO, codigo: 'V1', nombre: 'Vino A', activo: true },
    { id: GASEOSA, codigo: 'G1', nombre: 'Gaseosa', activo: true },
  ],
  cursor_siguiente: null,
}
const SALDOS = {
  items: [{ producto_id: VINO, producto_codigo: 'V1', producto_nombre: 'Vino A', cantidad_base: 37, unidades_referencia: 6, nombre_referencia: 'Caja x6' }],
  cursor_siguiente: null,
}

function reglas(resumen: unknown): ReglaDeApi[] {
  return [
    { ruta: `/stock/jornadas/${JORNADA}/resumen`, responder: () => ({ status: 200, cuerpo: resumen }) },
    { ruta: '/catalogo/productos', responder: () => ({ status: 200, cuerpo: PRODUCTOS }) },
    { ruta: `/stock/ubicaciones/${CAMIONETA_1}/saldos`, responder: () => ({ status: 200, cuerpo: SALDOS }) },
  ]
}

function renderResumen(rol: RolDePrueba) {
  return render(
    <QueryClientProvider client={queryClientConYo(rol)}>
      <MemoryRouter>
        <ResumenDeJornada jornadaId={JORNADA} ubicacionId={CAMIONETA_1} />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  apiFetchMock.mockReset()
})
afterEach(() => {
  vi.clearAllMocks()
})

describe('ResumenDeJornada: el stock (tarea 13.1; RUT-07, STK-04)', () => {
  it('muestra el título con su ayuda, las columnas aprobadas y una fila por producto con sus nombres', async () => {
    enrutar(apiFetchMock, reglas(resumenBase()))
    renderResumen('SUP')

    expect(await screen.findByRole('heading', { name: 'Resumen de la jornada' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Ayuda: Resumen de la jornada' })).toBeInTheDocument()
    for (const columna of ['Producto', 'Al abrir', 'Ingresos', 'Ventas', 'Anulaciones', 'Otros', 'Esperado', 'Contado', 'Diferencia']) {
      expect(await screen.findByRole('columnheader', { name: new RegExp(`^${columna}`) })).toBeInTheDocument()
    }
    const filaVino = (await screen.findByText('Vino A')).closest('tr') as HTMLElement
    expect(within(filaVino).getByText('40 unidades (6 Caja x6 + 4 un.)')).toBeInTheDocument()
    expect(within(filaVino).getByText('37 unidades (6 Caja x6 + 1 un.)')).toBeInTheDocument()
    expect(within(filaVino).getByText('-3 unidades')).toBeInTheDocument()
    expect(within(filaVino).getByText('10 unidades (1 Caja x6 + 4 un.)')).toBeInTheDocument()
    expect(screen.getByText('Gaseosa').closest('tr')).toBeInTheDocument()
  })

  it('sin permiso para costos no hay valor de la diferencia ni columna de valor (VER_COSTOS)', async () => {
    enrutar(apiFetchMock, reglas(resumenBase()))
    renderResumen('SUP')

    await screen.findByText('Vino A')
    expect(screen.queryByText(/Valor de la diferencia/)).not.toBeInTheDocument()
  })

  it('con VER_COSTOS muestra el valor de cada diferencia y el total tal como viene (INV-03)', async () => {
    const cuerpo = resumenBase({ valor_de_diferencias: '-4500.00' })
    cuerpo.lineas[0] = { ...cuerpo.lineas[0], valor_diferencia: '-4500.00' } as (typeof cuerpo.lineas)[number]
    cuerpo.lineas[1] = { ...cuerpo.lineas[1], valor_diferencia: '0.00' } as (typeof cuerpo.lineas)[number]
    enrutar(apiFetchMock, reglas(cuerpo))
    renderResumen('GES')

    expect(await screen.findByText('Valor de la diferencia: -4.500,00')).toBeInTheDocument()
    const filaVino = screen.getByText('Vino A').closest('tr') as HTMLElement
    expect(within(filaVino).getByText('-4.500,00')).toBeInTheDocument()
  })

  it('una jornada sin conteo dice «Esta jornada no tiene conteo.» y no muestra contado ni diferencias (D8)', async () => {
    const cuerpo = resumenBase({
      estado: 'CERRADA',
      con_conteo: false,
      lineas: [{ producto_id: VINO, al_abrir: 10, ingresos: 36, ventas: 8, anulaciones: 2, otros: 0, esperado: 40, contado: null, diferencia: null }],
    })
    enrutar(apiFetchMock, reglas(cuerpo))
    renderResumen('SUP')

    expect(await screen.findByText('Esta jornada no tiene conteo.')).toBeInTheDocument()
    expect(screen.queryByRole('columnheader', { name: /^Contado/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('columnheader', { name: /^Diferencia/ })).not.toBeInTheDocument()
    expect(screen.getByRole('columnheader', { name: /^Esperado/ })).toBeInTheDocument()
  })

  it('una jornada abierta todavía no tiene conteo y no lo dice', async () => {
    enrutar(apiFetchMock, reglas(resumenBase({ estado: 'ABIERTA', con_conteo: false, rendida_en: null })))
    renderResumen('SUP')

    await screen.findByText('Vino A')
    expect(screen.queryByText('Esta jornada no tiene conteo.')).not.toBeInTheDocument()
  })
})

describe('ResumenDeJornada: el dinero (tarea 13.1; RUT-07, COB-01, COB-05)', () => {
  it('muestra ventas y anuladas con su cantidad y total, las cobranzas por medio de pago y las anuladas', async () => {
    enrutar(apiFetchMock, reglas(resumenBase()))
    renderResumen('SUP')

    expect(await screen.findByText('Ventas: 4 por 31.250,00')).toBeInTheDocument()
    expect(screen.getByText('Anuladas: 1 por 8.000,00')).toBeInTheDocument()
    const cobranzas = screen.getByRole('heading', { name: 'Cobranzas por medio de pago' }).parentElement as HTMLElement
    expect(within(cobranzas).getByText('Efectivo: 20.000,00')).toBeInTheDocument()
    expect(within(cobranzas).getByText('Transferencia: 5.000,00')).toBeInTheDocument()
    const anuladas = screen.getByRole('heading', { name: 'Cobranzas anuladas' }).parentElement as HTMLElement
    expect(within(anuladas).getByText('Efectivo: 1.500,00')).toBeInTheDocument()
  })

  it('lo que llegó después de la rendición se muestra aparte y solo si hay algo', async () => {
    const tardio = {
      ventas: { cantidad: 1, total: '3000.00' },
      anuladas: SIN_DINERO,
      cobranzas: { cantidad: 1, total: '1000.00', por_medio: [{ medio_pago_id: EFECTIVO, nombre: 'Efectivo', total: '1000.00' }] },
      cobranzas_anuladas: SIN_COBRANZAS,
    }
    enrutar(apiFetchMock, reglas(resumenBase({ despues_de_la_rendicion: tardio })))
    const { unmount } = renderResumen('SUP')

    const aparte = (await screen.findByRole('heading', { name: 'Llegaron después de la rendición' })).parentElement as HTMLElement
    expect(within(aparte).getByText('Ventas: 1 por 3.000,00')).toBeInTheDocument()
    expect(within(aparte).getByText('Efectivo: 1.000,00')).toBeInTheDocument()
    // Lo de la jornada sigue aparte: el total de ventas del resumen no incluye lo tardío.
    expect(screen.getByText('Ventas: 4 por 31.250,00')).toBeInTheDocument()
    unmount()

    apiFetchMock.mockReset()
    const vacio = { ventas: SIN_DINERO, anuladas: SIN_DINERO, cobranzas: SIN_COBRANZAS, cobranzas_anuladas: SIN_COBRANZAS }
    enrutar(apiFetchMock, reglas(resumenBase({ despues_de_la_rendicion: vacio })))
    renderResumen('SUP')
    await screen.findByText('Vino A')
    expect(screen.queryByRole('heading', { name: 'Llegaron después de la rendición' })).not.toBeInTheDocument()
  })

  it('un 404 o un error del resumen no rompe la pantalla', async () => {
    enrutar(apiFetchMock, [{ ruta: `/stock/jornadas/${JORNADA}/resumen`, responder: () => ({ status: 500, cuerpo: { title: 'x', codigo: 'X' } }) }])
    renderResumen('SUP')

    expect(await screen.findByText('No se pudo obtener el resumen de la jornada.')).toBeInTheDocument()
    expect(llamadas(apiFetchMock, 'GET', `/stock/jornadas/${JORNADA}/resumen`).length).toBeGreaterThanOrEqual(1)
  })
})
