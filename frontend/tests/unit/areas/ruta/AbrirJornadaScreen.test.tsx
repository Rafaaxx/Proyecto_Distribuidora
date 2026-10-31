import 'fake-indexeddb/auto'

import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { bootstrapDePrueba } from '../../utils/bootstrapDePrueba'
import { montarEnRuta } from '../../utils/rutaDePrueba'

const mocks = vi.hoisted(() => ({ listarUbicaciones: vi.fn(), abrirJornada: vi.fn() }))
vi.mock('../../../../src/features/stock/api', () => ({
  listarUbicaciones: mocks.listarUbicaciones,
  abrirJornada: mocks.abrirJornada,
}))

import { AbrirJornadaScreen } from '../../../../src/areas/ruta/jornada/AbrirJornadaScreen'
import { ErrorDeStock } from '../../../../src/features/stock/errores'
import { baseLocal } from '../../../../src/lib/dispositivo/db'
import { aplicarBootstrap } from '../../../../src/sync/aplicarBootstrap'

/**
 * Change 21, tarea 13.2 (spec `ruta/area-de-ruta`, "La jornada se abre desde el área de ruta";
 * cita RUT-01, RUT-03, INV-06, INV-16): solo con conexión y `ABRIR_JORNADA`; ubicaciones activas,
 * con toma y libres; rechazos explicados; reintento con el mismo `Operation-Id`; encadena el
 * bootstrap.
 */
const UBICACIONES = [
  { id: 'u1', nombre: 'Camioneta 1', activo: true, requiere_toma: true, jornada: null },
  { id: 'u2', nombre: 'Camioneta 2', activo: true, requiere_toma: true, jornada: { estado: 'ABIERTA' } },
  { id: 'u3', nombre: 'Depósito', activo: true, requiere_toma: false, jornada: null },
  { id: 'u4', nombre: 'Camioneta vieja', activo: false, requiere_toma: true, jornada: null },
]

function conectado(valor: boolean) {
  vi.spyOn(window.navigator, 'onLine', 'get').mockReturnValue(valor)
}

async function sembrar(permisos: string[]) {
  const b = bootstrapDePrueba()
  b.sesion.permisos = permisos
  await aplicarBootstrap(b)
}

function montar() {
  return montarEnRuta(
    <Routes>
      <Route path="/ruta/jornada/abrir" element={<AbrirJornadaScreen />} />
      <Route path="/ruta" element={<p>Inicio de prueba</p>} />
    </Routes>,
    { ruta: '/ruta/jornada/abrir' },
  )
}

async function elegirCamioneta(u: ReturnType<typeof userEvent.setup>) {
  await screen.findByRole('option', { name: 'Camioneta 1' })
  await u.selectOptions(screen.getByLabelText('Ubicación'), 'u1')
}

describe('AbrirJornadaScreen (tarea 13.2)', () => {
  beforeEach(async () => {
    mocks.listarUbicaciones.mockReset()
    mocks.abrirJornada.mockReset()
    await Promise.all(baseLocal.tables.map((t) => t.clear()))
    conectado(true)
    mocks.listarUbicaciones.mockResolvedValue({ items: UBICACIONES, cursor_siguiente: null })
  })
  afterEach(() => vi.restoreAllMocks())

  it('ofrece solo las ubicaciones activas, con toma y libres, con su "(?)"', async () => {
    await sembrar(['VENDER', 'ABRIR_JORNADA'])
    montar()

    await screen.findByRole('option', { name: 'Camioneta 1' })
    const opciones = screen.getAllByRole('option')
    expect(opciones.map((o) => o.textContent)).toEqual(['Elegí la ubicación', 'Camioneta 1'])
    expect(mocks.listarUbicaciones).toHaveBeenCalledWith(true, undefined)
    expect(screen.getByRole('button', { name: 'Ayuda: Toma actual' })).toBeInTheDocument()
  })

  it('abre la jornada, vuelve al inicio y encadena el bootstrap', async () => {
    await sembrar(['VENDER', 'ABRIR_JORNADA'])
    mocks.abrirJornada.mockResolvedValue({ id: 'j1' })
    const { sesion } = montar()
    const u = userEvent.setup()

    await elegirCamioneta(u)
    await u.click(screen.getByRole('button', { name: 'Abrir jornada' }))

    expect(await screen.findByText('Inicio de prueba')).toBeInTheDocument()
    expect(mocks.abrirJornada).toHaveBeenCalledWith('u1', expect.any(String))
    expect(sesion.reintentarEntrada).toHaveBeenCalledTimes(1)
  })

  it('sin elegir ubicación no envía nada', async () => {
    await sembrar(['VENDER', 'ABRIR_JORNADA'])
    montar()

    await userEvent.setup().click(await screen.findByRole('button', { name: 'Abrir jornada' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(/elegí la ubicación/i)
    expect(mocks.abrirJornada).not.toHaveBeenCalled()
  })

  it('ubicación tomada: explica el rechazo, no abre nada y vuelve a leer las ubicaciones', async () => {
    await sembrar(['VENDER', 'ABRIR_JORNADA'])
    mocks.abrirJornada.mockRejectedValue(new ErrorDeStock('UBICACION_TOMADA', 'ya tomada'))
    montar()
    const u = userEvent.setup()

    await elegirCamioneta(u)
    await u.click(screen.getByRole('button', { name: 'Abrir jornada' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/otra jornada/i)
    expect(screen.queryByText('Inicio de prueba')).not.toBeInTheDocument()
    await waitFor(() => expect(mocks.listarUbicaciones).toHaveBeenCalledTimes(2))
  })

  it('reintenta con el mismo Operation-Id tras un corte de red (INV-06)', async () => {
    await sembrar(['VENDER', 'ABRIR_JORNADA'])
    mocks.abrirJornada.mockRejectedValueOnce(new TypeError('Failed to fetch'))
    mocks.abrirJornada.mockResolvedValueOnce({ id: 'j1' })
    montar()
    const u = userEvent.setup()

    await elegirCamioneta(u)
    await u.click(screen.getByRole('button', { name: 'Abrir jornada' }))
    await screen.findByRole('alert')
    await u.click(screen.getByRole('button', { name: 'Abrir jornada' }))

    await screen.findByText('Inicio de prueba')
    const [primero, segundo] = mocks.abrirJornada.mock.calls
    expect(primero?.[1]).toBe(segundo?.[1])
  })

  it('sin conexión: no se puede abrir y lo dice', async () => {
    conectado(false)
    await sembrar(['VENDER', 'ABRIR_JORNADA'])
    montar()

    expect(await screen.findByRole('button', { name: 'Abrir jornada' })).toBeDisabled()
    expect(screen.getByText(/abrir la jornada requiere conexión/i)).toBeInTheDocument()
  })

  it('sin el permiso ABRIR_JORNADA no ofrece el formulario', async () => {
    await sembrar(['VENDER'])
    montar()

    expect(await screen.findByText(/no tenés permiso para abrir jornadas/i)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Abrir jornada' })).not.toBeInTheDocument()
    expect(mocks.listarUbicaciones).not.toHaveBeenCalled()
  })
})
