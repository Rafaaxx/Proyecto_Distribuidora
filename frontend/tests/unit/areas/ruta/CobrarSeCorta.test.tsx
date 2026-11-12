import 'fake-indexeddb/auto'

import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { ClienteFichaScreen } from '../../../../src/areas/ruta/clientes/ClienteFichaScreen'
import { CobrarScreen } from '../../../../src/areas/ruta/cobranzas/CobrarScreen'
import { InicioScreen } from '../../../../src/areas/ruta/InicioScreen'
import { ProveedorGuardaDelCarrito } from '../../../../src/areas/ruta/ventas/guardaDelCarrito'
import { baseLocal } from '../../../../src/lib/dispositivo/db'
import { aplicarBootstrap } from '../../../../src/sync/aplicarBootstrap'
import { marcarJornadaNoAbierta, type EstadoDeJornadaNoAbierta } from '../../../../src/sync/estadoDeJornada'
import { CLAVE_VERSION_MINIMA } from '../../../../src/sync/versionMinima'
import { ID } from '../../utils/bootstrapDePrueba'
import { bootstrapParaVender, IDS_DE_PRUEBA } from '../../utils/datosParaVender'
import { montarEnRuta } from '../../utils/rutaDePrueba'
import { sembrarCobranza, sembrarVenta } from '../../utils/sembrarVenta'

/**
 * Change 23, tarea 11.1 (spec `ruta/area-de-ruta`, «Cobrar se corta con la jornada no abierta y por
 * debajo de la versión mínima», sus cuatro escenarios; `design.md` D7; cita RUT-09, `02` §6.6,
 * INV-01): «Cobrar» se deshabilita en el inicio y en la ficha; «Confirmar cobranza» no confirma y el
 * formulario sigue; la cola se sigue enviando; vale tras recargar; sin dato, todo normal.
 */
const AHORA = new Date('2026-11-03T12:00:00.000Z')
const J1 = ID(2)
const LO_YA_VENDIDO_Y_COBRADO = 'Lo que ya vendiste y cobraste se sigue enviando.'
const AVISO_DE_VERSION = 'Esta versión ya no puede confirmar ventas nuevas: actualizá la aplicación'

function conectado(valor: boolean) {
  vi.spyOn(window.navigator, 'onLine', 'get').mockReturnValue(valor)
}

async function guardar(estado: EstadoDeJornadaNoAbierta) {
  await marcarJornadaNoAbierta(J1, estado, AHORA)
}

async function versionMinima(valor: string | null) {
  if (valor === null) await baseLocal.meta.delete(CLAVE_VERSION_MINIMA)
  else await baseLocal.meta.put({ clave: CLAVE_VERSION_MINIMA, valor })
}

/** El usuario solo cobra: así el motivo lo muestra «Cobrar» y no «Vender». */
async function sembrarSoloCobra() {
  await aplicarBootstrap(
    bootstrapParaVender((b) => {
      b.sesion.permisos = ['REGISTRAR_COBRANZA']
    }),
  )
}

function montarFicha() {
  return montarEnRuta(
    <Routes>
      <Route path="/ruta/clientes/:id" element={<ClienteFichaScreen />} />
    </Routes>,
    { ruta: `/ruta/clientes/${IDS_DE_PRUEBA.cliente}` },
  )
}

