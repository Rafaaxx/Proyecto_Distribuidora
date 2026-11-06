import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }))
vi.mock('../../../../../src/lib/api/httpClient', () => ({ apiFetch: apiFetchMock }))

import StockArea from '../../../../../src/areas/admin/stock/StockArea'
import { formatearHora } from '../../../../../src/lib/fecha'
import { enrutar, llamadas, type ReglaDeApi } from '../../../utils/enrutarApi'
import { queryClientConYo, type RolDePrueba } from '../../../utils/permisosDePrueba'

/**
 * Change 24, tarea 13.1 (D4, D6, D8, D9; cita RUT-05, RUT-07, RUT-08, `01` §19): el detalle de la
 * jornada muestra la entrega o su falta, «Rendir» deshabilitado sin entrega, el resumen y el
 * diálogo de cierre con «Devolver el remanente a» (solo con `TRANSFERIR_STOCK`), con las líneas
 * precargadas con lo contado.
 */
const JORNADA = '33333333-3333-4333-8333-333333333333'
const CAMIONETA_1 = '22222222-2222-4222-8222-222222222221'
const DEPOSITO = '11111111-1111-4111-8111-111111111111'
const DEPOSITO_INACTIVO = '11111111-1111-4111-8111-111111111112'
const JUAN = '44444444-4444-4444-8444-444444444444'
const DISPOSITIVO = '55555555-5555-4555-8555-555555555555'
const VINO = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1'
const GASEOSA = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa2'
const TRANSFERENCIA = '77777777-7777-4777-8777-777777777777'
const ENTREGA = '2026-04-10T19:30:00Z'

