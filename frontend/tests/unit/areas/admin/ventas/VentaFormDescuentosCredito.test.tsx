import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }))
vi.mock('../../../../../src/lib/api/httpClient', () => ({ apiFetch: apiFetchMock }))

import { VentaFormScreen } from '../../../../../src/areas/admin/ventas/VentaFormScreen'
import { llamadas, type ReglaDeApi } from '../../../utils/enrutarApi'
import { queryClientConYo, type RolDePrueba } from '../../../utils/permisosDePrueba'
import {
  CLIENTE_ID,
  CONSUMIDOR_FINAL_ID,
  VENTA_CONFIRMADA,
  VINO_ID,
  montarApi,
} from './ventasDePrueba'

/**
 * Change 18b, tarea 13.2 (spec `ventas/administracion-de-ventas`, D20): la pantalla "Nueva venta"
 * con descuentos, crédito y autorización. Cada prueba dice qué escenario cubre.
 */

const MARTA_ID = 'a2a2a2a2-a2a2-42a2-82a2-a2a2a2a2a2a2'
const JULIA_ID = 'a3a3a3a3-a3a3-43a3-83a3-a3a3a3a3a3a3'
const MOTIVO_ID = 'cccccccc-cccc-4ccc-8ccc-cccccccccccc'
const REGLA_ID = 'dddddddd-dddd-4ddd-8ddd-dddddddddddd'
const CERVEZA_ID = '99999999-9999-4999-8999-999999999993'
const PRESENTACION_CERVEZA_ID = '98989898-9898-4989-8989-989898989804'
const PIN = '482913'

const MARTA = { id: MARTA_ID, nombre: 'Marta', puede_autorizar_descuento: true, puede_superar_credito: true }
const JULIA = { id: JULIA_ID, nombre: 'Julia', puede_autorizar_descuento: false, puede_superar_credito: true }

function contexto(parcial: Record<string, unknown> = {}, descuento: Record<string, unknown> = {}, credito: Record<string, unknown> = {}) {
  return {
    descuento_manual: {
      habilitado: true,
      motivo_obligatorio: false,
      tiene_permiso: true,
      tope: '0.050000',
      puede_autorizar: false,
      ...descuento,
    },
    credito: { puede_superar: false, ...credito },
    motivos: [{ id: MOTIVO_ID, nombre: 'Cliente frecuente' }],
    autorizadores: [MARTA, JULIA],
    ...parcial,
  }
}

function reglaContexto(cuerpo: unknown): ReglaDeApi {
  return { metodo: 'GET', ruta: '/ventas/contexto', responder: () => ({ status: 200, cuerpo }) }
}

function reglaCredito(parcial: Record<string, unknown> = {}): ReglaDeApi {
  return {
    metodo: 'GET',
    ruta: '/ventas/credito',
    responder: () => ({
      status: 200,
      cuerpo: {
        cliente_id: CLIENTE_ID,
        limite: '200000.00',
        saldo: '150000.00',
        disponible: '50000.00',
        politica: 'ADVERTIR',
        tolerancia_tipo: null,
        tolerancia_valor: null,
        ...parcial,
      },
    }),
  }
}

const REGLA_VOLUMEN = {
  id: REGLA_ID,
  nombre: 'Volumen vinos',
  tipo: 'VOLUMEN_OPERACION',
  medida: 'IMPORTE_BRUTO',
  operador: 'GTE',
  umbral: '10000.00',
  accion_tipo: 'PORCENTAJE',
  accion_porcentaje: '0.050000',
  accion_importe: null,
  acumulable: false,
  prioridad: 1,
  alcances: [],
}

function reglaDescuentosAplicables(...items: unknown[]): ReglaDeApi {
  return { metodo: 'GET', ruta: '/ventas/descuentos-aplicables', responder: () => ({ status: 200, cuerpo: { items } }) }
}

const CERVEZA = {
  producto_id: CERVEZA_ID,
  codigo: 'P-003',
  nombre: 'Cerveza B',
  precio_referencia: '1000.00',
  unidades_referencia: 1,
  sin_precio: false,
  stock_base: 500,
  presentaciones: [{ presentacion_id: PRESENTACION_CERVEZA_ID, nombre: 'Botella', unidades_base: 1, es_referencia: true }],
}

