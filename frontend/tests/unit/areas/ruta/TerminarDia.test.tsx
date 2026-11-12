import 'fake-indexeddb/auto'

import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({ dispararTrasVenta: vi.fn() }))
vi.mock('../../../../src/sync/disparadores', async (importOriginal) => {
  const real = await importOriginal<typeof import('../../../../src/sync/disparadores')>()
  return { ...real, dispararTrasVenta: mocks.dispararTrasVenta }
})

import { InicioScreen } from '../../../../src/areas/ruta/InicioScreen'
import { VentaGuardadaScreen } from '../../../../src/areas/ruta/ventas/VentaGuardadaScreen'
import { baseLocal } from '../../../../src/lib/dispositivo/db'
import { aplicarBootstrap } from '../../../../src/sync/aplicarBootstrap'
import { leerJornadaNoAbierta } from '../../../../src/sync/estadoDeJornada'
import * as terminarDia from '../../../../src/sync/terminarDia'
import { bootstrapParaVender } from '../../utils/datosParaVender'
import { montarEnRuta } from '../../utils/rutaDePrueba'
import { sembrarVenta } from '../../utils/sembrarVenta'

/**
 * Change 24, tarea 14.2 (spec `ruta/area-de-ruta`, «La marca sobrevive a la recarga» y «Sin
 * permiso»; `design.md` D10; cita RUT-05, SEG-06, INV-01): «Terminar el día» en el inicio, con
 * permiso y confirmación; después corta «Vender», «Cobrar» y «Anular venta» con el aviso, también
 * tras recargar y sin señal.
 */
const AVISO = 'Terminaste el día. Pasá a rendir con tu supervisor.'
const CONFIRMACION = 'Después no vas a poder vender, anular ventas ni cobrar en esta jornada.'
const FALTA_ENVIAR = 'Lo que falta enviar se envía antes de la entrega.'

function conectado(valor: boolean) {
  vi.spyOn(window.navigator, 'onLine', 'get').mockReturnValue(valor)
}

async function sembrar(permisos: string[]) {
  await aplicarBootstrap(
    bootstrapParaVender((b) => {
      b.sesion.permisos = permisos
    }),
  )
}

