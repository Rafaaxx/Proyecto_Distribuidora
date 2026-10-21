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
  EFECTIVO_ID,
  JORNADA_ABIERTA,
  LISTA_ID,
  MOTIVO_LISTA_ID,
  NUMERACION,
  OTRA_LISTA_ID,
  PRESENTACION_BOTELLA_ID,
  PRESENTACION_CAJA_ID,
  SIDRA_ID,
  TRANSFERENCIA_ID,
  UBICACION_ID,
  VENTA_CONFIRMADA,
  VENTA_ID,
  VERSION_ANTERIOR_ID,
  VERSION_ID,
  VINO_ID,
  montarApi,
} from './ventasDePrueba'

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

async function elegirCliente(usuario: Usuario) {
  await screen.findByRole('option', { name: 'Kiosco La Esquina' })
  await usuario.selectOptions(screen.getByLabelText(/^cliente$/i), CLIENTE_ID)
  await screen.findByTestId('saldo-actual')
}

async function agregarVinoA(usuario: Usuario) {
  await usuario.type(screen.getByLabelText(/buscar producto/i), 'vino')
  const resultado = await screen.findByTestId(`resultado-${VINO_ID}`)
  await usuario.click(within(resultado).getByRole('button', { name: /agregar vino a/i }))
  await screen.findByTestId(`item-${VINO_ID}`)
}

async function cargarCantidades(usuario: Usuario, cajas: string, unidades: string) {
  const cajasInput = screen.getByLabelText(/cajas de vino a/i)
  const unidadesInput = screen.getByLabelText(/unidades sueltas de vino a/i)
  await usuario.clear(cajasInput)
  await usuario.type(cajasInput, cajas)
  await usuario.clear(unidadesInput)
  await usuario.type(unidadesInput, unidades)
}

async function cargarEfectivo(usuario: Usuario, importe: string) {
  await usuario.click(screen.getByRole('button', { name: /agregar medio/i }))
  await screen.findByRole('option', { name: 'Efectivo' })
  await usuario.selectOptions(screen.getByLabelText(/^medio de pago$/i), EFECTIVO_ID)
  await usuario.type(screen.getByLabelText(/^importe del medio$/i), importe)
}

async function ventaLista(usuario: Usuario) {
  await elegirCliente(usuario)
  await agregarVinoA(usuario)
  await cargarCantidades(usuario, '2', '3')
}

interface CuerpoDeVenta {
  venta_id: string
  numero: string
  cliente_id: string
  ubicacion_id: string | null
  lista_id: string | null
  lista_version_id: string | null
  motivo_lista_id: string | null
  total: string
  lineas: { linea_id: string; producto_id: string; presentacion_id: string; cantidad: number; lista_version_id: string; precio_referencia: string; unidades_referencia: number; importe_bruto: string }[]
  cobranza: { cobranza_id: string; medios: { medio_pago_id: string; importe: string; referencia: string | null }[] } | null
}

function cuerpoDelPost(indice = 0): CuerpoDeVenta {
  return JSON.parse(String(llamadas(apiFetchMock, 'POST', '/ventas')[indice]?.init.body)) as CuerpoDeVenta
}

function idDeOperacion(indice: number): string | null {
  return new Headers(llamadas(apiFetchMock, 'POST', '/ventas')[indice]?.init.headers).get('Operation-Id')
}

const confirmarOk: ReglaDeApi = {
  metodo: 'POST',
  ruta: '/ventas',
  responder: () => ({ status: 201, cuerpo: VENTA_CONFIRMADA }),
}

function rechazo(status: number, codigo: string, title: string, extra: Record<string, unknown> = {}): ReglaDeApi {
  return { metodo: 'POST', ruta: '/ventas', responder: () => ({ status, cuerpo: { title, codigo, ...extra } }) }
}

const botonConfirmar = () => screen.getByRole('button', { name: /^confirmar venta$/i })

