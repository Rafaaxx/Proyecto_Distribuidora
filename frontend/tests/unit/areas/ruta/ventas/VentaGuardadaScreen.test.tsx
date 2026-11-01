import 'fake-indexeddb/auto'

import { screen } from '@testing-library/react'
import { Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { VentaGuardadaScreen } from '../../../../../src/areas/ruta/ventas/VentaGuardadaScreen'
import { baseLocal } from '../../../../../src/lib/dispositivo/db'
import { aplicarBootstrap } from '../../../../../src/sync/aplicarBootstrap'
import { bootstrapParaVender } from '../../../utils/datosParaVender'
import { montarEnRuta } from '../../../utils/rutaDePrueba'
import { sembrarVenta } from '../../../utils/sembrarVenta'

/**
 * Change 22a, tarea 10.3 (spec `ventas/venta-en-ruta`, "La venta confirmada se muestra con su
 * número y su estado"; `design.md` D13, D14; cita VTA-06): número, total, "Sin enviar", "Compartir
 * nota" solo si el navegador comparte archivos, "Descargar nota" y "Nueva venta".
 */
function comparteArchivos(comparte: boolean) {
  Object.defineProperty(window.navigator, 'canShare', {
    configurable: true,
    value: comparte ? () => true : undefined,
  })
}

function montar(ventaId: string) {
  return montarEnRuta(
    <Routes>
      <Route path="/ruta/ventas/:id" element={<VentaGuardadaScreen />} />
    </Routes>,
    { ruta: `/ruta/ventas/${ventaId}` },
  )
}

describe('VentaGuardadaScreen (tarea 10.3)', () => {
  beforeEach(async () => {
    await Promise.all(baseLocal.tables.map((t) => t.clear()))
    await aplicarBootstrap(bootstrapParaVender())
  })

  afterEach(() => comparteArchivos(false))

  it('muestra el número asignado, el total, "Sin enviar" y las acciones de la nota', async () => {
    comparteArchivos(true)
    await sembrarVenta('a')

    montar('venta-a')

    expect(await screen.findByRole('heading', { name: 'Venta 0001-000008' })).toBeInTheDocument()
    expect(screen.getByText('$ 120.000,00')).toBeInTheDocument()
    expect(screen.getByText('Sin enviar')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Compartir nota' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Descargar nota' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Nueva venta' })).toHaveAttribute('href', '/ruta/vender')
    expect(screen.getByRole('button', { name: /ayuda: sin enviar/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /ayuda: número de venta/i })).toBeInTheDocument()
  })

  it('sin Web Share con archivos no ofrece "Compartir nota" pero sí "Descargar nota"', async () => {
    comparteArchivos(false)
    await sembrarVenta('a')

    montar('venta-a')

    expect(await screen.findByRole('button', { name: 'Descargar nota' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Compartir nota' })).not.toBeInTheDocument()
  })

  it('la segunda venta lleva el número siguiente (VTA-06)', async () => {
    await sembrarVenta('a')
    await sembrarVenta('b', { cajas: 0, unidades: 2 })

    montar('venta-b')

    expect(await screen.findByRole('heading', { name: 'Venta 0001-000009' })).toBeInTheDocument()
  })

  it('una venta que no está en el teléfono avisa y vuelve a Ventas de hoy', async () => {
    montar('no-existe')

    expect(await screen.findByText('No encontramos esa venta en este teléfono.')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Ventas de hoy' })).toHaveAttribute('href', '/ruta/ventas')
  })

  /** Change 22b, tarea 10.3 (cita SYN-04, SYN-09): las etiquetas del detalle. */
  it.each([
    ['ACEPTADA', 'Enviada'],
    ['CON_OBSERVACIONES', 'Con observaciones'],
    ['RECHAZADA', 'Rechazada'],
  ] as const)('el detalle de una venta %s dice «%s»', async (estado, etiqueta) => {
    await sembrarVenta('a')
    await baseLocal.ventas.update('venta-a', { estado_envio: estado })

    montar('venta-a')

    expect(await screen.findByText(etiqueta)).toBeInTheDocument()
    if (estado === 'RECHAZADA') {
      expect(
        screen.getByText('El sistema no aceptó esta venta. Sigue guardada en el teléfono; avisá a administración.'),
      ).toBeInTheDocument()
    }
  })
})

vi.mock('../../../../../src/lib/nota/pdf', () => ({ generarPdfDeNota: vi.fn(async () => new Blob(['pdf'])) }))