function detalle(estado: string, entregada: boolean, extra: Record<string, unknown> = {}) {
  return {
    id: JORNADA,
    ubicacion_id: CAMIONETA_1,
    ubicacion_nombre: 'Camioneta 1',
    usuario_id: JUAN,
    usuario_nombre: 'Juan',
    dispositivo_id: DISPOSITIVO,
    estado,
    abierta_en: '2026-04-10T11:00:00Z',
    entregada_en: entregada ? ENTREGA : null,
    rendida_en: estado === 'EN_RENDICION' ? '2026-04-10T20:00:00Z' : null,
    rendida_por_id: null,
    rendida_por_nombre: estado === 'EN_RENDICION' ? 'Supervisora Sol' : null,
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

const SIN_DINERO = { cantidad: 0, total: '0.00' }
const SIN_COBRANZAS = { cantidad: 0, total: '0.00', por_medio: [] }
const RESUMEN = {
  jornada_id: JORNADA,
  estado: 'EN_RENDICION',
  con_conteo: true,
  rendida_en: '2026-04-10T20:00:00Z',
  lineas: [
    { producto_id: VINO, al_abrir: 10, ingresos: 36, ventas: 8, anulaciones: 2, otros: 0, esperado: 40, contado: 37, diferencia: -3 },
    { producto_id: GASEOSA, al_abrir: 0, ingresos: 12, ventas: 0, anulaciones: 0, otros: 0, esperado: 12, contado: 12, diferencia: 0 },
  ],
  dinero: { ventas: SIN_DINERO, anuladas: SIN_DINERO, cobranzas: SIN_COBRANZAS, cobranzas_anuladas: SIN_COBRANZAS },
  despues_de_la_rendicion: null,
}
const PRODUCTOS = {
  items: [
    { id: VINO, codigo: 'V1', nombre: 'Vino A', activo: true },
    { id: GASEOSA, codigo: 'G1', nombre: 'Gaseosa', activo: true },
  ],
  cursor_siguiente: null,
}
const SALDOS = {
  items: [
    { producto_id: VINO, producto_codigo: 'V1', producto_nombre: 'Vino A', cantidad_base: 37, unidades_referencia: 6, nombre_referencia: 'Caja x6' },
    { producto_id: GASEOSA, producto_codigo: 'G1', producto_nombre: 'Gaseosa', cantidad_base: 12, unidades_referencia: null, nombre_referencia: null },
  ],
  cursor_siguiente: null,
}
const BASE_UBICACION = { actualizado_en: '2026-01-01T00:00:00Z' }
const UBICACIONES = {
  items: [
    { ...BASE_UBICACION, id: CAMIONETA_1, nombre: 'Camioneta 1', tipo: 'VEHICULO', requiere_toma: true, activo: true, jornada: null },
    { ...BASE_UBICACION, id: DEPOSITO, nombre: 'Depósito central', tipo: 'DEPOSITO', requiere_toma: false, activo: true, jornada: null },
    { ...BASE_UBICACION, id: DEPOSITO_INACTIVO, nombre: 'Depósito viejo', tipo: 'DEPOSITO', requiere_toma: false, activo: false, jornada: null },
  ],
  cursor_siguiente: null,
}

function reglas(estado: string, entregada: boolean, extra: ReglaDeApi[] = []): ReglaDeApi[] {
  return [
    ...extra,
    { ruta: `/stock/jornadas/${JORNADA}`, responder: () => ({ status: 200, cuerpo: detalle(estado, entregada) }) },
    { ruta: `/stock/jornadas/${JORNADA}/resumen`, responder: () => ({ status: 200, cuerpo: { ...RESUMEN, estado } }) },
    { ruta: '/catalogo/productos', responder: () => ({ status: 200, cuerpo: PRODUCTOS }) },
    { ruta: `/stock/ubicaciones/${CAMIONETA_1}/saldos`, responder: () => ({ status: 200, cuerpo: SALDOS }) },
    { ruta: '/stock/ubicaciones', responder: () => ({ status: 200, cuerpo: UBICACIONES }) },
    { metodo: 'POST', ruta: `/stock/jornadas/${JORNADA}/cierre`, responder: () => ({ status: 200, cuerpo: { id: JORNADA, estado: 'CERRADA', transferencia_id: null } }) },
  ]
}

function UbicacionActual() {
  const { pathname } = useLocation()
  return <p data-testid="ruta">{pathname}</p>
}

function renderEn(rol: RolDePrueba, permisos?: string[]) {
  const cliente = queryClientConYo(rol, permisos === undefined ? {} : { permisos: permisos as never })
  return render(
    <QueryClientProvider client={cliente}>
      <MemoryRouter initialEntries={[`/admin/stock/jornadas/${JORNADA}`]}>
        <UbicacionActual />
        <Routes>
          <Route path="/admin/stock/*" element={<StockArea />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

const cuerpoDelCierre = () => JSON.parse(String(llamadas(apiFetchMock, 'POST', `/stock/jornadas/${JORNADA}/cierre`)[0]?.init.body)) as Record<string, unknown>

beforeEach(() => {
  apiFetchMock.mockReset()
})
afterEach(() => {
  vi.clearAllMocks()
})

describe('detalle de la jornada: la entrega y «Rendir» (tarea 13.1; RUT-05, D9)', () => {
  it('con la entrega dice a qué hora llegó y habilita «Rendir», que lleva al conteo', async () => {
    enrutar(apiFetchMock, reglas('ABIERTA', true))
    const usuario = userEvent.setup()
    renderEn('SUP')

    expect(await screen.findByText(`Entregada por el vendedor a las ${formatearHora(ENTREGA)}.`)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Ayuda: Entrega del día' })).toBeInTheDocument()
    const rendir = screen.getByRole('button', { name: 'Rendir' })
    expect(rendir).toBeEnabled()
    await usuario.click(rendir)

    expect(screen.getByTestId('ruta')).toHaveTextContent(`/admin/stock/jornadas/${JORNADA}/rendicion`)
  })

  it('sin la entrega dice que el vendedor todavía no terminó el día y deja «Rendir» deshabilitado', async () => {
    enrutar(apiFetchMock, reglas('ABIERTA', false))
    renderEn('SUP')

    expect(await screen.findByText('El vendedor todavía no terminó el día en el teléfono.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Rendir' })).toBeDisabled()
  })

  it('una jornada rendida o cerrada no vuelve a mostrar el aviso de que falta la entrega', async () => {
    enrutar(apiFetchMock, reglas('EN_RENDICION', true))
    renderEn('SUP')

    await screen.findByText(`Entregada por el vendedor a las ${formatearHora(ENTREGA)}.`)
    expect(screen.queryByText('El vendedor todavía no terminó el día en el teléfono.')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Rendir' })).not.toBeInTheDocument()
  })

  it('muestra el resumen de la jornada debajo de sus datos', async () => {
    enrutar(apiFetchMock, reglas('EN_RENDICION', true))
    renderEn('SUP')

    expect(await screen.findByRole('heading', { name: 'Resumen de la jornada' })).toBeInTheDocument()
    expect(await screen.findByText('Vino A')).toBeInTheDocument()
    expect(llamadas(apiFetchMock, 'GET', `/stock/jornadas/${JORNADA}/resumen`)).toHaveLength(1)
  })
})

describe('detalle de la jornada: «Cerrar» con devolución del remanente (tarea 13.1; RUT-08, D6, D9)', () => {
  async function abrirCierre(rol: RolDePrueba = 'SUP', permisos?: string[]) {
    const usuario = userEvent.setup()
    renderEn(rol, permisos)
    await usuario.click(await screen.findByRole('button', { name: 'Cerrar' }))
    const dialogo = await screen.findByRole('dialog', { name: 'Cerrar jornada' })
    return { usuario, dialogo }
  }

  it('muestra el aviso de cierre y ofrece devolver el remanente solo a depósitos activos', async () => {
    enrutar(apiFetchMock, reglas('EN_RENDICION', true))
    const { dialogo } = await abrirCierre()

    expect(within(dialogo).getByText('Vas a cerrar la jornada de Camioneta 1 y liberar la ubicación.')).toBeInTheDocument()
    expect(within(dialogo).getByRole('button', { name: 'Ayuda: Devolver el remanente' })).toBeInTheDocument()
    const selector = await within(dialogo).findByLabelText('Devolver el remanente a')
    await waitFor(() => expect(within(selector).getAllByRole('option').map((o) => o.textContent)).toContain('Depósito central'))
    const opciones = within(selector).getAllByRole('option').map((o) => o.textContent)
    expect(opciones.join('|')).not.toMatch(/Depósito viejo|Camioneta 1/)
  })

  it('sin elegir destino cierra sin devolución: cuerpo vacío', async () => {
    enrutar(apiFetchMock, reglas('EN_RENDICION', true))
    const { usuario, dialogo } = await abrirCierre()

    await usuario.click(within(dialogo).getByRole('button', { name: 'Confirmar' }))

    await waitFor(() => expect(llamadas(apiFetchMock, 'POST', `/stock/jornadas/${JORNADA}/cierre`)).toHaveLength(1))
    expect(cuerpoDelCierre()).toEqual({})
  })

  it('al elegir el destino precarga todo lo contado en cajas y unidades, editable, y dice cuántos productos se transfieren', async () => {
    enrutar(apiFetchMock, reglas('EN_RENDICION', true))
    const { usuario, dialogo } = await abrirCierre()

    await usuario.selectOptions(await within(dialogo).findByLabelText('Devolver el remanente a'), DEPOSITO)

    expect(await within(dialogo).findByLabelText('Cajas de Vino A')).toHaveValue('6')
    expect(within(dialogo).getByLabelText('Unidades de Vino A')).toHaveValue('1')
    expect(within(dialogo).getByLabelText('Unidades de Gaseosa')).toHaveValue('12')
    expect(within(dialogo).getByText('Cantidad a devolver', { selector: 'th, th *' })).toBeInTheDocument()
    expect(within(dialogo).getByText('Se transfieren 2 productos a Depósito central.')).toBeInTheDocument()

    await usuario.clear(within(dialogo).getByLabelText('Unidades de Gaseosa'))
    await usuario.type(within(dialogo).getByLabelText('Unidades de Gaseosa'), '0')
    expect(within(dialogo).getByText('Se transfiere 1 producto a Depósito central.')).toBeInTheDocument()
  })

  it('con una referencia de una unidad (Botella) muestra un solo campo, el total en unidades y transfiere 97', async () => {
    const BOTELLAS = { ...SALDOS, items: [{ producto_id: VINO, producto_codigo: 'V1', producto_nombre: 'Vino A', cantidad_base: 97, unidades_referencia: 1, nombre_referencia: 'Botella' }] }
    const RESUMEN_97 = { ...RESUMEN, lineas: [{ ...RESUMEN.lineas[0], contado: 97 }] }
    enrutar(
      apiFetchMock,
      reglas('EN_RENDICION', true, [
        { ruta: `/stock/ubicaciones/${CAMIONETA_1}/saldos`, responder: () => ({ status: 200, cuerpo: BOTELLAS }) },
        { ruta: `/stock/jornadas/${JORNADA}/resumen`, responder: () => ({ status: 200, cuerpo: RESUMEN_97 }) },
      ]),
    )
    const { usuario, dialogo } = await abrirCierre()
    await usuario.selectOptions(await within(dialogo).findByLabelText('Devolver el remanente a'), DEPOSITO)

    const campo = await within(dialogo).findByLabelText('Unidades de Vino A')
    expect(campo).toHaveValue('97')
    expect(within(dialogo).queryByLabelText('Cajas de Vino A')).not.toBeInTheDocument()
    expect(within(dialogo).getByText('Total: 97 unidades')).toBeInTheDocument()

    await usuario.clear(campo)
    await usuario.type(campo, '50')
    expect(within(dialogo).getByText('Total: 50 unidades')).toBeInTheDocument()
    await usuario.clear(campo)
    await usuario.type(campo, '97')
    await usuario.click(within(dialogo).getByRole('button', { name: 'Confirmar' }))

    await waitFor(() => expect(llamadas(apiFetchMock, 'POST', `/stock/jornadas/${JORNADA}/cierre`)).toHaveLength(1))
    expect(cuerpoDelCierre()).toEqual({ devolucion: { ubicacion_destino_id: DEPOSITO, lineas: [{ producto_id: VINO, cantidad_base: 97 }] } })
  })

  it('con una referencia de varias unidades muestra el total en unidades junto a las cajas', async () => {
    enrutar(apiFetchMock, reglas('EN_RENDICION', true))
    const { usuario, dialogo } = await abrirCierre()
    await usuario.selectOptions(await within(dialogo).findByLabelText('Devolver el remanente a'), DEPOSITO)

    await within(dialogo).findByLabelText('Cajas de Vino A')
    expect(within(dialogo).getByText('Total: 37 unidades (6 Caja x6 + 1 un.)')).toBeInTheDocument()
    expect(within(dialogo).getByText('Total: 12 unidades')).toBeInTheDocument()
  })

  it('no deja elegir el destino hasta que llegaron el resumen, los saldos y los productos; después precarga', async () => {
    enrutar(apiFetchMock, reglas('EN_RENDICION', true))
    const respuesta = apiFetchMock.getMockImplementation() as (ruta: string, init?: RequestInit) => Promise<unknown>
    let soltar: () => void = () => undefined
    const puerta = new Promise<void>((resolver) => {
      soltar = resolver
    })
    apiFetchMock.mockImplementation((ruta: string, init?: RequestInit) =>
      ruta.includes('/saldos') ? puerta.then(() => respuesta(ruta, init)) : respuesta(ruta, init),
    )
    const { usuario, dialogo } = await abrirCierre()

    const selector = await within(dialogo).findByLabelText('Devolver el remanente a')
    await waitFor(() => expect(within(selector).getAllByRole('option').map((o) => o.textContent)).toContain('Depósito central'))
    expect(selector).toBeDisabled()
    expect(within(dialogo).getByText('Cargando el remanente…')).toBeInTheDocument()

    soltar()
    await waitFor(() => expect(selector).toBeEnabled())
    expect(within(dialogo).queryByText('Cargando el remanente…')).not.toBeInTheDocument()
    await usuario.selectOptions(selector, DEPOSITO)

    expect(await within(dialogo).findByLabelText('Cajas de Vino A')).toHaveValue('6')
    expect(within(dialogo).getByText('Se transfieren 2 productos a Depósito central.')).toBeInTheDocument()
  })

  it('envía la devolución con las cantidades en unidad base y, aceptada, muestra el enlace a la transferencia', async () => {
    enrutar(
      apiFetchMock,
      reglas('EN_RENDICION', true, [
        { metodo: 'POST', ruta: `/stock/jornadas/${JORNADA}/cierre`, responder: () => ({ status: 200, cuerpo: { id: JORNADA, estado: 'CERRADA', transferencia_id: TRANSFERENCIA } }) },
      ]),
    )
    const { usuario, dialogo } = await abrirCierre()
    await usuario.selectOptions(await within(dialogo).findByLabelText('Devolver el remanente a'), DEPOSITO)
    await within(dialogo).findByLabelText('Cajas de Vino A')
    await usuario.click(within(dialogo).getByRole('button', { name: 'Confirmar' }))

    await waitFor(() => expect(llamadas(apiFetchMock, 'POST', `/stock/jornadas/${JORNADA}/cierre`)).toHaveLength(1))
    expect(cuerpoDelCierre()).toEqual({
      devolucion: {
        ubicacion_destino_id: DEPOSITO,
        lineas: [
          { producto_id: VINO, cantidad_base: 37 },
          { producto_id: GASEOSA, cantidad_base: 12 },
        ],
      },
    })
    const enlace = await screen.findByRole('link', { name: 'Ver transferencia' })
    expect(enlace).toHaveAttribute('href', `/admin/stock/transferencias/${TRANSFERENCIA}`)
  })

  it('elegido el destino, todo en cero pide una cantidad y no envía nada', async () => {
    enrutar(apiFetchMock, reglas('EN_RENDICION', true))
    const { usuario, dialogo } = await abrirCierre()
    await usuario.selectOptions(await within(dialogo).findByLabelText('Devolver el remanente a'), DEPOSITO)
    await usuario.clear(await within(dialogo).findByLabelText('Cajas de Vino A'))
    await usuario.clear(within(dialogo).getByLabelText('Unidades de Vino A'))
    await usuario.clear(within(dialogo).getByLabelText('Unidades de Gaseosa'))
    await usuario.click(within(dialogo).getByRole('button', { name: 'Confirmar' }))

    expect(await within(dialogo).findByText('Indicá la cantidad que se devuelve de al menos un producto.')).toBeInTheDocument()
    expect(llamadas(apiFetchMock, 'POST', `/stock/jornadas/${JORNADA}/cierre`)).toHaveLength(0)
  })

  it('UBICACION_CON_TOMA se muestra con su texto aprobado y el diálogo sigue abierto', async () => {
    enrutar(
      apiFetchMock,
      reglas('EN_RENDICION', true, [
        { metodo: 'POST', ruta: `/stock/jornadas/${JORNADA}/cierre`, responder: () => ({ status: 409, cuerpo: { title: 'x', codigo: 'UBICACION_CON_TOMA' } }) },
      ]),
    )
    const { usuario, dialogo } = await abrirCierre()
    await usuario.selectOptions(await within(dialogo).findByLabelText('Devolver el remanente a'), DEPOSITO)
    await within(dialogo).findByLabelText('Cajas de Vino A')
    await usuario.click(within(dialogo).getByRole('button', { name: 'Confirmar' }))

    expect(await within(dialogo).findByText('El destino es un vehículo con jornada; elegí un depósito.')).toBeInTheDocument()
    expect(screen.getByRole('dialog', { name: 'Cerrar jornada' })).toBeInTheDocument()
  })

  it('sin TRANSFERIR_STOCK no se ofrece devolver el remanente: solo el aviso de cierre (SEG-06)', async () => {
    enrutar(apiFetchMock, reglas('EN_RENDICION', true))
    const { dialogo } = await abrirCierre('SUP', ['RENDIR_JORNADA'])

    expect(within(dialogo).getByText('Vas a cerrar la jornada de Camioneta 1 y liberar la ubicación.')).toBeInTheDocument()
    expect(within(dialogo).queryByLabelText('Devolver el remanente a')).not.toBeInTheDocument()
    expect(llamadas(apiFetchMock, 'GET', '/stock/ubicaciones')).toHaveLength(0)
  })

  it('JORNADA_ESTADO_INVALIDO vuelve a leer la jornada', async () => {
    enrutar(
      apiFetchMock,
      reglas('EN_RENDICION', true, [
        { metodo: 'POST', ruta: `/stock/jornadas/${JORNADA}/cierre`, responder: () => ({ status: 409, cuerpo: { title: 'x', codigo: 'JORNADA_ESTADO_INVALIDO' } }) },
      ]),
    )
    const { usuario, dialogo } = await abrirCierre()
    const antes = llamadas(apiFetchMock, 'GET', `/stock/jornadas/${JORNADA}`).length

    await usuario.click(within(dialogo).getByRole('button', { name: 'Confirmar' }))

    expect(await within(dialogo).findByText(/La jornada ya cambió de estado/)).toBeInTheDocument()
    await waitFor(() => expect(llamadas(apiFetchMock, 'GET', `/stock/jornadas/${JORNADA}`).length).toBeGreaterThan(antes))
  })
})

/**
 * Change 25, tarea 15.3 (spec `stock/rendicion-de-jornada`, escenarios de pantalla; D9 = B, D12; RUT-05, SEG-06):
 * el detalle de la jornada avisa de los rechazos pendientes y deshabilita «Rendir».
 */
describe('detalle de la jornada: rechazos pendientes (tarea 15.3; D9 = B)', () => {
  const AVISO = (n: string) => `Esta jornada tiene ${n} sin resolver. Hay que resolverlas antes de rendir.`

  function reglasConRechazos(cantidad: number | undefined): ReglaDeApi[] {
    return [
      {
        ruta: `/stock/jornadas/${JORNADA}`,
        responder: () => ({ status: 200, cuerpo: { ...detalle('ABIERTA', true), rechazos_pendientes: cantidad } }),
      },
      ...reglas('ABIERTA', true),
    ]
  }

  it('con rechazos pendientes avisa cuántos, deshabilita «Rendir» y ofrece «Ver rechazadas» filtrada por la jornada', async () => {
    enrutar(apiFetchMock, reglasConRechazos(2))
    renderEn('SUP')

    expect(await screen.findByText(AVISO('2 operaciones rechazadas'))).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Rendir' })).toBeDisabled()
    expect(screen.getByRole('link', { name: 'Ver rechazadas' })).toHaveAttribute(
      'href',
      `/admin/revision/rechazadas?jornada=${JORNADA}`,
    )
  })

  it('con una sola dice «1 operación rechazada»', async () => {
    enrutar(apiFetchMock, reglasConRechazos(1))
    renderEn('SUP')

    expect(await screen.findByText(AVISO('1 operación rechazada'))).toBeInTheDocument()
  })

  it('sin REVISAR_OBSERVACIONES dice quién las resuelve y no ofrece el acceso ni pide la lista (SEG-06)', async () => {
    enrutar(apiFetchMock, reglasConRechazos(2))
    renderEn('SUP', ['TRANSFERIR_STOCK', 'RENDIR_JORNADA', 'ABRIR_JORNADA', 'LIBERAR_UBICACION'])

    expect(await screen.findByText(AVISO('2 operaciones rechazadas'))).toBeInTheDocument()
    expect(screen.getByText('Las resuelve quien revisa las observaciones.')).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Ver rechazadas' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Rendir' })).toBeDisabled()
    expect(llamadas(apiFetchMock, 'GET', '/observaciones/rechazos')).toHaveLength(0)
  })

  it('sin rechazos pendientes no hay aviso y «Rendir» queda habilitado', async () => {
    enrutar(apiFetchMock, reglasConRechazos(0))
    renderEn('SUP')

    expect(await screen.findByRole('button', { name: 'Rendir' })).toBeEnabled()
    expect(screen.queryByText(/operaciones? rechazadas? sin resolver/)).not.toBeInTheDocument()
  })

  it('un dato que no llegó cuenta como ninguno', async () => {
    enrutar(apiFetchMock, reglasConRechazos(undefined))
    renderEn('SUP')

    expect(await screen.findByRole('button', { name: 'Rendir' })).toBeEnabled()
    expect(screen.queryByText(/rechazadas? sin resolver/)).not.toBeInTheDocument()
  })
})