function reglaPrecios(...items: unknown[]): ReglaDeApi {
  return {
    metodo: 'GET',
    ruta: '/ventas/precios',
    responder: (url) => {
      const q = (url.searchParams.get('q') ?? '').toLowerCase()
      const productoId = url.searchParams.get('producto_id')
      const visibles = (items as { producto_id: string; nombre: string }[]).filter(
        (p) => (productoId === null || p.producto_id === productoId) && (q === '' || p.nombre.toLowerCase().includes(q)),
      )
      return {
        status: 200,
        cuerpo: {
          lista_id: '44444444-4444-4444-8444-444444444444',
          lista_nombre: 'Mayorista',
          version_id: '66666666-6666-4666-8666-666666666666',
          version_numero: 2,
          ubicacion_id: '33333333-3333-4333-8333-333333333333',
          items: visibles,
          cursor_siguiente: null,
        },
      }
    },
  }
}

const confirmarOk: ReglaDeApi = {
  metodo: 'POST',
  ruta: '/ventas',
  responder: () => ({ status: 201, cuerpo: VENTA_CONFIRMADA }),
}

function rechazo(status: number, codigo: string, title: string, extra: Record<string, unknown> = {}): ReglaDeApi {
  return { metodo: 'POST', ruta: '/ventas', responder: () => ({ status, cuerpo: { title, codigo, ...extra } }) }
}

