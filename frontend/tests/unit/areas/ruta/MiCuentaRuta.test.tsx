import 'fake-indexeddb/auto'

import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { montarEnRuta } from '../../utils/rutaDePrueba'

const mocks = vi.hoisted(() => ({ cambiarMiContrasena: vi.fn(), cerrarSesionDelDispositivo: vi.fn() }))
vi.mock('../../../../src/features/identidad/usuariosApi', async (importarOriginal) => ({
  ...(await importarOriginal<typeof import('../../../../src/features/identidad/usuariosApi')>()),
  cambiarMiContrasena: mocks.cambiarMiContrasena,
}))
vi.mock('../../../../src/sync/cierreDeSesion', () => ({
  cerrarSesionDelDispositivo: mocks.cerrarSesionDelDispositivo,
}))

import { CambiarPinScreen } from '../../../../src/areas/ruta/cuenta/CambiarPinScreen'
import { MiCuentaScreen } from '../../../../src/areas/ruta/cuenta/MiCuentaScreen'
import { MiContrasenaRutaScreen } from '../../../../src/areas/ruta/cuenta/MiContrasenaRutaScreen'
import { ErrorDeApiUsuarios } from '../../../../src/features/identidad/usuariosApi'
import { baseLocal } from '../../../../src/lib/dispositivo/db'
import { definirPin, desbloquearConPin } from '../../../../src/lib/sesionLocal/pin'

/**
 * Change 21, tarea 14.3 (spec `ruta/area-de-ruta`, "Mi cuenta en el área de ruta"; cita ADR-060,
 * SEG-03, SEG-04): "Mi contraseña" con conexión (misma lógica que `/admin`), "Cambiar PIN" con y
 * sin conexión y "Cerrar sesión" (tarea 10.1).
 */
const PIN = '482915'

function conectado(valor: boolean) {
  vi.spyOn(window.navigator, 'onLine', 'get').mockReturnValue(valor)
}

function montarCuenta() {
  return montarEnRuta(
    <Routes>
      <Route path="/ruta/cuenta" element={<MiCuentaScreen />} />
      <Route path="/ruta/cuenta/contrasena" element={<MiContrasenaRutaScreen />} />
      <Route path="/ruta/cuenta/pin" element={<CambiarPinScreen />} />
    </Routes>,
    { ruta: '/ruta/cuenta' },
  )
}

async function irA(ruta: string) {
  return montarEnRuta(
    <Routes>
      <Route path="/ruta/cuenta/contrasena" element={<MiContrasenaRutaScreen />} />
      <Route path="/ruta/cuenta/pin" element={<CambiarPinScreen />} />
    </Routes>,
    { ruta },
  )
}