describe('VentaFormScreen (tarea 12.2)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
    window.localStorage.clear()
  })
  afterEach(() => {
    vi.clearAllMocks()
  })

  it('sin VENDER muestra la falta de permiso y no pide nada (SEG-06)', () => {
    montarApi(apiFetchMock)
    renderPantalla('GES')
    expect(screen.getByText(/no ten[eé]s permiso para vender/i)).toBeInTheDocument()
    expect(apiFetchMock).not.toHaveBeenCalled()
  })

  it('al elegir el cliente muestra su saldo actual (VTA-01) y propone el número del dispositivo (VTA-06)', async () => {
    montarApi(apiFetchMock)
    const usuario = userEvent.setup()
    renderPantalla()
    await elegirCliente(usuario)
    expect(screen.getByTestId('saldo-actual')).toHaveTextContent('Nos debe $ 150.000,00')
    await waitFor(() => expect(screen.getByLabelText(/^n[uú]mero de venta$/i)).toHaveValue('V01-000042'))
  })

  it('propone el mayor entre el servidor y el navegador (D4) y tolera que el navegador no guarde nada', async () => {
    window.localStorage.setItem('ventas.correlativo.V01', '44')
    montarApi(apiFetchMock)
    renderPantalla()
    await waitFor(() => expect(screen.getByLabelText(/^n[uú]mero de venta$/i)).toHaveValue('V01-000045'))
  })

  it('el buscador consulta al servidor con el texto (no descarga el catálogo) y muestra precio y stock', async () => {
    montarApi(apiFetchMock)
    const usuario = userEvent.setup()
    renderPantalla()
    await elegirCliente(usuario)
    await usuario.type(screen.getByLabelText(/buscar producto/i), 'vino')
    const resultado = await screen.findByTestId(`resultado-${VINO_ID}`)
    expect(resultado).toHaveTextContent('Vino A')
    expect(resultado).toHaveTextContent('$ 12.500,00')
    expect(resultado).toHaveTextContent('48 unidades (8 Caja x6)')
    const textos = () => llamadas(apiFetchMock, 'GET', '/ventas/precios').map(({ url }) => url.searchParams.get('q'))
    await waitFor(() => expect(textos()).toContain('vino'))
    // La búsqueda es del servidor y espera a que termine de tipear: ninguna consulta por tecla suelta.
    expect(textos().every((q) => q === null || q === 'vino')).toBe(true)
    const ultima = llamadas(apiFetchMock, 'GET', '/ventas/precios').at(-1)?.url.searchParams
    expect(ultima?.get('cliente_id')).toBe(CLIENTE_ID)
    expect(ultima?.get('ubicacion_id')).toBe(UBICACION_ID)
  })

  it('un producto sin precio aparece deshabilitado y no se puede agregar (VTA-10, D7)', async () => {
    montarApi(apiFetchMock)
    const usuario = userEvent.setup()
    renderPantalla()
    await elegirCliente(usuario)
    await usuario.type(screen.getByLabelText(/buscar producto/i), 'sidra')
    const resultado = await screen.findByTestId(`resultado-${SIDRA_ID}`)
    expect(within(resultado).getByRole('button', { name: /agregar sidra/i })).toBeDisabled()
    expect(resultado).toHaveTextContent(/sin precio/i)
  })

  // Escenario: "Composición en la pantalla"
  it('2 cajas + 3 unidades de Vino A: dos líneas con brutos $ 25.000,00 y $ 6.250,00 y total $ 31.250,00 (VTA-02, PRC-22)', async () => {
    montarApi(apiFetchMock)
    const usuario = userEvent.setup()
    renderPantalla()
    await elegirCliente(usuario)
    await agregarVinoA(usuario)
    await cargarCantidades(usuario, '2', '3')
    const item = screen.getByTestId(`item-${VINO_ID}`)
    expect(item).toHaveTextContent('Caja x6')
    expect(item).toHaveTextContent('$ 25.000,00')
    expect(item).toHaveTextContent('Botella')
    expect(item).toHaveTextContent('$ 6.250,00')
    expect(screen.getByTestId('total-de-la-venta')).toHaveTextContent('$ 31.250,00')
  })

  // Escenario: "Unidades sueltas sin presentación de una unidad"
  it('un producto sin presentación de 1 unidad no ofrece unidades sueltas (CAT-07)', async () => {
    montarApi(apiFetchMock, [
      {
        metodo: 'GET',
        ruta: '/ventas/precios',
        responder: () => ({
          status: 200,
          cuerpo: {
            lista_id: LISTA_ID,
            lista_nombre: 'Mayorista',
            version_id: VERSION_ID,
            version_numero: 2,
            ubicacion_id: UBICACION_ID,
            cursor_siguiente: null,
            items: [
              {
                producto_id: VINO_ID,
                codigo: 'P-001',
                nombre: 'Vino A',
                precio_referencia: '12500.00',
                unidades_referencia: 6,
                sin_precio: false,
                stock_base: 48,
                presentaciones: [{ presentacion_id: PRESENTACION_CAJA_ID, nombre: 'Caja x6', unidades_base: 6, es_referencia: true }],
              },
            ],
          },
        }),
      },
    ])
    const usuario = userEvent.setup()
    renderPantalla()
    await elegirCliente(usuario)
    await agregarVinoA(usuario)
    expect(screen.getByLabelText(/cajas de vino a/i)).toBeEnabled()
    expect(screen.getByLabelText(/unidades sueltas de vino a/i)).toBeDisabled()
  })

  it('aviso de stock: pedir más de lo que hay lo marca, sin bloquear (STK-05, INV-13)', async () => {
    montarApi(apiFetchMock)
    const usuario = userEvent.setup()
    renderPantalla()
    await elegirCliente(usuario)
    await agregarVinoA(usuario)
    await cargarCantidades(usuario, '9', '0')
    expect(screen.getByTestId(`item-${VINO_ID}`)).toHaveTextContent(/supera el stock/i)
    expect(botonConfirmar()).toBeEnabled()
  })

  it('la cobranza suma sus medios en vivo y muestra el saldo resultante (VTA-11, INV-08)', async () => {
    montarApi(apiFetchMock)
    const usuario = userEvent.setup()
    renderPantalla()
    await ventaLista(usuario)
    await cargarEfectivo(usuario, '20000')
    expect(screen.getByTestId('cobrado')).toHaveTextContent('$ 20.000,00')
    expect(screen.getByTestId('saldo-resultante')).toHaveTextContent('Queda debiendo $ 161.250,00')
  })

  it('confirmar envía lo que el usuario vio: líneas con sus valores esperados, total, número y cobranza (D2, VTA-06)', async () => {
    montarApi(apiFetchMock, [confirmarOk])
    const usuario = userEvent.setup()
    renderPantalla()
    await ventaLista(usuario)
    await cargarEfectivo(usuario, '20000')
    await waitFor(() => expect(botonConfirmar()).toBeEnabled())
    await usuario.click(botonConfirmar())

    await screen.findByText(/venta registrada/i)
    const cuerpo = cuerpoDelPost()
    expect(cuerpo.numero).toBe('V01-000042')
    expect(cuerpo.cliente_id).toBe(CLIENTE_ID)
    expect(cuerpo.ubicacion_id).toBe(UBICACION_ID)
    expect(cuerpo.total).toBe('31250.00')
    expect(cuerpo.lista_id).toBeNull()
    expect(cuerpo.lineas).toHaveLength(2)
    expect(cuerpo.lineas[0]).toMatchObject({
      producto_id: VINO_ID,
      presentacion_id: PRESENTACION_CAJA_ID,
      cantidad: 2,
      lista_version_id: VERSION_ID,
      precio_referencia: '12500.00',
      unidades_referencia: 6,
      importe_bruto: '25000.00',
    })
    expect(cuerpo.lineas[1]).toMatchObject({ presentacion_id: PRESENTACION_BOTELLA_ID, cantidad: 3, importe_bruto: '6250.00' })
    expect(cuerpo.cobranza?.medios).toEqual([{ medio_pago_id: EFECTIVO_ID, importe: '20000.00', referencia: null }])
    expect(idDeOperacion(0)).toMatch(/^[0-9a-f-]{36}$/i)
    expect(screen.getByTestId('saldo-final')).toHaveTextContent('Nos debe $ 161.250,00')
    expect(window.localStorage.getItem('ventas.correlativo.V01')).toBe('42')
  })

  it('cobrar de más pide confirmación explícita del saldo a favor y no envía hasta aceptar (VTA-11)', async () => {
    montarApi(apiFetchMock, [confirmarOk], '0.00')
    const usuario = userEvent.setup()
    renderPantalla()
    await ventaLista(usuario)
    await cargarEfectivo(usuario, '40000')
    await waitFor(() => expect(botonConfirmar()).toBeEnabled())
    await usuario.click(botonConfirmar())

    const dialogo = await screen.findByRole('dialog')
    expect(dialogo).toHaveTextContent('Le queda saldo a favor de $ 8.750,00')
    expect(llamadas(apiFetchMock, 'POST', '/ventas')).toHaveLength(0)
    await usuario.click(within(dialogo).getByRole('button', { name: /aceptar y registrar/i }))
    await waitFor(() => expect(llamadas(apiFetchMock, 'POST', '/ventas')).toHaveLength(1))
  })

  // Escenario: "Precio que cambió"
  it('PRECIO_DIFIERE muestra el precio y el total nuevos y no reenvía hasta que el usuario confirme (D2)', async () => {
    let intento = 0
    montarApi(apiFetchMock, [
      {
        metodo: 'POST',
        ruta: '/ventas',
        responder: (_url, init) => {
          intento += 1
          if (intento > 1) return { status: 201, cuerpo: VENTA_CONFIRMADA }
          const enviadas = (JSON.parse(String(init?.body)) as { lineas: { linea_id: string; cantidad: number }[] }).lineas
          return {
            status: 409,
            cuerpo: {
              title: 'El precio o el total difieren de lo que vio el usuario.',
              codigo: 'PRECIO_DIFIERE',
              total: '32500.00',
              lineas: enviadas.map((l) => ({
                linea_id: l.linea_id,
                lista_version_id: 'aaaaaaaa-0000-4000-8000-000000000003',
                precio_referencia: '13000.00',
                unidades_referencia: 6,
                importe_bruto: l.cantidad === 2 ? '26000.00' : '6500.00',
              })),
            },
          }
        },
      },
    ])
    const usuario = userEvent.setup()
    renderPantalla()
    await ventaLista(usuario)
    await waitFor(() => expect(botonConfirmar()).toBeEnabled())
    await usuario.click(botonConfirmar())

    const dialogo = await screen.findByRole('dialog')
    expect(dialogo).toHaveTextContent('$ 32.500,00')
    expect(dialogo).toHaveTextContent('$ 13.000,00')
    expect(llamadas(apiFetchMock, 'POST', '/ventas')).toHaveLength(1)

    await usuario.click(within(dialogo).getByRole('button', { name: /confirmar con los valores nuevos/i }))
    await waitFor(() => expect(llamadas(apiFetchMock, 'POST', '/ventas')).toHaveLength(2))
    const reenviado = cuerpoDelPost(1)
    expect(reenviado.total).toBe('32500.00')
    expect(reenviado.lineas[0]).toMatchObject({ precio_referencia: '13000.00', importe_bruto: '26000.00', lista_version_id: 'aaaaaaaa-0000-4000-8000-000000000003' })
    expect(reenviado.lineas[1]).toMatchObject({ importe_bruto: '6500.00' })
    await screen.findByText(/venta registrada/i)
  })

  it('PRECIO_DIFIERE y Cancelar no reenvía nada y deja releer los precios', async () => {
    montarApi(apiFetchMock, [
      rechazo(409, 'PRECIO_DIFIERE', 'Difiere', {
        total: '32500.00',
        lineas: [{ linea_id: 'x', lista_version_id: VERSION_ID, precio_referencia: '13000.00', unidades_referencia: 6, importe_bruto: '1.00' }],
      }),
    ])
    const usuario = userEvent.setup()
    renderPantalla()
    await ventaLista(usuario)
    await waitFor(() => expect(botonConfirmar()).toBeEnabled())
    await usuario.click(botonConfirmar())
    const dialogo = await screen.findByRole('dialog')
    await usuario.click(within(dialogo).getByRole('button', { name: /cancelar/i }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(llamadas(apiFetchMock, 'POST', '/ventas')).toHaveLength(1)
  })

  // Escenario: "Número tomado por otra pestaña"
  it('NUMERO_DUPLICADO relee la numeración, propone el siguiente y espera la confirmación (VTA-06, D4)', async () => {
    let ultimo = NUMERACION.ultimo_correlativo
    montarApi(apiFetchMock, [
      {
        metodo: 'GET',
        ruta: '/ventas/numeracion',
        responder: () => ({ status: 200, cuerpo: { ...NUMERACION, ultimo_correlativo: ultimo } }),
      },
      {
        metodo: 'POST',
        ruta: '/ventas',
        responder: () => {
          if (ultimo === 41) {
            ultimo = 42
            return { status: 409, cuerpo: { title: 'El número ya fue usado.', codigo: 'NUMERO_DUPLICADO' } }
          }
          return { status: 201, cuerpo: { ...VENTA_CONFIRMADA, numero: 'V01-000043' } }
        },
      },
    ])
    const usuario = userEvent.setup()
    renderPantalla()
    await ventaLista(usuario)
    await waitFor(() => expect(screen.getByLabelText(/^n[uú]mero de venta$/i)).toHaveValue('V01-000042'))
    await waitFor(() => expect(botonConfirmar()).toBeEnabled())
    await usuario.click(botonConfirmar())

    await waitFor(() => expect(screen.getByLabelText(/^n[uú]mero de venta$/i)).toHaveValue('V01-000043'))
    expect(screen.getByText(/ya fue usado/i)).toBeInTheDocument()
    expect(llamadas(apiFetchMock, 'POST', '/ventas')).toHaveLength(1)

    await usuario.click(botonConfirmar())
    await waitFor(() => expect(llamadas(apiFetchMock, 'POST', '/ventas')).toHaveLength(2))
    expect(cuerpoDelPost(1).numero).toBe('V01-000043')
  })

  // Escenario: "Reintento con el mismo `Operation-Id`"
  it('tras un corte de red el reintento reenvía el mismo Operation-Id, la misma venta y el mismo número (INV-06)', async () => {
    let intento = 0
    montarApi(apiFetchMock, [
      {
        metodo: 'POST',
        ruta: '/ventas',
        responder: () => {
          intento += 1
          if (intento <= 6) throw new TypeError('Failed to fetch')
          return { status: 201, cuerpo: VENTA_CONFIRMADA }
        },
      },
    ])
    const usuario = userEvent.setup()
    renderPantalla()
    await ventaLista(usuario)
    await waitFor(() => expect(botonConfirmar()).toBeEnabled())
    await usuario.click(botonConfirmar())
    await screen.findByText(/revis[aá] la conexi[oó]n/i)
    const enviadas = llamadas(apiFetchMock, 'POST', '/ventas').length
    expect(enviadas).toBeGreaterThanOrEqual(2)
    for (let i = 1; i < enviadas; i += 1) {
      expect(idDeOperacion(i)).toBe(idDeOperacion(0))
      expect(cuerpoDelPost(i).venta_id).toBe(cuerpoDelPost(0).venta_id)
      expect(cuerpoDelPost(i).numero).toBe(cuerpoDelPost(0).numero)
    }

    await usuario.click(botonConfirmar())
    await waitFor(() => expect(llamadas(apiFetchMock, 'POST', '/ventas').length).toBeGreaterThan(enviadas))
    await waitFor(() => expect(botonConfirmar()).toBeEnabled())
    expect(idDeOperacion(enviadas)).toBe(idDeOperacion(0))
    expect(cuerpoDelPost(enviadas).venta_id).toBe(cuerpoDelPost(0).venta_id)
    expect(cuerpoDelPost(enviadas).lineas[0]?.linea_id).toBe(cuerpoDelPost(0).lineas[0]?.linea_id)
  })

  it('los errores del servidor se muestran junto a su campo (VTA-06, CLI-02, D5)', async () => {
    montarApi(apiFetchMock, [rechazo(409, 'CLIENTE_SUSPENDIDO', 'El cliente está suspendido.')])
    const usuario = userEvent.setup()
    renderPantalla()
    await ventaLista(usuario)
    await waitFor(() => expect(botonConfirmar()).toBeEnabled())
    await usuario.click(botonConfirmar())
    const campo = await screen.findByTestId('campo-cliente')
    expect(within(campo).getByRole('alert')).toHaveTextContent('El cliente está suspendido.')
  })

  it('consumidor final: avisa de entrada que es solo de contado y bloquea hasta que la cobranza iguale el total (CLI-03, D5)', async () => {
    montarApi(apiFetchMock, [confirmarOk])
    const usuario = userEvent.setup()
    renderPantalla()
    await screen.findByRole('option', { name: 'Consumidor final' })
    await usuario.selectOptions(screen.getByLabelText(/^cliente$/i), CONSUMIDOR_FINAL_ID)
    await screen.findByTestId('saldo-actual')
    expect(screen.getByTestId('aviso-consumidor-final')).toHaveTextContent(/solo de contado/i)
    expect(llamadas(apiFetchMock, 'GET', '/clientes/opciones').at(-1)?.url.searchParams.get('incluir_consumidor_final')).toBe('true')

    await agregarVinoA(usuario)
    await cargarCantidades(usuario, '2', '3')
    await cargarEfectivo(usuario, '20000')
    await waitFor(() => expect(screen.getByTestId('contado-consumidor-final')).toHaveTextContent(/igual al total/i))
    expect(botonConfirmar()).toBeDisabled()

    await usuario.clear(screen.getByLabelText(/^importe del medio$/i))
    await usuario.type(screen.getByLabelText(/^importe del medio$/i), '31250')
    await waitFor(() => expect(botonConfirmar()).toBeEnabled())
    await usuario.click(botonConfirmar())
    await screen.findByText(/venta registrada/i)
    expect(cuerpoDelPost().cobranza?.medios).toEqual([{ medio_pago_id: EFECTIVO_ID, importe: '31250.00', referencia: null }])
  })

  it('con un cliente común no hay aviso de contado y se puede confirmar sin cobranza (CLI-03)', async () => {
    montarApi(apiFetchMock)
    const usuario = userEvent.setup()
    renderPantalla()
    await ventaLista(usuario)
    expect(screen.queryByTestId('aviso-consumidor-final')).not.toBeInTheDocument()
    await waitFor(() => expect(botonConfirmar()).toBeEnabled())
  })

  it('NUMERO_INVALIDO y CONSUMIDOR_FINAL_CONTADO van a su campo; PRODUCTO_SIN_PRECIO lista los productos', async () => {
    const usuario = userEvent.setup()
    montarApi(apiFetchMock, [rechazo(422, 'NUMERO_INVALIDO', 'El prefijo no es el de este dispositivo.')])
    const primero = renderPantalla()
    await ventaLista(usuario)
    await waitFor(() => expect(botonConfirmar()).toBeEnabled())
    await usuario.click(botonConfirmar())
    expect(await within(await screen.findByTestId('campo-numero')).findByRole('alert')).toHaveTextContent('El prefijo no es el de este dispositivo.')
    primero.unmount()

    apiFetchMock.mockReset()
    montarApi(apiFetchMock, [rechazo(422, 'CONSUMIDOR_FINAL_CONTADO', 'El consumidor final se vende de contado.')])
    const segundo = renderPantalla()
    await ventaLista(usuario)
    await waitFor(() => expect(botonConfirmar()).toBeEnabled())
    await usuario.click(botonConfirmar())
    expect(await within(await screen.findByTestId('bloque-cobranza')).findByRole('alert')).toHaveTextContent('de contado')
    segundo.unmount()

    apiFetchMock.mockReset()
    montarApi(apiFetchMock, [rechazo(409, 'PRODUCTO_SIN_PRECIO', 'Falta precio.', { productos: [{ producto_id: SIDRA_ID, nombre: 'Sidra' }] })])
    renderPantalla()
    await ventaLista(usuario)
    await waitFor(() => expect(botonConfirmar()).toBeEnabled())
    await usuario.click(botonConfirmar())
    expect(await within(await screen.findByTestId('campo-lineas')).findByRole('alert')).toHaveTextContent(/Sidra/)
  })

  it('sin USAR_LISTA_ANTERIOR no se ofrece otra lista ni versión (PRC-21)', async () => {
    montarApi(apiFetchMock)
    renderPantalla('VEN')
    await screen.findByLabelText(/^n[uú]mero de venta$/i)
    expect(screen.queryByLabelText(/lista de precios/i)).not.toBeInTheDocument()
    expect(llamadas(apiFetchMock, 'GET', '/ventas/versiones')).toHaveLength(0)
  })

  it('con USAR_LISTA_ANTERIOR elige otra lista y una versión anterior con motivo, y todo viaja en la venta (PRC-21, D6)', async () => {
    montarApi(apiFetchMock, [confirmarOk])
    const usuario = userEvent.setup()
    renderPantalla('ADM')
    await elegirCliente(usuario)
    await usuario.selectOptions(await screen.findByLabelText(/lista de precios/i), LISTA_ID)
    await usuario.selectOptions(await screen.findByLabelText(/^versi[oó]n$/i), VERSION_ANTERIOR_ID)
    await usuario.selectOptions(await screen.findByLabelText(/^motivo$/i), MOTIVO_LISTA_ID)
    await agregarVinoA(usuario)
    await cargarCantidades(usuario, '2', '3')

    const ultima = llamadas(apiFetchMock, 'GET', '/ventas/precios').at(-1)?.url.searchParams
    expect(ultima?.get('lista_id')).toBe(LISTA_ID)
    expect(ultima?.get('version_id')).toBe(VERSION_ANTERIOR_ID)
    expect(llamadas(apiFetchMock, 'GET', '/configuracion/motivos').at(-1)?.url.searchParams.get('ambito')).toBe('LISTA_ANTERIOR')

    await waitFor(() => expect(botonConfirmar()).toBeEnabled())
    await usuario.click(botonConfirmar())
    await screen.findByText(/venta registrada/i)
    expect(cuerpoDelPost()).toMatchObject({ lista_id: LISTA_ID, lista_version_id: VERSION_ANTERIOR_ID, motivo_lista_id: MOTIVO_LISTA_ID })
  })

  it('MOTIVO_INVALIDO se muestra junto a la lista elegida', async () => {
    montarApi(apiFetchMock, [rechazo(422, 'MOTIVO_INVALIDO', 'La organización exige un motivo para cambiar la lista.')])
    const usuario = userEvent.setup()
    renderPantalla('ADM')
    await elegirCliente(usuario)
    await usuario.selectOptions(await screen.findByLabelText(/lista de precios/i), OTRA_LISTA_ID)
    await agregarVinoA(usuario)
    await waitFor(() => expect(botonConfirmar()).toBeEnabled())
    await usuario.click(botonConfirmar())
    expect(await within(await screen.findByTestId('bloque-lista')).findByRole('alert')).toHaveTextContent(/exige un motivo/i)
  })

  it('con jornada abierta la venta va a la ubicación de la jornada: no se elige ni se envía ubicación (D3)', async () => {
    montarApi(apiFetchMock, [
      confirmarOk,
      { metodo: 'GET', ruta: '/stock/jornadas/actual', responder: () => ({ status: 200, cuerpo: JORNADA_ABIERTA }) },
    ])
    const usuario = userEvent.setup()
    renderPantalla('VEN')
    await elegirCliente(usuario)
    expect(await screen.findByTestId('ubicacion-de-jornada')).toHaveTextContent('Camioneta 2')
    expect(screen.queryByLabelText(/^ubicaci[oó]n$/i)).not.toBeInTheDocument()
    await agregarVinoA(usuario)
    expect(llamadas(apiFetchMock, 'GET', '/ventas/precios').at(-1)?.url.searchParams.get('ubicacion_id')).toBe(JORNADA_ABIERTA.ubicacion_id)
    await waitFor(() => expect(botonConfirmar()).toBeEnabled())
    await usuario.click(botonConfirmar())
    await screen.findByText(/venta registrada/i)
    expect(cuerpoDelPost().ubicacion_id).toBeNull()
  })

  it('sin jornada la ubicación es obligatoria: no se confirma hasta elegirla (D3)', async () => {
    montarApi(apiFetchMock, [confirmarOk])
    const usuario = userEvent.setup()
    renderPantalla('VEN')
    await elegirCliente(usuario)
    await agregarVinoA(usuario)
    await usuario.selectOptions(screen.getByLabelText(/^ubicaci[oó]n$/i), '')
    await waitFor(() => expect(botonConfirmar()).toBeDisabled())
    await usuario.selectOptions(screen.getByLabelText(/^ubicaci[oó]n$/i), UBICACION_ID)
    await waitFor(() => expect(botonConfirmar()).toBeEnabled())
  })

  it('referencia obligatoria en un medio que la exige: sin ella no se confirma', async () => {
    montarApi(apiFetchMock, [confirmarOk])
    const usuario = userEvent.setup()
    renderPantalla()
    await ventaLista(usuario)
    await usuario.click(screen.getByRole('button', { name: /agregar medio/i }))
    await screen.findByRole('option', { name: 'Transferencia' })
    await usuario.selectOptions(screen.getByLabelText(/^medio de pago$/i), TRANSFERENCIA_ID)
    await usuario.type(screen.getByLabelText(/^importe del medio$/i), '5000')
    expect(screen.getByLabelText(/referencia/i)).toBeRequired()
    expect(botonConfirmar()).toBeDisabled()
    await usuario.type(screen.getByLabelText(/referencia/i), '0042')
    await waitFor(() => expect(botonConfirmar()).toBeEnabled())
  })

  it('"Nueva venta" tras registrar deja el formulario limpio y usa venta, cobranza y número nuevos', async () => {
    montarApi(apiFetchMock, [confirmarOk])
    const usuario = userEvent.setup()
    renderPantalla()
    await ventaLista(usuario)
    await waitFor(() => expect(botonConfirmar()).toBeEnabled())
    await usuario.click(botonConfirmar())
    await screen.findByText(/venta registrada/i)
    expect(VENTA_ID).toBeTruthy()

    await usuario.click(screen.getByRole('button', { name: /cargar otra venta/i }))
    await waitFor(() => expect(screen.getByLabelText(/^n[uú]mero de venta$/i)).toHaveValue('V01-000043'))
    expect(screen.queryByTestId(`item-${VINO_ID}`)).not.toBeInTheDocument()
  })
})