function renderPantalla(rol: RolDePrueba = 'VEN') {
  return render(
    <QueryClientProvider client={queryClientConYo(rol)}>
      <MemoryRouter initialEntries={['/admin/ventas/nueva']}>
        <Routes>
          <Route path="/admin/ventas/nueva" element={<VentaFormScreen />} />
          <Route path="/admin/ventas" element={<p>Listado de ventas</p>} />
          <Route path="/admin/ventas/:ventaId" element={<p>Detalle de la venta</p>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

type Usuario = ReturnType<typeof userEvent.setup>

async function elegirCliente(usuario: Usuario, id = CLIENTE_ID) {
  await screen.findByRole('option', { name: 'Kiosco La Esquina' })
  await usuario.selectOptions(screen.getByLabelText(/^cliente$/i), id)
  await screen.findByTestId('saldo-actual')
}

async function agregarProducto(usuario: Usuario, texto: string, id: string, nombre: RegExp) {
  await usuario.clear(screen.getByLabelText(/buscar producto/i))
  await usuario.type(screen.getByLabelText(/buscar producto/i), texto)
  const resultado = await screen.findByTestId(`resultado-${id}`)
  await usuario.click(within(resultado).getByRole('button', { name: nombre }))
  await screen.findByTestId(`item-${id}`)
}

async function cargarVino(usuario: Usuario, cajas: string, unidades: string) {
  const cajasInput = screen.getByLabelText(/cajas de vino a/i)
  const unidadesInput = screen.getByLabelText(/unidades sueltas de vino a/i)
  await usuario.clear(cajasInput)
  await usuario.type(cajasInput, cajas)
  await usuario.clear(unidadesInput)
  await usuario.type(unidadesInput, unidades)
}

/** 2 cajas + 3 botellas de Vino A: $ 31.250,00 (el ejemplo de 01 §9.2 a menor escala). */
async function ventaDeVino(usuario: Usuario) {
  await elegirCliente(usuario)
  await agregarProducto(usuario, 'vino', VINO_ID, /agregar vino a/i)
  await cargarVino(usuario, '2', '3')
}

const botonConfirmar = () => screen.getByRole('button', { name: /^confirmar venta$/i })

function cuerpoDelPost(indice = 0) {
  return JSON.parse(String(llamadas(apiFetchMock, 'POST', '/ventas')[indice]?.init.body)) as Record<string, any> // eslint-disable-line @typescript-eslint/no-explicit-any
}

describe('Nueva venta: tope y descuento manual (D15, D20; DSC-05, DSC-06)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
    window.localStorage.clear()
    window.sessionStorage.clear()
  })
  afterEach(() => {
    vi.clearAllMocks()
  })

  // Escenario: "El vendedor ve su tope"
  it('Pedro (tope 5 %) ve "Podés descontar hasta 5 %; más pide autorización."', async () => {
    montarApi(apiFetchMock, [reglaContexto(contexto())])
    renderPantalla()
    expect(await screen.findByTestId('aviso-de-tope')).toHaveTextContent('Podés descontar hasta 5 %; más pide autorización.')
  })

  // Escenario: "Sin permiso de descuento manual"
  it('sin DESCUENTO_MANUAL avisa que no puede y deshabilita el porcentaje general', async () => {
    montarApi(apiFetchMock, [reglaContexto(contexto({}, { tiene_permiso: false, tope: null }))])
    const usuario = userEvent.setup()
    renderPantalla()
    expect(await screen.findByTestId('aviso-de-tope')).toHaveTextContent('No podés dar descuentos manuales.')
    expect(screen.getByLabelText(/^descuento a toda la venta \(%\)$/i)).toBeDisabled()
    await elegirCliente(usuario)
    await agregarProducto(usuario, 'vino', VINO_ID, /agregar vino a/i)
    expect(screen.queryByLabelText(/descuento propio de vino a/i)).not.toBeInTheDocument()
  })

  // Escenario: "Cuál porcentaje rige en cada línea"
  it('un general de 5 % y un propio de 10 % en el vino: el vino muestra "10 % (propio)" y las demás líneas "5 % (general)"', async () => {
    montarApi(apiFetchMock, [reglaContexto(contexto({}, { tope: '1.000000' })), reglaPrecios(CERVEZA, { ...CERVEZA, producto_id: VINO_ID, nombre: 'Vino A', precio_referencia: '12500.00', unidades_referencia: 6, presentaciones: [{ presentacion_id: '98989898-9898-4989-8989-989898989802', nombre: 'Caja x6', unidades_base: 6, es_referencia: true }, { presentacion_id: '98989898-9898-4989-8989-989898989801', nombre: 'Botella', unidades_base: 1, es_referencia: false }] })])
    const usuario = userEvent.setup()
    renderPantalla()
    await elegirCliente(usuario)
    await agregarProducto(usuario, 'vino', VINO_ID, /agregar vino a/i)
    await cargarVino(usuario, '2', '0')
    await agregarProducto(usuario, 'cerveza', CERVEZA_ID, /agregar cerveza b/i)
    await usuario.clear(screen.getByLabelText(/unidades sueltas de cerveza b/i))
    await usuario.type(screen.getByLabelText(/unidades sueltas de cerveza b/i), '10')

    await usuario.type(screen.getByLabelText(/^descuento a toda la venta \(%\)$/i), '5')
    await usuario.type(screen.getByLabelText(/descuento propio de vino a/i), '10')

    const vino = screen.getByTestId(`item-${VINO_ID}`)
    expect(within(vino).getByText(/10 % \(propio\)/)).toBeInTheDocument()
    const cerveza = screen.getByTestId(`item-${CERVEZA_ID}`)
    expect(within(cerveza).getByText(/5 % \(general\)/)).toBeInTheDocument()
    // 25.000 al 10 % + 10.000 al 5 %: neto 22.500 + 9.500 = 32.000.
    expect(screen.getByTestId('total-de-la-venta')).toHaveTextContent('$ 32.000,00')
    expect(screen.getByTestId('descuentos-de-la-venta')).toHaveTextContent('$ 3.000,00')
  })

  it('un porcentaje inválido (0, mayor que 100, con letras) se avisa y no deja confirmar', async () => {
    montarApi(apiFetchMock, [reglaContexto(contexto({}, { tope: '1.000000' })), confirmarOk])
    const usuario = userEvent.setup()
    renderPantalla()
    await ventaDeVino(usuario)
    await waitFor(() => expect(botonConfirmar()).toBeEnabled())

    await usuario.type(screen.getByLabelText(/^descuento a toda la venta \(%\)$/i), '0')
    expect(screen.getByText(/mayor que 0 y hasta 100/i)).toBeInTheDocument()
    expect(botonConfirmar()).toBeDisabled()
    await usuario.clear(screen.getByLabelText(/^descuento a toda la venta \(%\)$/i))
    await usuario.type(screen.getByLabelText(/^descuento a toda la venta \(%\)$/i), '150')
    expect(botonConfirmar()).toBeDisabled()
    await usuario.clear(screen.getByLabelText(/^descuento a toda la venta \(%\)$/i))
    expect(botonConfirmar()).toBeEnabled()
  })

  it('dentro del tope envía el general, el propio y los descuentos esperados con su importe, sin autorizador', async () => {
    montarApi(apiFetchMock, [reglaContexto(contexto()), confirmarOk])
    const usuario = userEvent.setup()
    renderPantalla()
    await ventaDeVino(usuario)
    await usuario.type(screen.getByLabelText(/^descuento a toda la venta \(%\)$/i), '5')
    await waitFor(() => expect(botonConfirmar()).toBeEnabled())
    await usuario.click(botonConfirmar())

    await screen.findByText(/venta registrada/i)
    const cuerpo = cuerpoDelPost()
    expect(cuerpo.descuento_manual_general).toBe('0.050000')
    expect(cuerpo.total).toBe('29687.50')
    expect(cuerpo.descuento_autorizador_id).toBeUndefined()
    expect(cuerpo.credenciales).toBeUndefined()
    expect(cuerpo.lineas[0].descuentos).toEqual([{ origen: 'MANUAL', regla_id: null, porcentaje: '0.050000', importe: '1250.00' }])
    expect(cuerpo.lineas[1].descuentos).toEqual([{ origen: 'MANUAL', regla_id: null, porcentaje: '0.050000', importe: '312.50' }])
  })

  // Escenario: "El vendedor ve los descuentos automáticos antes de confirmar" (DSC-05, ADR-050)
  it('con una regla vigente muestra el descuento automático con el nombre de la regla antes de confirmar y lo envía', async () => {
    montarApi(apiFetchMock, [reglaContexto(contexto()), reglaDescuentosAplicables(REGLA_VOLUMEN), confirmarOk])
    const usuario = userEvent.setup()
    renderPantalla()
    await ventaDeVino(usuario) // 25.000 + 6.250 = 31.250 de bruto, supera 10.000

    const automaticos = await screen.findAllByTestId(/^descuento-.*-0$/)
    expect(automaticos).toHaveLength(2)
    expect(automaticos[0]).toHaveTextContent('Descuento automático «Volumen vinos» 5 %: −$ 1.250,00')
    expect(automaticos[1]).toHaveTextContent('Descuento automático «Volumen vinos» 5 %: −$ 312,50')
    expect(screen.getByTestId('total-de-la-venta')).toHaveTextContent('$ 29.687,50')

    await waitFor(() => expect(botonConfirmar()).toBeEnabled())
    await usuario.click(botonConfirmar())
    await screen.findByText(/venta registrada/i)
    const cuerpo = cuerpoDelPost()
    expect(cuerpo.total).toBe('29687.50')
    expect(cuerpo.lineas[0].descuentos).toEqual([
      { origen: 'AUTOMATICO', regla_id: REGLA_ID, porcentaje: '0.050000', importe: '1250.00' },
    ])
    expect(cuerpo.lineas[1].descuentos).toEqual([
      { origen: 'AUTOMATICO', regla_id: REGLA_ID, porcentaje: '0.050000', importe: '312.50' },
    ])
  })

  it('si la consulta de reglas falla, la pantalla sigue (el servidor decide) y no inventa descuentos', async () => {
    montarApi(apiFetchMock, [reglaContexto(contexto()), confirmarOk])
    const usuario = userEvent.setup()
    renderPantalla()
    await ventaDeVino(usuario)
    expect(screen.queryByText(/descuento automático/i)).not.toBeInTheDocument()
    expect(screen.getByTestId('total-de-la-venta')).toHaveTextContent('$ 31.250,00')
  })

  // ADR-050, DSC-08: el propio es por línea, no por producto
  it('el propio de la línea de cajas no toca la línea de botellas del mismo producto', async () => {
    montarApi(apiFetchMock, [reglaContexto(contexto({}, { tope: '1.000000' })), confirmarOk])
    const usuario = userEvent.setup()
    renderPantalla()
    await ventaDeVino(usuario) // 2 cajas (25.000) + 3 botellas (6.250)
    await usuario.type(screen.getByLabelText(/descuento propio de vino a \(caja x6\)/i), '10')

    const vino = screen.getByTestId(`item-${VINO_ID}`)
    expect(within(vino).getAllByText(/10 % \(propio\)/)).toHaveLength(1)
    expect(screen.getByLabelText(/descuento propio de vino a \(botella\)/i)).toHaveValue('')
    // Solo las cajas: 25.000 - 2.500 + 6.250 = 28.750.
    expect(screen.getByTestId('total-de-la-venta')).toHaveTextContent('$ 28.750,00')

    await waitFor(() => expect(botonConfirmar()).toBeEnabled())
    await usuario.click(botonConfirmar())
    await screen.findByText(/venta registrada/i)
    const cuerpo = cuerpoDelPost()
    expect(cuerpo.lineas[0].descuento_manual).toBe('0.100000')
    expect(cuerpo.lineas[1].descuento_manual).toBeUndefined()
    expect(cuerpo.lineas[1].descuentos).toBeUndefined()
  })

  it('dos propios distintos en las dos líneas del mismo producto se envían cada uno en la suya', async () => {
    montarApi(apiFetchMock, [reglaContexto(contexto({}, { tope: '1.000000' })), confirmarOk])
    const usuario = userEvent.setup()
    renderPantalla()
    await ventaDeVino(usuario)
    await usuario.type(screen.getByLabelText(/descuento propio de vino a \(caja x6\)/i), '10')
    await usuario.type(screen.getByLabelText(/descuento propio de vino a \(botella\)/i), '4')
    await waitFor(() => expect(botonConfirmar()).toBeEnabled())
    await usuario.click(botonConfirmar())
    await screen.findByText(/venta registrada/i)
    const cuerpo = cuerpoDelPost()
    expect(cuerpo.lineas[0].descuento_manual).toBe('0.100000')
    expect(cuerpo.lineas[1].descuento_manual).toBe('0.040000')
  })

  // Escenario: motivo obligatorio (DSC-06)
  it('con motivo obligatorio pide elegirlo y lo envía', async () => {
    montarApi(apiFetchMock, [reglaContexto(contexto({}, { motivo_obligatorio: true })), confirmarOk])
    const usuario = userEvent.setup()
    renderPantalla()
    await ventaDeVino(usuario)
    expect(screen.queryByLabelText(/^motivo del descuento/i)).not.toBeInTheDocument()
    await usuario.type(screen.getByLabelText(/^descuento a toda la venta \(%\)$/i), '3')
    expect(await screen.findByText('Elegí el motivo del descuento.')).toBeInTheDocument()
    expect(botonConfirmar()).toBeDisabled()

    await usuario.selectOptions(screen.getByLabelText(/^motivo del descuento/i), MOTIVO_ID)
    await waitFor(() => expect(botonConfirmar()).toBeEnabled())
    await usuario.click(botonConfirmar())
    await screen.findByText(/venta registrada/i)
    expect(cuerpoDelPost().motivo_descuento_id).toBe(MOTIVO_ID)
  })

  // Escenario: "Los descuentos automáticos cambian"
  it('DESCUENTO_DIFIERE muestra los descuentos del servidor y, al aceptarlos, la pantalla los usa para reenviar', async () => {
    let intento = 0
    montarApi(apiFetchMock, [
      reglaContexto(contexto()),
      {
        metodo: 'POST',
        ruta: '/ventas',
        responder: (_url, init) => {
          intento += 1
          const enviadas = (JSON.parse(String(init?.body)) as { lineas: { linea_id: string; importe_bruto: string }[] }).lineas
          if (intento > 1) return { status: 201, cuerpo: VENTA_CONFIRMADA }
          return {
            status: 409,
            cuerpo: {
              title: 'Los descuentos difieren de los que vio el usuario.',
              codigo: 'DESCUENTO_DIFIERE',
              lineas: enviadas.map((l) => ({
                linea_id: l.linea_id,
                descuentos: [
                  {
                    origen: 'AUTOMATICO',
                    regla_id: REGLA_ID,
                    porcentaje: '0.050000',
                    importe: l.importe_bruto === '25000.00' ? '1250.00' : '312.50',
                  },
                ],
              })),
            },
          }
        },
      },
    ])
    const usuario = userEvent.setup()
    renderPantalla()
    await ventaDeVino(usuario)
    await waitFor(() => expect(botonConfirmar()).toBeEnabled())
    await usuario.click(botonConfirmar())

    const dialogo = await screen.findByRole('dialog', { name: /cambiaron los descuentos/i })
    expect(dialogo).toHaveTextContent('descuento automático 5 %')
    expect(dialogo).toHaveTextContent('Total: $ 31.250,00 pasa a $ 29.687,50')
    expect(llamadas(apiFetchMock, 'POST', '/ventas')).toHaveLength(1)

    await usuario.click(within(dialogo).getByRole('button', { name: /aceptar los descuentos nuevos/i }))
    expect(await screen.findByTestId('descuentos-de-la-venta')).toHaveTextContent('$ 1.562,50')
    await usuario.click(botonConfirmar())
    await screen.findByText(/venta registrada/i)
    const cuerpo = cuerpoDelPost(1)
    expect(cuerpo.total).toBe('29687.50')
    expect(cuerpo.lineas[0].descuentos).toEqual([
      { origen: 'AUTOMATICO', regla_id: REGLA_ID, porcentaje: '0.050000', importe: '1250.00' },
    ])
  })
})