describe('«Terminar el día» en el inicio (tarea 14.2, D10)', () => {
  beforeEach(async () => {
    mocks.dispararTrasVenta.mockReset()
    conectado(true)
    await Promise.all(baseLocal.tables.map((t) => t.clear()))
  })
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('con ABRIR_JORNADA se ofrece, junto con su ayuda (RUT-05)', async () => {
    await sembrar(['VENDER', 'ABRIR_JORNADA'])
    montarEnRuta(<InicioScreen />)

    expect(await screen.findByRole('button', { name: 'Terminar el día' })).toBeEnabled()
    expect(screen.getByRole('button', { name: 'Ayuda: Terminar el día' })).toBeInTheDocument()
  })

  it('sin ABRIR_JORNADA en el bootstrap no se ofrece (SEG-06)', async () => {
    await sembrar(['VENDER'])
    montarEnRuta(<InicioScreen />)

    await screen.findByRole('link', { name: 'Vender' })
    expect(screen.queryByRole('button', { name: 'Terminar el día' })).not.toBeInTheDocument()
  })

  it('pide confirmación con el aviso de lo que pasa después; cancelar no escribe nada', async () => {
    await sembrar(['VENDER', 'ABRIR_JORNADA'])
    montarEnRuta(<InicioScreen />)
    const u = userEvent.setup()

    await u.click(await screen.findByRole('button', { name: 'Terminar el día' }))
    const dialogo = await screen.findByRole('dialog', { name: '¿Terminar el día?' })
    expect(within(dialogo).getByText(CONFIRMACION)).toBeInTheDocument()
    await u.click(within(dialogo).getByRole('button', { name: 'Cancelar' }))

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(await baseLocal.cola.count()).toBe(0)
    expect(await leerJornadaNoAbierta()).toBeNull()
    expect(screen.getByRole('link', { name: 'Vender' })).toBeInTheDocument()
  })

  it('sin señal: confirma, encola la entrega, dispara la sincronización y corta «Vender» y «Cobrar» con el aviso (RUT-05, SYN-03)', async () => {
    conectado(false)
    await sembrar(['VENDER', 'ABRIR_JORNADA', 'REGISTRAR_COBRANZA'])
    montarEnRuta(<InicioScreen />)
    const u = userEvent.setup()

    await u.click(await screen.findByRole('button', { name: 'Terminar el día' }))
    await u.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Terminar el día' }))

    expect(await screen.findByText(AVISO)).toBeInTheDocument()
    const cola = await baseLocal.cola.toArray()
    expect(cola).toHaveLength(1)
    expect(cola[0]?.sobre).toMatchObject({ tipo: 'JORNADA_ENTREGAR', modo: 'OFFLINE', version: 1 })
    expect(mocks.dispararTrasVenta).toHaveBeenCalledTimes(1)
    expect(await screen.findByRole('button', { name: 'Vender' })).toBeDisabled()
    expect(await screen.findByRole('button', { name: 'Cobrar' })).toBeDisabled()
    expect(screen.queryByRole('button', { name: 'Terminar el día' })).not.toBeInTheDocument()
  })

  it('con ventas sin enviar avisa que lo que falta se envía antes de la entrega; sin pendientes no lo dice', async () => {
    await sembrar(['VENDER', 'ABRIR_JORNADA'])
    await sembrarVenta('a')
    const u = userEvent.setup()
    const { unmount } = montarEnRuta(<InicioScreen />)
    await u.click(await screen.findByRole('button', { name: 'Terminar el día' }))
    await u.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Terminar el día' }))

    expect(await screen.findByText(FALTA_ENVIAR)).toBeInTheDocument()
    unmount()

    // Lo pendiente se envió: queda solo la entrega, que no cuenta como pendiente a enviar «antes».
    await baseLocal.cola.where('estado').equals('PENDIENTE').modify((c) => {
      if (c.sobre.tipo !== 'JORNADA_ENTREGAR') c.estado = 'ACEPTADO'
    })
    montarEnRuta(<InicioScreen />)
    expect(await screen.findByText(AVISO)).toBeInTheDocument()
    expect(screen.queryByText(FALTA_ENVIAR)).not.toBeInTheDocument()
  })

  it('la marca sobrevive a la recarga: el inicio sigue cortado y sin «Terminar el día» (RUT-05)', async () => {
    await sembrar(['VENDER', 'ABRIR_JORNADA', 'REGISTRAR_COBRANZA'])
    const u = userEvent.setup()
    const { unmount } = montarEnRuta(<InicioScreen />)
    await u.click(await screen.findByRole('button', { name: 'Terminar el día' }))
    await u.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Terminar el día' }))
    await screen.findByText(AVISO)
    unmount()

    conectado(false)
    montarEnRuta(<InicioScreen />)

    expect(await screen.findByText(AVISO)).toBeInTheDocument()
    expect(await screen.findByRole('button', { name: 'Vender' })).toBeDisabled()
    expect(await screen.findByRole('button', { name: 'Cobrar' })).toBeDisabled()
    expect(screen.queryByRole('button', { name: 'Terminar el día' })).not.toBeInTheDocument()
    expect(await baseLocal.cola.count()).toBe(1)
  })

  it('INV-01: si falla la escritura local lo dice, no corta nada y se puede reintentar', async () => {
    await sembrar(['VENDER', 'ABRIR_JORNADA'])
    vi.spyOn(baseLocal.cola, 'add').mockRejectedValueOnce(new Error('disco lleno'))
    montarEnRuta(<InicioScreen />)
    const u = userEvent.setup()

    await u.click(await screen.findByRole('button', { name: 'Terminar el día' }))
    await u.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Terminar el día' }))

    expect(await screen.findByText('No se pudo terminar el día. Probá de nuevo.')).toBeInTheDocument()
    expect(await baseLocal.cola.count()).toBe(0)
    expect(screen.queryByText(AVISO)).not.toBeInTheDocument()
    expect(mocks.dispararTrasVenta).not.toHaveBeenCalled()

    await u.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Terminar el día' }))
    expect(await screen.findByText(AVISO)).toBeInTheDocument()
    expect(await baseLocal.cola.count()).toBe(1)
  })
})

describe('«Anular venta» después de terminar el día (tarea 14.2, D10; RUT-05)', () => {
  beforeEach(async () => {
    await Promise.all(baseLocal.tables.map((t) => t.clear()))
  })

  it('no se ofrece con la entrega hecha y sí antes', async () => {
    await sembrar(['VENDER', 'ANULAR_VENTA'])
    await sembrarVenta('a')
    const montar = () =>
      montarEnRuta(
        <Routes>
          <Route path="/ruta/ventas/:id" element={<VentaGuardadaScreen />} />
        </Routes>,
        { ruta: '/ruta/ventas/venta-a' },
      )
    const { unmount } = montar()
    expect(await screen.findByRole('link', { name: 'Anular venta' })).toBeInTheDocument()
    unmount()

    await terminarDia.terminarElDia({
      operationId: 'op-e',
      usuarioId: '00000000-0000-4000-8000-000000000001',
      dispositivoId: 'disp-1',
      ahora: new Date('2026-11-04T18:00:00.000Z'),
      appVersion: '1.0.0',
    })
    montar()

    await screen.findByRole('heading', { name: /Venta 0001-000008/ })
    expect(screen.queryByRole('link', { name: 'Anular venta' })).not.toBeInTheDocument()
  })
})
