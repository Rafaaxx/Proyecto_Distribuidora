import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }))
vi.mock('../../../../../src/lib/api/httpClient', () => ({ apiFetch: apiFetchMock }))

import StockArea from '../../../../../src/areas/admin/stock/StockArea'
import { SECCIONES, seccionesPermitidas } from '../../../../../src/features/identidad/secciones'
import { enrutar, llamadas } from '../../../utils/enrutarApi'
import { PERMISOS_POR_ROL, queryClientConYo, type RolDePrueba } from '../../../utils/permisosDePrueba'

const DEPOSITO = '11111111-1111-4111-8111-111111111111'
const CAMIONETA_1 = '22222222-2222-4222-8222-222222222221'
const CAMIONETA_2 = '22222222-2222-4222-8222-222222222222'
const CAMIONETA_3 = '22222222-2222-4222-8222-222222222223'
const JORNADA = '33333333-3333-4333-8333-333333333333'
const JUAN = '44444444-4444-4444-8444-444444444444'
const DISPOSITIVO = '55555555-5555-4555-8555-555555555555'
const MOTIVO = '66666666-6666-4666-8666-666666666666'

const BASE_UBICACION = { actualizado_en: '2026-01-01T00:00:00Z' }
const UBICACIONES = {
  items: [
    {
      ...BASE_UBICACION,
      id: CAMIONETA_1,
      nombre: 'Camioneta 1',
      tipo: 'VEHICULO',
      requiere_toma: true,
      activo: true,
      jornada: { id: JORNADA, usuario_id: JUAN, usuario_nombre: 'Juan', abierta_en: '2026-04-10T11:00:00Z', estado: 'ABIERTA' },
    },
    { ...BASE_UBICACION, id: CAMIONETA_2, nombre: 'Camioneta 2', tipo: 'VEHICULO', requiere_toma: true, activo: true, jornada: null },
    { ...BASE_UBICACION, id: CAMIONETA_3, nombre: 'Camioneta 3', tipo: 'VEHICULO', requiere_toma: true, activo: false, jornada: null },
    { ...BASE_UBICACION, id: DEPOSITO, nombre: 'Depósito central', tipo: 'DEPOSITO', requiere_toma: false, activo: true, jornada: null },
  ],
  cursor_siguiente: null,
}

type Estado = 'ABIERTA' | 'EN_RENDICION' | 'CERRADA' | 'LIBERADA'

function detalle(estado: Estado, extra: Record<string, unknown> = {}) {
  return {
    id: JORNADA,
    ubicacion_id: CAMIONETA_1,
    ubicacion_nombre: 'Camioneta 1',
    usuario_id: JUAN,
    usuario_nombre: 'Juan',
    dispositivo_id: DISPOSITIVO,
    estado,
    abierta_en: '2026-04-10T11:00:00Z',
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
    ...extra,
  }
}

function delListado(estado: Estado, extra: Record<string, unknown> = {}) {
  return {
    id: JORNADA,
    ubicacion_id: CAMIONETA_1,
    ubicacion_nombre: 'Camioneta 1',
    usuario_id: JUAN,
    usuario_nombre: 'Juan',
    dispositivo_id: DISPOSITIVO,
    estado,
    abierta_en: '2026-04-10T11:00:00Z',
    ...extra,
  }
}

function UbicacionActual() {
  const { pathname, search } = useLocation()
  return <p data-testid="ruta">{pathname + search}</p>
}