describe('Nueva venta: crédito (D5, D6, D16, D20; CRE-01 a CRE-07)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
    window.localStorage.clear()
    window.sessionStorage.clear()
  })
  afterEach(() => {
    vi.clearAllMocks()
  })

  it('muestra límite, deuda, disponible, saldo resultante, exceso y política con la cuenta del servidor', async () => {
    montarApi(apiFetchMock, [reglaContexto(contexto()), reglaCredito({ limite: '160000.00', disponible: '10000.00' })])
    const usuario = userEvent.setup()
    renderPantalla()
    await ventaDeVino(usuario)

    const panel = await screen.findByTestId('panel-de-credito')
    expect(within(panel).getByTestId('credito-limite')).toHaveTextContent('$ 160.000,00')
    expect(within(panel).getByTestId('credito-saldo')).toHaveTextContent('$ 150.000,00')
    expect(within(panel).getByTestId('credito-disponible')).toHaveTextContent('$ 10.000,00')
    expect(within(panel).getByTestId('credito-resultante')).toHaveTextContent('$ 181.250,00')
    expect(within(panel).getByTestId('credito-exceso')).toHaveTextContent('$ 21.250,00')
    expect(within(panel).getByTestId('credito-politica')).toHaveTextContent('Advertir')
  })

  // Escenario: ADVERTIR (CRE-04)
  it('ADVERTIR pide confirmar el exceso: sin la casilla no se puede confirmar y con ella viaja acepta_exceso', async () => {
    montarApi(apiFetchMock, [reglaContexto(contexto()), reglaCredito({ limite: '160000.00' }), confirmarOk])
    const usuario = userEvent.setup()
    renderPantalla()
    await ventaDeVino(usuario)
    await screen.findByTestId('panel-de-credito')
    expect(botonConfirmar()).toBeDisabled()

    await usuario.click(screen.getByRole('checkbox', { name: /confirmo vender con exceso/i }))
    await waitFor(() => expect(botonConfirmar()).toBeEnabled())
    await usuario.click(botonConfirmar())
    await screen.findByText(/venta registrada/i)
    expect(cuerpoDelPost().credito).toEqual({ acepta_exceso: true })
  })

  // Escenario: "BLOQUEAR en pantalla" (CRE-07)
  it('BLOQUEAR no deja confirmar y sugiere aumentar la cobranza o sacar productos; cobrando todo se destraba', async () => {
    montarApi(apiFetchMock, [reglaContexto(contexto({}, {}, { puede_superar: true })), reglaCredito({ limite: '160000.00', politica: 'BLOQUEAR' }), confirmarOk])
    const usuario = userEvent.setup()
    renderPantalla()
    await ventaDeVino(usuario)

    const panel = await screen.findByTestId('panel-de-credito')
    expect(within(panel).getByTestId('credito-aviso')).toHaveTextContent('Aumentá la cobranza o sacá productos.')
    expect(botonConfirmar()).toBeDisabled()

    await usuario.click(screen.getByRole('button', { name: /agregar medio/i }))
    await screen.findByRole('option', { name: 'Efectivo' })
    await usuario.selectOptions(screen.getByLabelText(/^medio de pago$/i), screen.getByRole('option', { name: 'Efectivo' }).getAttribute('value') ?? '')
    await usuario.type(screen.getByLabelText(/^importe del medio$/i), '31250')
    await waitFor(() => expect(botonConfirmar()).toBeEnabled())
    expect(within(screen.getByTestId('panel-de-credito')).getByTestId('credito-exceso')).toHaveTextContent('$ 0,00')
  })

  it('con el crédito sin control (sin límite) el panel lo dice y no frena la venta', async () => {
    montarApi(apiFetchMock, [reglaContexto(contexto()), reglaCredito({ limite: null, disponible: null }), confirmarOk])
    const usuario = userEvent.setup()
    renderPantalla()
    await ventaDeVino(usuario)
    const panel = await screen.findByTestId('panel-de-credito')
    expect(panel).toHaveTextContent('Sin límite')
    expect(panel).toHaveTextContent('El cliente no tiene límite de crédito.')
    await waitFor(() => expect(botonConfirmar()).toBeEnabled())
  })

  it('al consumidor final no se le muestra panel de crédito (se vende de contado, CLI-03)', async () => {
    montarApi(apiFetchMock, [reglaContexto(contexto()), reglaCredito()])
    const usuario = userEvent.setup()
    renderPantalla()
    await screen.findByRole('option', { name: 'Consumidor final' })
    await usuario.selectOptions(screen.getByLabelText(/^cliente$/i), CONSUMIDOR_FINAL_ID)
    await screen.findByTestId('saldo-actual')
    expect(screen.queryByTestId('panel-de-credito')).not.toBeInTheDocument()
    expect(llamadas(apiFetchMock, 'GET', '/ventas/credito')).toHaveLength(0)
  })
})