describe('«Cobrar» en el inicio con la jornada no abierta o la versión vieja (tarea 11.1, D7)', () => {
  beforeEach(async () => {
    conectado(true)
    await Promise.all(baseLocal.tables.map((t) => t.clear()))
    await sembrarSoloCobra()
  })
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it.each([
    ['LIBERADA', 'Tu jornada fue liberada.'],
    ['EN_RENDICION', 'Tu jornada está en rendición.'],
  ] as const)('con la jornada %s «Cobrar» queda deshabilitado y se lee «%s %s» (RUT-09)', async (estado, aviso) => {
    await guardar(estado)
    montarEnRuta(<InicioScreen />)

    expect(await screen.findByRole('button', { name: 'Cobrar' })).toBeDisabled()
    expect(screen.queryByRole('link', { name: 'Cobrar' })).not.toBeInTheDocument()
    expect(screen.getAllByText(aviso).length).toBeGreaterThan(0)
    expect(screen.getAllByText(LO_YA_VENDIDO_Y_COBRADO).length).toBeGreaterThan(0)
  })

  it('«Cobranzas de hoy» y «Sincronizar» siguen disponibles: la cola se sigue enviando', async () => {
    await guardar('LIBERADA')
    montarEnRuta(<InicioScreen />)

    await screen.findByRole('button', { name: 'Cobrar' })
    expect(screen.getByRole('link', { name: 'Cobranzas de hoy' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Sincronizar' })).toBeEnabled()
  })

  it('por debajo de la versión mínima «Cobrar» está deshabilitado con el aviso de versión y las cobranzas guardadas se siguen enviando (02 §6.6)', async () => {
    await sembrarCobranza('a')
    await versionMinima('9.0.0')
    montarEnRuta(<InicioScreen />)

    expect(await screen.findByRole('button', { name: 'Cobrar' })).toBeDisabled()
    expect(screen.getByText(AVISO_DE_VERSION)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Sincronizar' })).toBeEnabled()
    expect(await screen.findByText('1 cobranza sin enviar')).toBeInTheDocument()
  })

  it('sigue igual sin señal y después de recargar la aplicación (RUT-09)', async () => {
    await guardar('LIBERADA')
    const { unmount } = montarEnRuta(<InicioScreen />)
    await screen.findByRole('button', { name: 'Cobrar' })
    unmount()

    conectado(false)
    montarEnRuta(<InicioScreen />)

    expect(await screen.findByRole('button', { name: 'Cobrar' })).toBeDisabled()
    expect(screen.getByText('Tu jornada fue liberada.')).toBeInTheDocument()
  })

  it('sin dato guardado y con la versión al día «Cobrar» funciona como siempre', async () => {
    montarEnRuta(<InicioScreen />)

    expect(await screen.findByRole('link', { name: 'Cobrar' })).toHaveAttribute('href', '/ruta/cobrar')
    expect(screen.queryByText(LO_YA_VENDIDO_Y_COBRADO)).not.toBeInTheDocument()
    expect(screen.queryByText(AVISO_DE_VERSION)).not.toBeInTheDocument()
  })

  it('un dato guardado de otra jornada no corta nada', async () => {
    await marcarJornadaNoAbierta('otra-jornada', 'LIBERADA', AHORA)
    montarEnRuta(<InicioScreen />)

    expect(await screen.findByRole('link', { name: 'Cobrar' })).toBeInTheDocument()
  })

  it('el corte aparece solo cuando el teléfono se entera, sin recargar', async () => {
    montarEnRuta(<InicioScreen />)
    await screen.findByRole('link', { name: 'Cobrar' })

    await guardar('LIBERADA')

    expect(await screen.findByRole('button', { name: 'Cobrar' })).toBeDisabled()
  })
})

describe('«Cobrar» en la ficha con la jornada no abierta o la versión vieja (tarea 11.1, D7)', () => {
  beforeEach(async () => {
    conectado(true)
    await Promise.all(baseLocal.tables.map((t) => t.clear()))
  })
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('solo con REGISTRAR_COBRANZA: deshabilitado con el aviso del estado y que lo ya hecho se sigue enviando', async () => {
    await sembrarSoloCobra()
    await guardar('CERRADA')
    montarFicha()

    expect(await screen.findByRole('button', { name: 'Cobrar' })).toBeDisabled()
    expect(screen.getByText('Tu jornada fue cerrada.')).toBeInTheDocument()
    expect(screen.getByText(LO_YA_VENDIDO_Y_COBRADO)).toBeInTheDocument()
  })

  it('con VENDER y REGISTRAR_COBRANZA ambos quedan deshabilitados y el motivo se muestra una sola vez', async () => {
    await aplicarBootstrap(
      bootstrapParaVender((b) => {
        b.sesion.permisos = ['VENDER', 'REGISTRAR_COBRANZA']
      }),
    )
    await guardar('LIBERADA')
    montarFicha()

    expect(await screen.findByRole('button', { name: 'Cobrar' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Vender' })).toBeDisabled()
    expect(screen.getAllByText(LO_YA_VENDIDO_Y_COBRADO)).toHaveLength(1)
  })

  it('por debajo de la versión mínima: deshabilitado con el aviso de versión', async () => {
    await sembrarSoloCobra()
    await versionMinima('9.0.0')
    montarFicha()

    expect(await screen.findByRole('button', { name: 'Cobrar' })).toBeDisabled()
    expect(screen.getByText(AVISO_DE_VERSION)).toBeInTheDocument()
  })

  it('sin dato guardado ofrece «Cobrar» como siempre', async () => {
    await sembrarSoloCobra()
    montarFicha()

    expect(await screen.findByRole('link', { name: 'Cobrar' })).toBeInTheDocument()
  })
})

describe('«Confirmar cobranza» con la jornada no abierta o la versión vieja (tarea 11.1, D7; INV-01)', () => {
  beforeEach(async () => {
    conectado(true)
    await Promise.all(baseLocal.tables.map((t) => t.clear()))
    await sembrarSoloCobra()
  })
  afterEach(() => {
    vi.restoreAllMocks()
  })

  async function llegarAConfirmar() {
    montarEnRuta(
      <ProveedorGuardaDelCarrito>
        <Routes>
          <Route path="/ruta/cobrar" element={<CobrarScreen />} />
        </Routes>
      </ProveedorGuardaDelCarrito>,
      { ruta: '/ruta/cobrar?cliente=' + IDS_DE_PRUEBA.cliente },
    )
    const u = userEvent.setup()
    await u.type(await screen.findByLabelText('Importe a cobrar'), '10.00')
    await u.selectOptions(screen.getByLabelText('Medio de cobro 1'), 'Efectivo')
    await u.type(screen.getByLabelText('Importe del medio 1'), '10.00')
    return u
  }

  it('con el formulario abierto, si el teléfono se entera «Confirmar cobranza» no guarda, los datos siguen y se muestra el aviso', async () => {
    const u = await llegarAConfirmar()

    await guardar('LIBERADA')
    await u.click(screen.getByRole('button', { name: 'Confirmar cobranza' }))

    expect(await screen.findByText(/Tu jornada fue liberada\. Lo que ya vendiste y cobraste se sigue enviando\./)).toBeInTheDocument()
    expect(await baseLocal.cobranzas.count()).toBe(0)
    expect(await baseLocal.cola.count()).toBe(0)
    expect(screen.queryByRole('button', { name: 'Registrar' })).not.toBeInTheDocument()
    expect(screen.getByLabelText('Importe a cobrar')).toHaveValue('10.00')
    expect(screen.getByLabelText('Importe del medio 1')).toHaveValue('10.00')
  })

  it('por debajo de la versión mínima no guarda y muestra el aviso de versión', async () => {
    const u = await llegarAConfirmar()

    await versionMinima('9.0.0')
    await u.click(screen.getByRole('button', { name: 'Confirmar cobranza' }))

    expect(await screen.findByText(AVISO_DE_VERSION)).toBeInTheDocument()
    expect(await baseLocal.cobranzas.count()).toBe(0)
  })

  it('con el diálogo abierto, si la jornada se corta antes de «Registrar» tampoco guarda', async () => {
    const u = await llegarAConfirmar()
    await u.click(screen.getByRole('button', { name: 'Confirmar cobranza' }))
    const registrar = await screen.findByRole('button', { name: 'Registrar' })

    await guardar('EN_RENDICION')
    await u.click(registrar)

    expect(await screen.findByText(/Tu jornada está en rendición\./)).toBeInTheDocument()
    expect(await baseLocal.cobranzas.count()).toBe(0)
    expect(screen.getByLabelText('Importe a cobrar')).toHaveValue('10.00')
  })

  it('las ventas y cobranzas ya guardadas siguen en la cola cuando se corta', async () => {
    await sembrarVenta('a', { cajas: 1, unidades: 0 })
    await sembrarCobranza('a')
    await guardar('LIBERADA')

    expect(await baseLocal.cola.where('estado').equals('PENDIENTE').count()).toBe(2)
  })
})