describe('Mi cuenta en /ruta (tarea 14.3)', () => {
  beforeEach(async () => {
    mocks.cambiarMiContrasena.mockReset()
    mocks.cerrarSesionDelDispositivo.mockReset()
    await Promise.all(baseLocal.tables.map((t) => t.clear()))
    conectado(true)
  })
  afterEach(() => vi.restoreAllMocks())

  it('con conexión ofrece Mi contraseña, Cambiar PIN y Cerrar sesión', () => {
    montarCuenta()

    expect(screen.getByRole('link', { name: 'Mi contraseña' })).toHaveAttribute('href', '/ruta/cuenta/contrasena')
    expect(screen.getByRole('link', { name: 'Cambiar PIN' })).toHaveAttribute('href', '/ruta/cuenta/pin')
    expect(screen.getByRole('button', { name: 'Cerrar sesión' })).toBeEnabled()
  })

  it('sin conexión: Mi contraseña y Cerrar sesión deshabilitados con su motivo; Cambiar PIN sigue', () => {
    conectado(false)
    montarCuenta()

    expect(screen.queryByRole('link', { name: 'Mi contraseña' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Mi contraseña' })).toBeDisabled()
    expect(screen.getByText(/cambiar la contraseña requiere conexión/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Cerrar sesión' })).toBeDisabled()
    expect(screen.getByText(/cerrar sesión requiere conexión/i)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Cambiar PIN' })).toBeInTheDocument()
  })

  it('cerrar sesión llama al cierre y vuelve al login', async () => {
    mocks.cerrarSesionDelDispositivo.mockResolvedValue('cerrada')
    const { sesion } = montarCuenta()
    const u = userEvent.setup()

    await u.click(screen.getByRole('button', { name: 'Cerrar sesión' }))
    await u.click(screen.getByRole('button', { name: 'Confirmar' }))

    await waitFor(() => expect(sesion.alCerrarSesion).toHaveBeenCalledTimes(1))
  })
})

describe('Mi contraseña en /ruta (tarea 14.3)', () => {
  beforeEach(async () => {
    mocks.cambiarMiContrasena.mockReset()
    await Promise.all(baseLocal.tables.map((t) => t.clear()))
    conectado(true)
  })
  afterEach(() => vi.restoreAllMocks())

  async function completar(u: ReturnType<typeof userEvent.setup>, actual: string, nueva: string, repetida = nueva) {
    await u.type(screen.getByLabelText('Tu contraseña actual'), actual)
    await u.type(screen.getByLabelText('Contraseña nueva'), nueva)
    await u.type(screen.getByLabelText('Repetí la contraseña nueva'), repetida)
    await u.click(screen.getByRole('button', { name: 'Cambiar mi contraseña' }))
  }

  it('cambia la contraseña con la actual y la sesión del teléfono sigue abierta', async () => {
    mocks.cambiarMiContrasena.mockResolvedValue(undefined)
    const { sesion } = await irA('/ruta/cuenta/contrasena')
    const u = userEvent.setup()

    await completar(u, 'ClaveVieja#1', 'ClaveNueva#2024')

    expect(await screen.findByRole('status')).toHaveTextContent(/tu contraseña quedó cambiada/i)
    expect(mocks.cambiarMiContrasena).toHaveBeenCalledWith('ClaveVieja#1', 'ClaveNueva#2024', expect.any(String))
    expect(sesion.alCerrarSesion).not.toHaveBeenCalled()
    expect(screen.getByLabelText('Tu contraseña actual')).toHaveValue('')
  })

  it('contraseña actual incorrecta: explica el rechazo y no cambia nada', async () => {
    mocks.cambiarMiContrasena.mockRejectedValue(
      new ErrorDeApiUsuarios('IDENTIDAD_CONTRASENA_INCORRECTA', 'La contraseña actual no es correcta.', 403),
    )
    await irA('/ruta/cuenta/contrasena')

    await completar(userEvent.setup(), 'incorrecta', 'ClaveNueva#2024')

    expect(await screen.findByRole('alert')).toHaveTextContent(/contraseña/i)
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })

  it('las dos contraseñas nuevas deben coincidir: no se envía nada', async () => {
    await irA('/ruta/cuenta/contrasena')

    await completar(userEvent.setup(), 'ClaveVieja#1', 'ClaveNueva#2024', 'otra distinta')

    expect(await screen.findByText(/tienen que ser iguales/i)).toBeInTheDocument()
    expect(mocks.cambiarMiContrasena).not.toHaveBeenCalled()
  })

  it('un corte de red lo explica y el reintento reenvía el mismo Operation-Id (INV-06)', async () => {
    mocks.cambiarMiContrasena.mockRejectedValueOnce(new TypeError('Failed to fetch'))
    mocks.cambiarMiContrasena.mockResolvedValueOnce(undefined)
    await irA('/ruta/cuenta/contrasena')
    const u = userEvent.setup()

    await completar(u, 'ClaveVieja#1', 'ClaveNueva#2024')
    expect(await screen.findByRole('alert')).toHaveTextContent(/conexión/i)
    await completar(u, 'ClaveVieja#1', 'ClaveNueva#2024')

    await screen.findByRole('status')
    const [primero, segundo] = mocks.cambiarMiContrasena.mock.calls
    expect(primero?.[2]).toBe(segundo?.[2])
  })

  it('sin conexión no se puede enviar y lo dice', async () => {
    conectado(false)
    await irA('/ruta/cuenta/contrasena')

    expect(screen.getByRole('button', { name: 'Cambiar mi contraseña' })).toBeDisabled()
    expect(screen.getByText(/cambiar la contraseña requiere conexión/i)).toBeInTheDocument()
  })
})

describe('Cambiar PIN en /ruta (tarea 14.3)', () => {
  beforeEach(async () => {
    await Promise.all(baseLocal.tables.map((t) => t.clear()))
    conectado(true)
    await definirPin(PIN, PIN)
  }, 15_000)
  afterEach(() => vi.restoreAllMocks())

  async function completar(u: ReturnType<typeof userEvent.setup>, actual: string, nuevo: string, repetido = nuevo) {
    await u.type(screen.getByLabelText('PIN actual'), actual)
    await u.type(screen.getByLabelText('PIN nuevo'), nuevo)
    await u.type(screen.getByLabelText('Repetí el PIN nuevo'), repetido)
    await u.click(screen.getByRole('button', { name: 'Cambiar PIN' }))
  }

  it('cambia el PIN con el actual, también sin conexión: el anterior deja de abrir', async () => {
    conectado(false)
    await irA('/ruta/cuenta/pin')

    await completar(userEvent.setup(), PIN, '907314')

    expect(await screen.findByRole('status', {}, { timeout: 10_000 })).toHaveTextContent(/cambiaste tu pin/i)
    expect(await desbloquearConPin('907314')).toEqual({ tipo: 'ok' })
    expect(await desbloquearConPin(PIN)).toMatchObject({ tipo: 'incorrecto' })
  }, 30_000)

  it('PIN actual incorrecto: suma un fallo, dice cuántos quedan (10 en total) y no cambia nada', async () => {
    await irA('/ruta/cuenta/pin')

    await completar(userEvent.setup(), '000001', '907314')

    expect(await screen.findByRole('alert', {}, { timeout: 10_000 })).toHaveTextContent('Te quedan 9 intentos')
    expect(await desbloquearConPin(PIN)).toEqual({ tipo: 'ok' })
  }, 30_000)

  it('un PIN nuevo trivial se rechaza sin sumar fallos', async () => {
    await irA('/ruta/cuenta/pin')

    await completar(userEvent.setup(), PIN, '111111')

    expect(await screen.findByRole('alert', {}, { timeout: 10_000 })).toHaveTextContent(/iguales/i)
  }, 30_000)

  it('al agotar los intentos (10) borra el PIN y vuelve al login', async () => {
    await baseLocal.meta.put({ clave: 'pin_intentos', valor: '9' })
    const { sesion } = await irA('/ruta/cuenta/pin')

    await completar(userEvent.setup(), '000001', '907314')

    await waitFor(() => expect(sesion.alBloquearse).toHaveBeenCalledTimes(1))
    expect(await baseLocal.meta.get('pin_hash')).toBeUndefined()
  }, 30_000)

  it('lleva el "(?)" del PIN', async () => {
    await irA('/ruta/cuenta/pin')
    expect(screen.getByRole('button', { name: 'Ayuda: PIN de este teléfono' })).toBeInTheDocument()
  })
})