describe('Nueva venta: autorización con PIN (D2, D4, D20; DSC-06, CRE-05, SEG-05)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
    window.localStorage.clear()
    window.sessionStorage.clear()
  })
  afterEach(() => {
    vi.clearAllMocks()
  })

  /** Descuento general de 8 % (sobre el tope de 5 %) y crédito AUTORIZAR con exceso. */
  async function ventaQuePideAutorizacion(usuario: Usuario) {
    await ventaDeVino(usuario)
    await usuario.type(screen.getByLabelText(/^descuento a toda la venta \(%\)$/i), '8')
    await screen.findByTestId('panel-de-credito')
    await waitFor(() => expect(botonConfirmar()).toBeEnabled())
    await usuario.click(botonConfirmar())
    return screen.findByRole('dialog', { name: /autorización/i })
  }

  const reglasDeAutorizacion = (autorizadores: unknown[] = [MARTA, JULIA]) => [
    reglaContexto(contexto({ autorizadores })),
    reglaCredito({ limite: '160000.00', politica: 'AUTORIZAR' }),
  ]

  // Escenario: "Pedir autorización una sola vez para la misma persona"
  it('descuento sobre el tope y exceso con AUTORIZAR: si Marta puede las dos cosas, el PIN se pide una sola vez', async () => {
    montarApi(apiFetchMock, [...reglasDeAutorizacion([MARTA]), confirmarOk])
    const usuario = userEvent.setup()
    renderPantalla()
    const dialogo = await ventaQuePideAutorizacion(usuario)

    expect(llamadas(apiFetchMock, 'POST', '/ventas')).toHaveLength(0)
    expect(within(dialogo).getByLabelText(/quién autoriza el descuento/i)).toHaveValue(MARTA_ID)
    expect(within(dialogo).getByLabelText(/quién autoriza el exceso de crédito/i)).toHaveValue(MARTA_ID)
    expect(within(dialogo).getAllByLabelText(/^pin de /i)).toHaveLength(1)

    const pin = within(dialogo).getByLabelText(/pin de marta/i)
    expect(pin).toHaveAttribute('type', 'password')
    await usuario.type(pin, PIN)
    await usuario.click(within(dialogo).getByRole('button', { name: /autorizar y registrar/i }))

    await screen.findByText(/venta registrada/i)
    const cuerpo = cuerpoDelPost()
    expect(cuerpo.credenciales).toEqual([{ autorizador_id: MARTA_ID, pin: PIN }])
    expect(cuerpo.descuento_autorizador_id).toBe(MARTA_ID)
    expect(cuerpo.credito).toEqual({ acepta_exceso: false, autorizador_id: MARTA_ID })
    expect(cuerpo.total).toBe('28750.00')
  })

  it('dos personas distintas: cada una pone su PIN y viajan dos credenciales', async () => {
    montarApi(apiFetchMock, [
      reglaContexto(contexto({ autorizadores: [{ ...MARTA, puede_superar_credito: false }, JULIA] })),
      reglaCredito({ limite: '160000.00', politica: 'AUTORIZAR' }),
      confirmarOk,
    ])
    const usuario = userEvent.setup()
    renderPantalla()
    const dialogo = await ventaQuePideAutorizacion(usuario)

    expect(within(dialogo).getAllByLabelText(/^pin de /i)).toHaveLength(2)
    await usuario.type(within(dialogo).getByLabelText(/pin de marta/i), PIN)
    await usuario.type(within(dialogo).getByLabelText(/pin de julia/i), '115599')
    await usuario.click(within(dialogo).getByRole('button', { name: /autorizar y registrar/i }))

    await screen.findByText(/venta registrada/i)
    const cuerpo = cuerpoDelPost()
    expect(cuerpo.credenciales).toEqual([
      { autorizador_id: MARTA_ID, pin: PIN },
      { autorizador_id: JULIA_ID, pin: '115599' },
    ])
    expect(cuerpo.descuento_autorizador_id).toBe(MARTA_ID)
    expect(cuerpo.credito.autorizador_id).toBe(JULIA_ID)
  })

  it('con permiso propio de autorizar no se pide nada y no viaja autorizador ni credencial (DSC-06)', async () => {
    montarApi(apiFetchMock, [
      reglaContexto(contexto({}, { puede_autorizar: true }, { puede_superar: true })),
      reglaCredito({ limite: '160000.00', politica: 'AUTORIZAR' }),
      confirmarOk,
    ])
    const usuario = userEvent.setup()
    renderPantalla()
    await ventaDeVino(usuario)
    await usuario.type(screen.getByLabelText(/^descuento a toda la venta \(%\)$/i), '8')
    await screen.findByTestId('panel-de-credito')
    await waitFor(() => expect(botonConfirmar()).toBeEnabled())
    await usuario.click(botonConfirmar())

    await screen.findByText(/venta registrada/i)
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    const cuerpo = cuerpoDelPost()
    expect(cuerpo.credenciales).toBeUndefined()
    expect(cuerpo.descuento_autorizador_id).toBeUndefined()
    expect(cuerpo.credito).toBeUndefined()
  })

  // Escenario: "PIN incorrecto"
  it('PIN_INCORRECTO lo muestra, borra el PIN escrito y la venta no se confirma', async () => {
    montarApi(apiFetchMock, [...reglasDeAutorizacion([MARTA]), rechazo(403, 'PIN_INCORRECTO', 'El PIN de autorización es incorrecto.')])
    const usuario = userEvent.setup()
    renderPantalla()
    const dialogo = await ventaQuePideAutorizacion(usuario)

    await usuario.type(within(dialogo).getByLabelText(/pin de marta/i), '937104')
    await usuario.click(within(dialogo).getByRole('button', { name: /autorizar y registrar/i }))

    expect(await within(dialogo).findByText('El PIN de autorización es incorrecto.')).toBeInTheDocument()
    expect(within(dialogo).getByLabelText(/pin de marta/i)).toHaveValue('')
    expect(screen.queryByText(/venta registrada/i)).not.toBeInTheDocument()
    expect(within(dialogo).getByRole('button', { name: /autorizar y registrar/i })).toBeDisabled()
  })

  it('PIN_BLOQUEADO también se muestra en el diálogo y no se reintenta solo', async () => {
    montarApi(apiFetchMock, [
      ...reglasDeAutorizacion([MARTA]),
      rechazo(429, 'PIN_BLOQUEADO', 'Demasiados intentos con el PIN de autorización. Probá más tarde.'),
    ])
    const usuario = userEvent.setup()
    renderPantalla()
    const dialogo = await ventaQuePideAutorizacion(usuario)

    await usuario.type(within(dialogo).getByLabelText(/pin de marta/i), PIN)
    await usuario.click(within(dialogo).getByRole('button', { name: /autorizar y registrar/i }))

    expect(await within(dialogo).findByText(/demasiados intentos/i)).toBeInTheDocument()
    expect(llamadas(apiFetchMock, 'POST', '/ventas')).toHaveLength(1)
  })

  it('cancelar el diálogo borra el PIN y no envía nada', async () => {
    montarApi(apiFetchMock, [...reglasDeAutorizacion([MARTA]), confirmarOk])
    const usuario = userEvent.setup()
    renderPantalla()
    const dialogo = await ventaQuePideAutorizacion(usuario)

    await usuario.type(within(dialogo).getByLabelText(/pin de marta/i), PIN)
    await usuario.click(within(dialogo).getByRole('button', { name: /^cancelar$/i }))
    expect(screen.queryByRole('dialog', { name: /autorización/i })).not.toBeInTheDocument()
    expect(llamadas(apiFetchMock, 'POST', '/ventas')).toHaveLength(0)

    await usuario.click(botonConfirmar())
    const otro = await screen.findByRole('dialog', { name: /autorización/i })
    expect(within(otro).getByLabelText(/pin de marta/i)).toHaveValue('')
  })

  it('sin ningún supervisor con PIN avisa y no deja autorizar', async () => {
    montarApi(apiFetchMock, [...reglasDeAutorizacion([]), confirmarOk])
    const usuario = userEvent.setup()
    renderPantalla()
    const dialogo = await ventaQuePideAutorizacion(usuario)

    expect(dialogo).toHaveTextContent(/no hay ning[uú]n supervisor con pin/i)
    expect(within(dialogo).getByRole('button', { name: /autorizar y registrar/i })).toBeDisabled()
  })

  it('el PIN no queda en ningún almacenamiento del navegador, ni antes ni después de enviar', async () => {
    const escrituras: string[] = []
    const setItem = vi.spyOn(Storage.prototype, 'setItem').mockImplementation((clave, valor) => {
      escrituras.push(`${clave}=${valor}`)
    })
    montarApi(apiFetchMock, [...reglasDeAutorizacion([MARTA]), confirmarOk])
    const usuario = userEvent.setup()
    renderPantalla()
    const dialogo = await ventaQuePideAutorizacion(usuario)
    await usuario.type(within(dialogo).getByLabelText(/pin de marta/i), PIN)
    expect(escrituras.some((e) => e.includes(PIN))).toBe(false)
    await usuario.click(within(dialogo).getByRole('button', { name: /autorizar y registrar/i }))
    await screen.findByText(/venta registrada/i)

    expect(escrituras.some((e) => e.includes(PIN))).toBe(false)
    expect(JSON.stringify({ ...window.localStorage })).not.toContain(PIN)
    expect(JSON.stringify({ ...window.sessionStorage })).not.toContain(PIN)
    // El Operation-Id es del contenido: el PIN no entra a lo que identifica la operación.
    const operationId = new Headers(llamadas(apiFetchMock, 'POST', '/ventas')[0]?.init.headers).get('Operation-Id') ?? ''
    expect(operationId).not.toContain(PIN)
    setItem.mockRestore()
  })
})
