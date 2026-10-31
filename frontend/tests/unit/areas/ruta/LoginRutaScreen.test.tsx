import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join } from 'node:path'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }))

vi.mock('../../../../src/lib/api/httpClient', () => ({ apiFetch: apiFetchMock }))
vi.mock('../../../../src/lib/dispositivo/dispositivoId', () => ({
  obtenerOGenerarDispositivoId: vi.fn(async () => 'dispositivo-de-prueba'),
}))

import { LoginRutaScreen } from '../../../../src/areas/ruta/auth/LoginRutaScreen'
import { obtenerAccessToken } from '../../../../src/lib/auth/tokenStore'

function respuesta(status: number, cuerpo: unknown) {
  return { ok: status >= 200 && status < 300, status, json: async () => cuerpo }
}

function conectado(valor: boolean) {
  vi.spyOn(window.navigator, 'onLine', 'get').mockReturnValue(valor)
}

async function completarYEnviar(usuario = 'vendedor', contrasena = 'secreta1') {
  const u = userEvent.setup()
  await u.type(screen.getByLabelText(/organización/i), 'demo')
  await u.type(screen.getByLabelText(/^usuario$/i), usuario)
  await u.type(screen.getByLabelText(/contraseña/i), contrasena)
  await u.click(screen.getByRole('button', { name: /iniciar sesión/i }))
}

/**
 * Change 21, tarea 9.1 (spec `ruta/area-de-ruta`, "El área de ruta tiene su propio inicio de
 * sesión"; `design.md` D12; SEG-01, SEG-02, ADR-018).
 */
describe('LoginRutaScreen (tarea 9.1)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
    conectado(true)
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('con conexión inicia sesión enviando el identificador del dispositivo y avisa', async () => {
    apiFetchMock.mockResolvedValueOnce(respuesta(200, { access_token: 'tok-ruta' }))
    const onIniciada = vi.fn()
    render(<LoginRutaScreen onIniciada={onIniciada} />)

    await completarYEnviar()

    await waitFor(() => expect(onIniciada).toHaveBeenCalledTimes(1))
    const [ruta, init] = apiFetchMock.mock.calls[0] as [string, RequestInit]
    expect(ruta).toBe('/auth/login')
    const cuerpo = JSON.parse(String(init.body)) as Record<string, string>
    expect(cuerpo).toMatchObject({
      organizacion_slug: 'demo',
      usuario: 'vendedor',
      contrasena: 'secreta1',
      dispositivo_id: 'dispositivo-de-prueba',
    })
    expect(obtenerAccessToken()).toBe('tok-ruta')
  })

  it.each([
    [401, 'Usuario o contraseña incorrectos.'],
    [423, 'La cuenta está bloqueada por intentos fallidos.'],
  ])('un rechazo %s se muestra explicado y sigue en la pantalla', async (estado, titulo) => {
    apiFetchMock.mockResolvedValueOnce(respuesta(estado, { title: titulo }))
    const onIniciada = vi.fn()
    render(<LoginRutaScreen onIniciada={onIniciada} />)

    await completarYEnviar()

    expect(await screen.findByText(titulo)).toBeInTheDocument()
    expect(onIniciada).not.toHaveBeenCalled()
    expect(screen.getByRole('button', { name: /iniciar sesión/i })).toBeEnabled()
  })

  it('un corte de red durante el envío se explica en palabras simples', async () => {
    apiFetchMock.mockRejectedValueOnce(new TypeError('Failed to fetch'))
    render(<LoginRutaScreen onIniciada={vi.fn()} />)

    await completarYEnviar()

    expect(await screen.findByText(/no se pudo conectar/i)).toBeInTheDocument()
  })

  it('sin conexión avisa que iniciar sesión la requiere y no deja enviar', async () => {
    conectado(false)
    render(<LoginRutaScreen onIniciada={vi.fn()} />)

    expect(screen.getByText(/requiere conexión/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /iniciar sesión/i })).toBeDisabled()
    expect(apiFetchMock).not.toHaveBeenCalled()
  })

  it('al volver la señal habilita el envío', async () => {
    conectado(false)
    render(<LoginRutaScreen onIniciada={vi.fn()} />)
    expect(screen.getByRole('button', { name: /iniciar sesión/i })).toBeDisabled()

    conectado(true)
    act(() => {
      window.dispatchEvent(new Event('online'))
    })

    await waitFor(() => expect(screen.getByRole('button', { name: /iniciar sesión/i })).toBeEnabled())
  })

  it('muestra el motivo de por qué se pide iniciar sesión otra vez', () => {
    render(<LoginRutaScreen onIniciada={vi.fn()} motivo="bloqueado" />)
    expect(screen.getByText(/intentos del PIN/i)).toBeInTheDocument()
  })
})

function archivosFuente(dir: string): string[] {
  return readdirSync(dir).flatMap((nombre) => {
    const ruta = join(dir, nombre)
    return statSync(ruta).isDirectory() ? archivosFuente(ruta) : /\.(ts|tsx)$/.test(nombre) ? [ruta] : []
  })
}

describe('área de ruta: no descarga el código de /admin (tarea 9.1, D12)', () => {
  it('ningún archivo de areas/ruta importa de areas/admin ni usa TanStack Query', () => {
    const raiz = join(__dirname, '../../../../src/areas/ruta')
    const ofensores = archivosFuente(raiz).filter((archivo) => {
      const codigo = readFileSync(archivo, 'utf8')
      return /from\s+['"][^'"]*areas\/admin|from\s+['"]\.\.\/admin|@tanstack\/react-query/.test(codigo)
    })
    expect(ofensores).toEqual([])
  })
})