function renderEn(ruta: string, rol: RolDePrueba) {
  return render(
    <QueryClientProvider client={queryClientConYo(rol)}>
      <MemoryRouter initialEntries={[ruta]}>
        <UbicacionActual />
        <Routes>
          <Route path="/admin/stock/*" element={<StockArea />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

const REGLA_UBICACIONES = { ruta: '/stock/ubicaciones', responder: () => ({ status: 200, cuerpo: UBICACIONES }) }
const REGLA_MOTIVOS = {
  ruta: '/configuracion/motivos',
  responder: () => ({ status: 200, cuerpo: { items: [{ id: MOTIVO, nombre: 'Vendedor ausente' }] } }),
}
const SIN_JORNADA_ACTUAL = {
  ruta: '/stock/jornadas/actual',
  responder: () => ({ status: 404, cuerpo: { title: 'No hay', codigo: 'RECURSO_NO_ENCONTRADO' } }),
}

beforeEach(() => {
  apiFetchMock.mockReset()
})
afterEach(() => {
  vi.clearAllMocks()
})

describe('menú y rutas de jornadas por permiso (tarea 14.1)', () => {
  beforeEach(() => {
    enrutar(apiFetchMock, [REGLA_UBICACIONES, { ruta: '/stock/jornadas', responder: () => ({ status: 200, cuerpo: { items: [], cursor_siguiente: null } }) }])
  })

  it('un Vendedor ve "Jornadas" y "Abrir jornada" en la sección Stock', async () => {
    renderEn('/admin/stock', 'VEN')

    expect(await screen.findByRole('link', { name: 'Jornadas' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Abrir jornada' })).toBeInTheDocument()
  })

  it('Administración (RENDIR_JORNADA) ve "Jornadas" y no "Abrir jornada"', async () => {
    renderEn('/admin/stock', 'GES')

    expect(await screen.findByRole('link', { name: 'Jornadas' })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Abrir jornada' })).not.toBeInTheDocument()
  })

  it('la Supervisora ve ambas', async () => {
    renderEn('/admin/stock', 'SUP')

    expect(await screen.findByRole('link', { name: 'Jornadas' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Abrir jornada' })).toBeInTheDocument()
  })

  it('Consulta no ve la sección Stock ni "Jornadas", y la ruta directa no pide nada', async () => {
    const ve = seccionesPermitidas((permiso) => PERMISOS_POR_ROL.CON.includes(permiso))
    expect(ve.some((s) => s.ruta === '/admin/stock')).toBe(false)
    expect(SECCIONES.some((s) => s.etiqueta === 'Jornadas')).toBe(false)

    renderEn('/admin/stock/jornadas', 'CON')

    expect(await screen.findByText('No tenés permiso para ver las jornadas.')).toBeInTheDocument()
    expect(llamadas(apiFetchMock, 'GET', '/stock/jornadas')).toHaveLength(0)
  })

  it.each([
    ['/admin/stock/jornadas', 'No hay jornadas para mostrar.'],
    ['/admin/stock/jornadas/abrir', 'Abrir jornada'],
  ])('%s se resuelve a su pantalla', async (ruta, texto) => {
    renderEn(ruta, 'SUP')

    expect((await screen.findAllByText(texto)).length).toBeGreaterThan(0)
  })
})

describe('listado de jornadas (tarea 14.1; RUT-09, D15)', () => {
  it('muestra ubicación, usuario y estado de cada jornada y enlaza a su detalle', async () => {
    enrutar(apiFetchMock, [
      REGLA_UBICACIONES,
      {
        ruta: '/stock/jornadas',
        responder: () => ({
          status: 200,
          cuerpo: { items: [delListado('EN_RENDICION'), delListado('LIBERADA', { id: 'otra', ubicacion_nombre: 'Camioneta 2' })], cursor_siguiente: null },
        }),
      },
    ])
    renderEn('/admin/stock/jornadas', 'SUP')

    expect(await screen.findByText('En rendición', { selector: 'span' })).toBeInTheDocument()
    expect(screen.getByText('Liberada', { selector: 'span' })).toBeInTheDocument()
    expect(screen.getAllByRole('cell', { name: 'Juan' })).toHaveLength(2)
    expect(screen.getByRole('cell', { name: 'Camioneta 2' })).toBeInTheDocument()
    const enlaces = screen.getAllByRole('link', { name: 'Ver detalle' })
    expect(enlaces[0]).toHaveAttribute('href', `/admin/stock/jornadas/${JORNADA}`)
  })

  it('filtra por ubicación, usuario, estado y fechas', async () => {
    enrutar(apiFetchMock, [
      REGLA_UBICACIONES,
      { ruta: '/stock/jornadas', responder: () => ({ status: 200, cuerpo: { items: [delListado('ABIERTA')], cursor_siguiente: null } }) },
    ])
    const usuario = userEvent.setup()
    renderEn('/admin/stock/jornadas', 'SUP')

    await screen.findByText('Abierta', { selector: 'span' })
    await usuario.selectOptions(await screen.findByLabelText('Ubicación'), CAMIONETA_1)
    await usuario.selectOptions(screen.getByLabelText('Estado'), 'ABIERTA')
    await usuario.selectOptions(screen.getByLabelText('Usuario'), JUAN)
    await usuario.type(screen.getByLabelText('Desde'), '2026-04-01')
    await usuario.type(screen.getByLabelText('Hasta'), '2026-04-30')

    await waitFor(() => {
      const ultima = llamadas(apiFetchMock, 'GET', '/stock/jornadas').at(-1)
      expect(ultima?.url.searchParams.get('ubicacion_id')).toBe(CAMIONETA_1)
      expect(ultima?.url.searchParams.get('usuario_id')).toBe(JUAN)
      expect(ultima?.url.searchParams.get('estado')).toBe('ABIERTA')
      expect(ultima?.url.searchParams.get('desde')).toBe('2026-04-01')
      expect(ultima?.url.searchParams.get('hasta')).toBe('2026-04-30')
    })
  })
})

describe('detalle de una jornada según estado y permiso (tarea 14.1; RUT-09, ADR-027)', () => {
  function reglasDeDetalle(estado: Estado, extra: Record<string, unknown> = {}) {
    return [{ ruta: `/stock/jornadas/${JORNADA}`, responder: () => ({ status: 200, cuerpo: detalle(estado, extra) }) }, REGLA_MOTIVOS]
  }
  const boton = (nombre: string) => screen.queryByRole('button', { name: nombre })

  it('un Vendedor no ve Rendir, Cerrar ni Liberar sobre una jornada ABIERTA', async () => {
    enrutar(apiFetchMock, reglasDeDetalle('ABIERTA'))
    renderEn(`/admin/stock/jornadas/${JORNADA}`, 'VEN')

    expect(await screen.findByText('Abierta', { selector: 'span' })).toBeInTheDocument()
    for (const nombre of ['Rendir', 'Cerrar', 'Liberar']) expect(boton(nombre)).not.toBeInTheDocument()
  })

  it('una Supervisora ve Rendir y Liberar sobre una ABIERTA, y no Cerrar', async () => {
    enrutar(apiFetchMock, reglasDeDetalle('ABIERTA'))
    renderEn(`/admin/stock/jornadas/${JORNADA}`, 'SUP')

    expect(await screen.findByRole('button', { name: 'Rendir' })).toBeInTheDocument()
    expect(boton('Liberar')).toBeInTheDocument()
    expect(boton('Cerrar')).not.toBeInTheDocument()
  })

  it('Administración ve Cerrar sobre una EN_RENDICION, y no Liberar ni Abrir jornada', async () => {
    enrutar(apiFetchMock, reglasDeDetalle('EN_RENDICION', { rendida_en: '2026-04-10T20:00:00Z', rendida_por_nombre: 'Supervisora Sol' }))
    renderEn(`/admin/stock/jornadas/${JORNADA}`, 'GES')

    expect(await screen.findByRole('button', { name: 'Cerrar' })).toBeInTheDocument()
    expect(boton('Liberar')).not.toBeInTheDocument()
    expect(boton('Rendir')).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Abrir jornada' })).not.toBeInTheDocument()
  })

  it.each([
    ['CERRADA', { cerrada_en: '2026-04-10T21:00:00Z', cerrada_por_nombre: 'Supervisora Sol' }, 'Cerrada'],
    [
      'LIBERADA',
      { liberada_en: '2026-04-10T21:00:00Z', liberada_por_nombre: 'Supervisora Sol', motivo_liberacion_nombre: 'Vendedor ausente' },
      'Liberada',
    ],
  ] as const)('una jornada %s muestra su estado y sus datos y ninguna acción', async (estado, extra, etiqueta) => {
    enrutar(apiFetchMock, reglasDeDetalle(estado, extra))
    renderEn(`/admin/stock/jornadas/${JORNADA}`, 'SUP')

    expect(await screen.findByText(etiqueta, { selector: 'span' })).toBeInTheDocument()
    expect(screen.getByText(/Supervisora Sol/)).toBeInTheDocument()
    for (const nombre of ['Rendir', 'Cerrar', 'Liberar']) expect(boton(nombre)).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Cargar vehículo' })).not.toBeInTheDocument()
  })

  it('una jornada inexistente o ajena avisa que no se encontró', async () => {
    enrutar(apiFetchMock, [
      { ruta: `/stock/jornadas/${JORNADA}`, responder: () => ({ status: 404, cuerpo: { title: 'No existe', codigo: 'RECURSO_NO_ENCONTRADO' } }) },
    ])
    renderEn(`/admin/stock/jornadas/${JORNADA}`, 'SUP')

    expect(await screen.findByText('No se encontró la jornada.')).toBeInTheDocument()
  })
})

describe('abrir una jornada (tarea 14.2; RUT-01, RUT-03, INV-16)', () => {
  const REGLA_ABRIR_OK = {
    metodo: 'POST',
    ruta: '/stock/jornadas',
    responder: () => ({ status: 201, cuerpo: { id: JORNADA, estado: 'ABIERTA' } }),
  }

  it('solo ofrece la ubicación activa, con toma y libre', async () => {
    enrutar(apiFetchMock, [REGLA_UBICACIONES, SIN_JORNADA_ACTUAL])
    renderEn('/admin/stock/jornadas/abrir', 'VEN')

    const selector = await screen.findByLabelText('Ubicación')
    await waitFor(() => expect(within(selector).getByRole('option', { name: 'Camioneta 2' })).toBeInTheDocument())
    const opciones = within(selector).getAllByRole('option').map((o) => o.textContent)
    expect(opciones).toEqual(['Elegí la ubicación', 'Camioneta 2'])
  })

  it('avisa que requiere conexión', async () => {
    enrutar(apiFetchMock, [REGLA_UBICACIONES, SIN_JORNADA_ACTUAL])
    renderEn('/admin/stock/jornadas/abrir', 'VEN')

    expect(await screen.findByText(/requiere conexión/)).toBeInTheDocument()
  })

  it('confirmar sin elegir ubicación no envía nada y la pide', async () => {
    enrutar(apiFetchMock, [REGLA_UBICACIONES, SIN_JORNADA_ACTUAL, REGLA_ABRIR_OK])
    const usuario = userEvent.setup()
    renderEn('/admin/stock/jornadas/abrir', 'VEN')

    await usuario.click(await screen.findByRole('button', { name: 'Abrir jornada' }))

    expect(await screen.findByText('Elegí la ubicación que vas a tomar.')).toBeInTheDocument()
    expect(llamadas(apiFetchMock, 'POST', '/stock/jornadas')).toHaveLength(0)
  })

  it('abre la jornada y lleva a su detalle', async () => {
    enrutar(apiFetchMock, [
      REGLA_UBICACIONES,
      SIN_JORNADA_ACTUAL,
      REGLA_ABRIR_OK,
      { ruta: `/stock/jornadas/${JORNADA}`, responder: () => ({ status: 200, cuerpo: detalle('ABIERTA') }) },
    ])
    const usuario = userEvent.setup()
    renderEn('/admin/stock/jornadas/abrir', 'VEN')

    const selector = await screen.findByLabelText('Ubicación')
    await waitFor(() => expect(within(selector).getByRole('option', { name: 'Camioneta 2' })).toBeInTheDocument())
    await usuario.selectOptions(selector, CAMIONETA_2)
    await usuario.click(screen.getByRole('button', { name: 'Abrir jornada' }))

    await waitFor(() => expect(screen.getByTestId('ruta')).toHaveTextContent(`/admin/stock/jornadas/${JORNADA}`))
    const envio = llamadas(apiFetchMock, 'POST', '/stock/jornadas')[0]
    expect(JSON.parse(String(envio?.init.body))).toEqual({ ubicacion_id: CAMIONETA_2 })
  })

  it('si otro la tomó mientras tanto, muestra UBICACION_TOMADA y sigue en la pantalla de apertura', async () => {
    enrutar(apiFetchMock, [
      REGLA_UBICACIONES,
      SIN_JORNADA_ACTUAL,
      {
        metodo: 'POST',
        ruta: '/stock/jornadas',
        responder: () => ({ status: 409, cuerpo: { title: 'Tomada', codigo: 'UBICACION_TOMADA' } }),
      },
    ])
    const usuario = userEvent.setup()
    renderEn('/admin/stock/jornadas/abrir', 'VEN')

    const selector = await screen.findByLabelText('Ubicación')
    await waitFor(() => expect(within(selector).getByRole('option', { name: 'Camioneta 2' })).toBeInTheDocument())
    await usuario.selectOptions(selector, CAMIONETA_2)
    await usuario.click(screen.getByRole('button', { name: 'Abrir jornada' }))

    expect(await screen.findByText('Esa ubicación ya la tomó otra jornada. Elegí otra.')).toBeInTheDocument()
    expect(screen.getByTestId('ruta')).toHaveTextContent('/admin/stock/jornadas/abrir')
  })

  it('USUARIO_CON_JORNADA se muestra al usuario', async () => {
    enrutar(apiFetchMock, [
      REGLA_UBICACIONES,
      SIN_JORNADA_ACTUAL,
      {
        metodo: 'POST',
        ruta: '/stock/jornadas',
        responder: () => ({ status: 409, cuerpo: { title: 'x', codigo: 'USUARIO_CON_JORNADA' } }),
      },
    ])
    const usuario = userEvent.setup()
    renderEn('/admin/stock/jornadas/abrir', 'VEN')

    const selector = await screen.findByLabelText('Ubicación')
    await waitFor(() => expect(within(selector).getByRole('option', { name: 'Camioneta 2' })).toBeInTheDocument())
    await usuario.selectOptions(selector, CAMIONETA_2)
    await usuario.click(screen.getByRole('button', { name: 'Abrir jornada' }))

    expect(await screen.findByText(/Ya tenés una jornada abierta/)).toBeInTheDocument()
  })

  it('reintenta con el mismo operation_id tras un corte de red y con otro si cambia la ubicación', async () => {
    let intentos = 0
    enrutar(apiFetchMock, [
      {
        ruta: '/stock/ubicaciones',
        responder: () => ({
          status: 200,
          cuerpo: { items: [UBICACIONES.items[1], { ...UBICACIONES.items[1], id: CAMIONETA_3, nombre: 'Camioneta 4', activo: true }], cursor_siguiente: null },
        }),
      },
      SIN_JORNADA_ACTUAL,
      {
        metodo: 'POST',
        ruta: '/stock/jornadas',
        responder: () => {
          intentos += 1
          if (intentos <= 6) throw new TypeError('Failed to fetch')
          return { status: 201, cuerpo: { id: JORNADA, estado: 'ABIERTA' } }
        },
      },
    ])
    const usuario = userEvent.setup()
    renderEn('/admin/stock/jornadas/abrir', 'VEN')

    const selector = await screen.findByLabelText('Ubicación')
    await waitFor(() => expect(within(selector).getByRole('option', { name: 'Camioneta 2' })).toBeInTheDocument())
    await usuario.selectOptions(selector, CAMIONETA_2)
    await usuario.click(screen.getByRole('button', { name: 'Abrir jornada' }))
    expect(await screen.findByText(/Se necesita conexión/)).toBeInTheDocument()
    await usuario.click(screen.getByRole('button', { name: 'Abrir jornada' }))
    await waitFor(() => expect(llamadas(apiFetchMock, 'POST', '/stock/jornadas')).toHaveLength(6))

    const ids = () =>
      llamadas(apiFetchMock, 'POST', '/stock/jornadas').map(({ init }) => new Headers(init.headers).get('Operation-Id'))
    expect(new Set(ids()).size).toBe(1)

    await usuario.selectOptions(screen.getByLabelText('Ubicación'), CAMIONETA_3)
    await usuario.click(screen.getByRole('button', { name: 'Abrir jornada' }))
    await waitFor(() => expect(llamadas(apiFetchMock, 'POST', '/stock/jornadas').length).toBeGreaterThan(6))
    expect(new Set(ids()).size).toBe(2)
  })

  it('un usuario con una jornada abierta ve un enlace a ella', async () => {
    enrutar(apiFetchMock, [
      REGLA_UBICACIONES,
      { ruta: '/stock/jornadas/actual', responder: () => ({ status: 200, cuerpo: detalle('ABIERTA') }) },
    ])
    renderEn('/admin/stock/jornadas/abrir', 'VEN')

    const enlace = await screen.findByRole('link', { name: /Ver mi jornada/ })
    expect(enlace).toHaveAttribute('href', `/admin/stock/jornadas/${JORNADA}`)
  })

  it('sin ABRIR_JORNADA la pantalla no se monta ni pide nada', async () => {
    enrutar(apiFetchMock, [REGLA_UBICACIONES])
    renderEn('/admin/stock/jornadas/abrir', 'GES')

    expect(await screen.findByText('No tenés permiso para abrir jornadas.')).toBeInTheDocument()
    expect(llamadas(apiFetchMock, 'GET', '/stock/ubicaciones')).toHaveLength(0)
    expect(llamadas(apiFetchMock, 'GET', '/stock/jornadas/actual')).toHaveLength(0)
  })
})

describe('rendir, cerrar y liberar desde el detalle (tarea 14.2; RUT-09, D13)', () => {
  function reglasMutables(inicial: Estado) {
    let actual: Estado = inicial
    let extra: Record<string, unknown> = {}
    return [
      { ruta: `/stock/jornadas/${JORNADA}`, responder: () => ({ status: 200, cuerpo: detalle(actual, extra) }) },
      REGLA_MOTIVOS,
      {
        metodo: 'POST',
        ruta: `/stock/jornadas/${JORNADA}/rendicion`,
        responder: () => {
          actual = 'EN_RENDICION'
          return { status: 200, cuerpo: { id: JORNADA, estado: 'EN_RENDICION' } }
        },
      },
      {
        metodo: 'POST',
        ruta: `/stock/jornadas/${JORNADA}/cierre`,
        responder: () => {
          actual = 'CERRADA'
          return { status: 200, cuerpo: { id: JORNADA, estado: 'CERRADA' } }
        },
      },
      {
        metodo: 'POST',
        ruta: `/stock/jornadas/${JORNADA}/liberacion`,
        responder: () => {
          actual = 'LIBERADA'
          extra = {
            liberada_en: '2026-04-10T21:00:00Z',
            liberada_por_nombre: 'Supervisora Sol',
            motivo_liberacion_nombre: 'Vendedor ausente',
            observacion_liberacion: 'No vino',
          }
          return { status: 200, cuerpo: { id: JORNADA, estado: 'LIBERADA' } }
        },
      },
    ]
  }

  it('Rendir pide confirmación y, al aceptarse, el detalle pasa a En rendición', async () => {
    enrutar(apiFetchMock, reglasMutables('ABIERTA'))
    const usuario = userEvent.setup()
    renderEn(`/admin/stock/jornadas/${JORNADA}`, 'SUP')

    await usuario.click(await screen.findByRole('button', { name: 'Rendir' }))
    expect(llamadas(apiFetchMock, 'POST', `/stock/jornadas/${JORNADA}/rendicion`)).toHaveLength(0)
    const dialogo = await screen.findByRole('dialog')
    expect(within(dialogo).getByText(/requiere conexión/)).toBeInTheDocument()
    await usuario.click(within(dialogo).getByRole('button', { name: 'Confirmar' }))

    expect(await screen.findByText('En rendición', { selector: 'span' })).toBeInTheDocument()
    expect(llamadas(apiFetchMock, 'POST', `/stock/jornadas/${JORNADA}/rendicion`)).toHaveLength(1)
    expect(screen.queryByRole('button', { name: 'Rendir' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Cerrar' })).toBeInTheDocument()
  })

  it('cancelar la confirmación no envía nada', async () => {
    enrutar(apiFetchMock, reglasMutables('ABIERTA'))
    const usuario = userEvent.setup()
    renderEn(`/admin/stock/jornadas/${JORNADA}`, 'SUP')

    await usuario.click(await screen.findByRole('button', { name: 'Rendir' }))
    await usuario.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Cancelar' }))

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(llamadas(apiFetchMock, 'POST', `/stock/jornadas/${JORNADA}/rendicion`)).toHaveLength(0)
  })

  it('Cerrar pide confirmación y deja la jornada Cerrada sin acciones', async () => {
    enrutar(apiFetchMock, reglasMutables('EN_RENDICION'))
    const usuario = userEvent.setup()
    renderEn(`/admin/stock/jornadas/${JORNADA}`, 'GES')

    await usuario.click(await screen.findByRole('button', { name: 'Cerrar' }))
    await usuario.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Confirmar' }))

    expect(await screen.findByText('Cerrada', { selector: 'span' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Cerrar' })).not.toBeInTheDocument()
  })

  it('Liberar exige motivo: sin elegirlo no envía nada y lo pide', async () => {
    enrutar(apiFetchMock, reglasMutables('ABIERTA'))
    const usuario = userEvent.setup()
    renderEn(`/admin/stock/jornadas/${JORNADA}`, 'SUP')

    await usuario.click(await screen.findByRole('button', { name: 'Liberar' }))
    const dialogo = await screen.findByRole('dialog')
    await usuario.click(within(dialogo).getByRole('button', { name: 'Confirmar liberación' }))

    expect(await within(dialogo).findByText('Elegí el motivo de la liberación.')).toBeInTheDocument()
    expect(llamadas(apiFetchMock, 'POST', `/stock/jornadas/${JORNADA}/liberacion`)).toHaveLength(0)
    const ambitos = llamadas(apiFetchMock, 'GET', '/configuracion/motivos').map((c) => c.url.searchParams.get('ambito'))
    expect(ambitos).toContain('LIBERACION_JORNADA')
  })

  it('después de liberar, el detalle pasa a Liberada con motivo, quién y cuándo, sin acciones', async () => {
    enrutar(apiFetchMock, reglasMutables('ABIERTA'))
    const usuario = userEvent.setup()
    renderEn(`/admin/stock/jornadas/${JORNADA}`, 'SUP')

    await usuario.click(await screen.findByRole('button', { name: 'Liberar' }))
    const dialogo = await screen.findByRole('dialog')
    await usuario.selectOptions(await within(dialogo).findByLabelText('Motivo'), MOTIVO)
    await usuario.type(within(dialogo).getByLabelText('Observación'), 'No vino')
    await usuario.click(within(dialogo).getByRole('button', { name: 'Confirmar liberación' }))

    const liberacion = await screen.findByTestId('liberacion')
    expect(liberacion).toHaveTextContent('Vendedor ausente')
    expect(liberacion).toHaveTextContent('Supervisora Sol')
    expect(liberacion).toHaveTextContent('No vino')
    expect(liberacion).toHaveTextContent(/\d{2}\/\d{2}\/\d{4} \d{2}:\d{2}/)
    expect(screen.getByText('Liberada', { selector: 'span' })).toBeInTheDocument()
    for (const nombre of ['Rendir', 'Cerrar', 'Liberar']) {
      expect(screen.queryByRole('button', { name: nombre })).not.toBeInTheDocument()
    }
    const envio = llamadas(apiFetchMock, 'POST', `/stock/jornadas/${JORNADA}/liberacion`)[0]
    expect(JSON.parse(String(envio?.init.body))).toEqual({ motivo_id: MOTIVO, observacion: 'No vino' })
  })

  it('un rechazo JORNADA_ESTADO_INVALIDO se muestra en el diálogo', async () => {
    const reglas = reglasMutables('ABIERTA').map((r) =>
      r.ruta === `/stock/jornadas/${JORNADA}/rendicion`
        ? { ...r, responder: () => ({ status: 409, cuerpo: { title: 'x', codigo: 'JORNADA_ESTADO_INVALIDO' } }) }
        : r,
    )
    enrutar(apiFetchMock, reglas)
    const usuario = userEvent.setup()
    renderEn(`/admin/stock/jornadas/${JORNADA}`, 'SUP')

    await usuario.click(await screen.findByRole('button', { name: 'Rendir' }))
    await usuario.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Confirmar' }))

    expect(await screen.findByText(/La jornada ya cambió de estado/)).toBeInTheDocument()
  })
})

describe('cargar vehículo desde la jornada (tarea 14.2; RUT-02)', () => {
  it('lleva al alta de transferencia con la camioneta como destino', async () => {
    enrutar(apiFetchMock, [
      { ruta: `/stock/jornadas/${JORNADA}`, responder: () => ({ status: 200, cuerpo: detalle('ABIERTA') }) },
      REGLA_UBICACIONES,
      { ruta: /\/stock\/ubicaciones\/.*\/saldos/, responder: () => ({ status: 200, cuerpo: { items: [], cursor_siguiente: null } }) },
    ])
    const usuario = userEvent.setup()
    renderEn(`/admin/stock/jornadas/${JORNADA}`, 'VEN')

    await usuario.click(await screen.findByRole('link', { name: 'Cargar vehículo' }))

    expect(screen.getByTestId('ruta')).toHaveTextContent(`/admin/stock/transferencias/nueva?destino=${CAMIONETA_1}`)
    const destino = await screen.findByLabelText('Destino')
    await waitFor(() => expect(destino).toHaveValue(CAMIONETA_1))
  })

  it('no se ofrece en una jornada En rendición', async () => {
    enrutar(apiFetchMock, [{ ruta: `/stock/jornadas/${JORNADA}`, responder: () => ({ status: 200, cuerpo: detalle('EN_RENDICION') }) }])
    renderEn(`/admin/stock/jornadas/${JORNADA}`, 'VEN')

    await screen.findByText('En rendición', { selector: 'span' })
    expect(screen.queryByRole('link', { name: 'Cargar vehículo' })).not.toBeInTheDocument()
  })
})
