import 'fake-indexeddb/auto'

import { act, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { bootstrapParaVender } from '../../utils/datosParaVender'
import { sembrarVenta } from '../../utils/sembrarVenta'
import { sincronizadorDePrueba } from '../../utils/sincronizadorDePrueba'
import { montarEnRuta } from '../../utils/rutaDePrueba'

import { InicioScreen } from '../../../../src/areas/ruta/InicioScreen'
import { RutaLayout } from '../../../../src/areas/ruta/RutaLayout'
import { baseLocal } from '../../../../src/lib/dispositivo/db'
import { formatearFechaHora } from '../../../../src/lib/fecha'
import { aplicarBootstrap } from '../../../../src/sync/aplicarBootstrap'
import { iniciarDisparadores, type Disparadores } from '../../../../src/sync/disparadores'
import { CLAVE_ULTIMA_SINCRONIZACION } from '../../../../src/sync/sincronizar'
import { ID } from '../../utils/bootstrapDePrueba'

/**
 * Change 22b, tarea 10.1 (spec `ruta/area-de-ruta`, «El estado de la sincronización se ve en todo
 * momento» y «El inicio muestra las ventas sin enviar»; `design.md` D8; cita `02` §13.3, SYN-09).
 */
function conectado(valor: boolean) {
  vi.spyOn(window.navigator, 'onLine', 'get').mockReturnValue(valor)
}

function montarConLayout(ruta: string) {
  return montarEnRuta(
    <Routes>
      <Route path="/ruta/*" element={<RutaLayout />} />
    </Routes>,
    { ruta },
  )
}

async function sembrar() {
  await Promise.all(baseLocal.tables.map((t) => t.clear()))
  await aplicarBootstrap(bootstrapParaVender())
}

describe('cabecera de /ruta con el estado de la sincronización (tarea 10.1)', () => {
  beforeEach(sembrar)
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('en cualquier pantalla muestra la conexión y «N sin enviar»', async () => {
    conectado(false)
    await sembrarVenta('a', { cajas: 1, unidades: 0 })
    montarConLayout('/ruta/clientes')

    const cabecera = await screen.findByRole('banner')
    expect(await within(cabecera).findByText('1 sin enviar')).toBeInTheDocument()
    expect(within(cabecera).getByText('Sin conexión')).toBeInTheDocument()
  })

  it('sin ventas pendientes dice «Todo enviado» y con conexión «Con conexión»', async () => {
    conectado(true)
    montarConLayout('/ruta/productos')

    const cabecera = await screen.findByRole('banner')
    expect(await within(cabecera).findByText('Todo enviado')).toBeInTheDocument()
    expect(within(cabecera).getByText('Con conexión')).toBeInTheDocument()
  })

  it('con una rechazada muestra el aviso y, al tocarlo, abre «Sincronización»', async () => {
    conectado(true)
    await sembrarVenta('a', { cajas: 1, unidades: 0 })
    await baseLocal.ventas.update('venta-a', { estado_envio: 'RECHAZADA' })
    await baseLocal.cola.update(1, { estado: 'RECHAZADO', error_codigo: 'JORNADA_INEXISTENTE' })
    montarConLayout('/ruta/clientes')

    const cabecera = await screen.findByRole('banner')
    expect(await within(cabecera).findByText('1 rechazada')).toBeInTheDocument()
    await userEvent.setup().click(within(cabecera).getByRole('link', { name: /rechazada/ }))
    expect(await screen.findByRole('heading', { name: 'Sincronización' })).toBeInTheDocument()
  })

  it('se actualiza solo cuando otra pestaña escribe en la base (liveQuery)', async () => {
    conectado(true)
    await sembrarVenta('a', { cajas: 1, unidades: 0 })
    montarConLayout('/ruta/clientes')
    const cabecera = await screen.findByRole('banner')
    expect(await within(cabecera).findByText('1 sin enviar')).toBeInTheDocument()

    await baseLocal.cola.update(1, { estado: 'ACEPTADO' })

    expect(await within(cabecera).findByText('Todo enviado')).toBeInTheDocument()
  })
})

describe('inicio con la última sincronización y «Sincronizar» (tarea 10.1)', () => {
  let activos: Disparadores | null = null
  beforeEach(sembrar)
  afterEach(() => {
    activos?.detener()
    activos = null
    vi.restoreAllMocks()
  })

  function arrancar(responder?: Parameters<ReturnType<typeof sincronizadorDePrueba>['responderCon']>[0]) {
    const prueba = sincronizadorDePrueba()
    if (responder) prueba.responderCon(responder)
    activos = iniciarDisparadores({ usuarioId: ID(1), dispositivoId: 'd1', sincronizador: prueba.sincronizador })
    return prueba
  }

  it('muestra «Última sincronización: {hora}» y el conteo de ventas sin enviar', async () => {
    conectado(true)
    await sembrarVenta('a', { cajas: 1, unidades: 0 })
    await baseLocal.meta.put({ clave: CLAVE_ULTIMA_SINCRONIZACION, valor: '2026-11-01T12:34:00.000Z' })
    montarEnRuta(<InicioScreen />)

    expect(await screen.findByText('1 venta sin enviar')).toBeInTheDocument()
    expect(screen.getByText(`Última sincronización: ${formatearFechaHora('2026-11-01T12:34:00.000Z')}`)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Sincronizar' })).toBeEnabled()
  })

  it('«Sincronizar» pasa por «Enviando…» deshabilitado y vuelve a quedar disponible', async () => {
    conectado(true)
    const prueba = arrancar()
    let terminar: () => void = () => undefined
    prueba.responderCon(
      () =>
        new Promise((resolver) => {
          terminar = () => resolver({ tipo: 'completa', enviadas: 1 })
        }),
    )
    montarEnRuta(<InicioScreen />)
    const u = userEvent.setup()

    await u.click(await screen.findByRole('button', { name: /^(Sincronizar|Enviando)/ }))
    expect(await screen.findByRole('button', { name: 'Enviando…' })).toBeDisabled()
    expect(prueba.origenes).toContain('manual')

    await act(async () => terminar())
    expect(await screen.findByRole('button', { name: 'Sincronizar' })).toBeEnabled()
  })

  it('si otra pestaña está sincronizando lo dice', async () => {
    conectado(true)
    arrancar(async () => ({ tipo: 'otra_pestana' }))
    montarEnRuta(<InicioScreen />)

    expect(await screen.findByText('Sincronizando en otra pestaña')).toBeInTheDocument()
  })

  it('sin señal informa que requiere conexión y no cambia la hora ni lo pendiente', async () => {
    conectado(false)
    arrancar()
    await sembrarVenta('a', { cajas: 1, unidades: 0 })
    await baseLocal.meta.put({ clave: CLAVE_ULTIMA_SINCRONIZACION, valor: '2026-11-01T12:34:00.000Z' })
    montarEnRuta(<InicioScreen />)
    const u = userEvent.setup()

    await u.click(await screen.findByRole('button', { name: 'Sincronizar' }))

    expect(await screen.findByText('Sincronizar requiere conexión.')).toBeInTheDocument()
    expect(screen.getByText('1 venta sin enviar')).toBeInTheDocument()
    expect(screen.getByText(`Última sincronización: ${formatearFechaHora('2026-11-01T12:34:00.000Z')}`)).toBeInTheDocument()
    await waitFor(() => expect(screen.getByRole('button', { name: 'Sincronizar' })).toBeEnabled())
  })
})
