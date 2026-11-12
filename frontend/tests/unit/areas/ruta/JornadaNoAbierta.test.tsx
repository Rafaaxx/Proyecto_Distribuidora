import 'fake-indexeddb/auto'

import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { ClienteFichaScreen } from '../../../../src/areas/ruta/clientes/ClienteFichaScreen'
import { InicioScreen } from '../../../../src/areas/ruta/InicioScreen'
import { ProveedorGuardaDelCarrito } from '../../../../src/areas/ruta/ventas/guardaDelCarrito'
import { VenderScreen } from '../../../../src/areas/ruta/ventas/VenderScreen'
import { baseLocal } from '../../../../src/lib/dispositivo/db'
import { aplicarBootstrap } from '../../../../src/sync/aplicarBootstrap'
import {
  CLAVE_JORNADA_NO_ABIERTA,
  marcarJornadaNoAbierta,
  type EstadoDeJornadaNoAbierta,
} from '../../../../src/sync/estadoDeJornada'
import { ID } from '../../utils/bootstrapDePrueba'
import { bootstrapParaVender } from '../../utils/datosParaVender'
import { montarEnRuta } from '../../utils/rutaDePrueba'

/**
 * Change 22d, tarea 13.1 (spec `ruta/area-de-ruta`, «Vender y anular se cortan cuando la jornada ya
 * no está abierta», sus seis escenarios; `design.md` D9; cita RUT-05, RUT-09, VTA-24, SYN-05,
 * INV-01): lo que el teléfono guardó sobre su jornada corta «Vender» en el inicio, la ficha y
 * «Confirmar venta»; «Anular venta» se prueba en `AnularVentaScreen.test.tsx`. La jornada de la
 * sesión de prueba es `ID(2)`.
 */
const AHORA = new Date('2026-11-03T12:00:00.000Z')
const J1 = ID(2)
const LO_YA_VENDIDO = 'Lo que ya vendiste y cobraste se sigue enviando.'

function conectado(valor: boolean) {
  vi.spyOn(window.navigator, 'onLine', 'get').mockReturnValue(valor)
}

async function guardar(estado: EstadoDeJornadaNoAbierta) {
  await marcarJornadaNoAbierta(J1, estado, AHORA)
}

function montarFicha() {
  return montarEnRuta(
    <Routes>
      <Route path="/ruta/clientes/:id" element={<ClienteFichaScreen />} />
    </Routes>,
    { ruta: `/ruta/clientes/${ID(101)}` },
  )
}

describe('Inicio con la jornada no abierta (tarea 13.1, D9)', () => {
  beforeEach(async () => {
    conectado(true)
    await Promise.all(baseLocal.tables.map((t) => t.clear()))
    await aplicarBootstrap(bootstrapParaVender((b) => b.sesion.permisos.push('ABRIR_JORNADA')))
  })
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it.each([
    ['LIBERADA', 'Tu jornada fue liberada.'],
    ['EN_RENDICION', 'Tu jornada está en rendición.'],
    ['CERRADA', 'Tu jornada fue cerrada.'],
    ['DESCONOCIDO', 'Tu jornada ya no está abierta.'],
  ] as const)('con la jornada %s dice «%s», que lo vendido se sigue enviando y deshabilita «Vender» (RUT-09)', async (estado, aviso) => {
    await guardar(estado)
    montarEnRuta(<InicioScreen />)

    expect(await screen.findByText(aviso)).toBeInTheDocument()
    expect(screen.getByText(LO_YA_VENDIDO)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Vender' })).toBeDisabled()
    expect(screen.queryByRole('link', { name: 'Vender' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /ayuda: jornada no abierta/i })).toBeInTheDocument()
  })

  it('Stock, Clientes, Productos, Ventas de hoy y Sincronizar siguen disponibles', async () => {
    await guardar('LIBERADA')
    montarEnRuta(<InicioScreen />)

    await screen.findByText('Tu jornada fue liberada.')
    for (const nombre of ['Stock', 'Clientes', 'Productos', 'Ventas de hoy']) {
      expect(screen.getByRole('link', { name: nombre })).toBeInTheDocument()
    }
    expect(screen.getByRole('button', { name: 'Sincronizar' })).toBeEnabled()
  })

  it('con señal ofrece abrir una jornada nueva; sin señal queda deshabilitado', async () => {
    await guardar('LIBERADA')
    const { unmount } = montarEnRuta(<InicioScreen />)
    expect(await screen.findByRole('link', { name: 'Abrir jornada' })).toHaveAttribute('href', '/ruta/jornada/abrir')
    unmount()

    conectado(false)
    montarEnRuta(<InicioScreen />)
    expect(await screen.findByRole('button', { name: 'Abrir jornada' })).toBeDisabled()
  })

  it('sigue igual sin señal y después de recargar la aplicación (RUT-09)', async () => {
    await guardar('LIBERADA')
    const { unmount } = montarEnRuta(<InicioScreen />)
    await screen.findByText('Tu jornada fue liberada.')
    unmount()

    conectado(false)
    montarEnRuta(<InicioScreen />)

    expect(await screen.findByText('Tu jornada fue liberada.')).toBeInTheDocument()
    expect(screen.getByText(LO_YA_VENDIDO)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Vender' })).toBeDisabled()
  })

  it('sin dato guardado «Vender» sigue disponible y no hay aviso (SYN-05)', async () => {
    montarEnRuta(<InicioScreen />)

    expect(await screen.findByRole('link', { name: 'Vender' })).toBeInTheDocument()
    expect(screen.queryByText(LO_YA_VENDIDO)).not.toBeInTheDocument()
  })

  it('un dato guardado de otra jornada no corta nada', async () => {
    await baseLocal.meta.put({
      clave: CLAVE_JORNADA_NO_ABIERTA,
      valor: JSON.stringify({ jornada_id: 'otra-jornada', estado: 'LIBERADA', en: AHORA.toISOString() }),
    })
    montarEnRuta(<InicioScreen />)

    expect(await screen.findByRole('link', { name: 'Vender' })).toBeInTheDocument()
    expect(screen.queryByText(LO_YA_VENDIDO)).not.toBeInTheDocument()
  })

  it('el aviso aparece solo cuando el teléfono se entera, sin recargar', async () => {
    montarEnRuta(<InicioScreen />)
    await screen.findByRole('link', { name: 'Vender' })

    await guardar('LIBERADA')

    expect(await screen.findByText('Tu jornada fue liberada.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Vender' })).toBeDisabled()
  })
})

describe('Ficha del cliente con la jornada no abierta (tarea 13.1, D9)', () => {
  beforeEach(async () => {
    conectado(true)
    await Promise.all(baseLocal.tables.map((t) => t.clear()))
    await aplicarBootstrap(bootstrapParaVender())
  })
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('«Vender» queda deshabilitado con el aviso del estado', async () => {
    await guardar('EN_RENDICION')
    montarFicha()

    expect(await screen.findByText('Tu jornada está en rendición.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Vender' })).toBeDisabled()
    expect(screen.queryByRole('link', { name: 'Vender' })).not.toBeInTheDocument()
  })

  it('sin dato guardado ofrece «Vender» como siempre', async () => {
    montarFicha()

    expect(await screen.findByRole('link', { name: 'Vender' })).toBeInTheDocument()
  })
})

describe('Vender con la jornada no abierta (tarea 13.1, D9; INV-01)', () => {
  beforeEach(async () => {
    conectado(true)
    await Promise.all(baseLocal.tables.map((t) => t.clear()))
    await aplicarBootstrap(bootstrapParaVender())
  })
  afterEach(() => {
    vi.restoreAllMocks()
  })

  async function llegarAlCobro() {
    montarEnRuta(
      <ProveedorGuardaDelCarrito>
        <Routes>
          <Route path="/ruta/vender" element={<VenderScreen />} />
        </Routes>
      </ProveedorGuardaDelCarrito>,
      { ruta: '/ruta/vender' },
    )
    const u = userEvent.setup()
    await u.click(await screen.findByRole('button', { name: /Almacén Uno/ }))
    await u.click(await screen.findByRole('button', { name: 'Agregar Gaseosa' }))
    const cajas = await screen.findByLabelText('Cajas de Gaseosa')
    await u.clear(cajas)
    await u.type(cajas, '1')
    await u.click(screen.getByRole('button', { name: 'Siguiente' }))
    await screen.findByText(/paso 3 de 3/i)
    return u
  }

  it('con el carrito abierto, si el teléfono se entera «Confirmar venta» no confirma, el carrito sigue y muestra el aviso', async () => {
    const u = await llegarAlCobro()

    await guardar('LIBERADA')
    await u.click(screen.getByRole('button', { name: 'Confirmar venta' }))

    expect(await screen.findByText(/Tu jornada fue liberada\./)).toBeInTheDocument()
    expect(await baseLocal.ventas.count()).toBe(0)
    expect(await baseLocal.cola.count()).toBe(0)
    expect(screen.getByRole('button', { name: 'Confirmar venta' })).toBeInTheDocument()
  })

  it('el aviso nombra el estado: en rendición', async () => {
    const u = await llegarAlCobro()

    await guardar('EN_RENDICION')
    await u.click(screen.getByRole('button', { name: 'Confirmar venta' }))

    const alerta = await screen.findByText(/Tu jornada está en rendición\./)
    expect(within(alerta).queryByText(/liberada/)).not.toBeInTheDocument()
    expect(await baseLocal.ventas.count()).toBe(0)
  })

  it('sin dato guardado, aunque el servidor ya la hubiera liberado, la venta se confirma como siempre (SYN-05)', async () => {
    const u = await llegarAlCobro()

    await u.click(screen.getByRole('button', { name: 'Confirmar venta' }))

    await vi.waitFor(async () => expect(await baseLocal.ventas.count()).toBe(1))
  })
})
