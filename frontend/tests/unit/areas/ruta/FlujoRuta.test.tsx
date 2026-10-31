import 'fake-indexeddb/auto'

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { bootstrapDePrueba, clienteDePrueba, ID } from '../../utils/bootstrapDePrueba'

import { RutaScreen } from '../../../../src/areas/ruta/RutaScreen'
import { limpiarAccessToken } from '../../../../src/lib/auth/tokenStore'
import { baseLocal } from '../../../../src/lib/dispositivo/db'

/**
 * Change 21, tarea 17.2 (de punta a punta en el navegador simulado: `fake-indexeddb`, Web Crypto
 * real y un `fetch` simulado, sin ningún mock de módulos propios): login, PIN, abrir la jornada,
 * bootstrap, clientes y productos; sin red: recarga, PIN y datos visibles; diez PIN errados
 * bloquean y piden el login; el login vuelve a definir el PIN con los datos intactos.
 * Cita RUT-03, SYN-11, SEG-03, SEG-04, INV-01, ADR-011, ADR-062.
 */
const PIN = '482915'
const PIN_NUEVO = '735190'

interface Servidor {
  conRed: boolean
  jornadaAbierta: boolean
  llamadas: string[]
}

function respuesta(status: number, cuerpo: unknown): Response {
  return new Response(JSON.stringify(cuerpo), { status, headers: { 'Content-Type': 'application/json' } })
}

function instalarServidor(): Servidor {
  const servidor: Servidor = { conRed: true, jornadaAbierta: false, llamadas: [] }
  vi.stubGlobal(
    'fetch',
    vi.fn(async (entrada: RequestInfo | URL, init?: RequestInit) => {
      if (!servidor.conRed) throw new TypeError('Failed to fetch')
      const url = new URL(String(entrada), 'http://x')
      const metodo = (init?.method ?? 'GET').toUpperCase()
      servidor.llamadas.push(`${metodo} ${url.pathname}`)
      const ruta = url.pathname.replace('/api/v1', '')
      if (ruta === '/auth/login') return respuesta(200, { access_token: 'token-1' })
      if (ruta === '/auth/refresh') return respuesta(200, { access_token: 'token-2' })
      if (ruta === '/yo') return respuesta(200, { usuario: { id: ID(1), nombre: 'Vendedor Uno' } })
      if (ruta === '/stock/jornadas/actual') {
        return servidor.jornadaAbierta
          ? respuesta(200, { id: ID(2), estado: 'ABIERTA' })
          : respuesta(404, { codigo: 'JORNADA_INEXISTENTE', title: 'Sin jornada' })
      }
      if (ruta === '/stock/ubicaciones') {
        return respuesta(200, {
          items: [{ id: ID(3), nombre: 'Camioneta 1', activo: true, requiere_toma: true, jornada: null }],
          cursor_siguiente: null,
        })
      }
      if (ruta === '/stock/jornadas' && metodo === 'POST') {
        servidor.jornadaAbierta = true
        return respuesta(201, { id: ID(2), estado: 'ABIERTA' })
      }
      if (ruta === '/sync/bootstrap') {
        if (!servidor.jornadaAbierta) return respuesta(409, { codigo: 'JORNADA_REQUERIDA', title: 'Sin jornada' })
        const b = bootstrapDePrueba({
          clientes: [clienteDePrueba(1, 'Almacén Norte'), clienteDePrueba(2, 'Kiosco Sur')],
        })
        b.sesion.permisos = ['VENDER', 'ABRIR_JORNADA']
        return respuesta(200, b)
      }
      return respuesta(404, { codigo: 'SIN_REGLA', title: `Sin regla para ${metodo} ${ruta}` })
    }),
  )
  return servidor
}

function conectado(servidor: Servidor, valor: boolean) {
  servidor.conRed = valor
  vi.spyOn(window.navigator, 'onLine', 'get').mockReturnValue(valor)
}

/** Un arranque de la aplicación: un montaje nuevo sobre la misma base local. */
function abrirAplicacion() {
  return render(
    <MemoryRouter initialEntries={['/ruta']}>
      <Routes>
        <Route path="/ruta/*" element={<RutaScreen />} />
      </Routes>
    </MemoryRouter>,
  )
}

type Usuario = ReturnType<typeof userEvent.setup>

async function tipearPin(u: Usuario, pin: string) {
  const campo = await screen.findByLabelText(/^PIN$/i)
  await u.clear(campo)
  await u.type(campo, pin)
  await u.click(screen.getByRole('button', { name: /desbloquear/i }))
}

async function iniciarSesion(u: Usuario) {
  await u.type(await screen.findByLabelText(/organización/i), 'demo')
  await u.type(screen.getByLabelText(/^usuario$/i), 'vendedor')
  await u.type(screen.getByLabelText(/contraseña/i), 'secreta1')
  await u.click(screen.getByRole('button', { name: /iniciar sesión/i }))
}

async function definirPinEnPantalla(u: Usuario, pin: string) {
  const campo = await screen.findByLabelText(/^PIN$/i)
  const repetir = screen.getByLabelText(/repetí el PIN/i)
  await u.clear(campo)
  await u.clear(repetir)
  await u.type(campo, pin)
  await u.type(repetir, pin)
  await u.click(screen.getByRole('button', { name: /guardar PIN/i }))
}

describe('Flujo de /ruta de punta a punta (tarea 17.2)', () => {
  beforeEach(async () => {
    await Promise.all(baseLocal.tables.map((t) => t.clear()))
    limpiarAccessToken()
  })
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('login, PIN, jornada, bootstrap, datos sin red con PIN, bloqueo por diez fallos y login con datos intactos', async () => {
    const servidor = instalarServidor()
    conectado(servidor, true)
    const u = userEvent.setup()
    const arranque1 = abrirAplicacion()

    // login y PIN (el trivial se rechaza)
    await iniciarSesion(u)
    await definirPinEnPantalla(u, '123456')
    expect(await screen.findByText(/dígitos seguidos/i)).toBeInTheDocument()
    await definirPinEnPantalla(u, PIN)

    // sin jornada: la abre desde /ruta y se baja el bootstrap
    await u.click(await screen.findByRole('link', { name: /abrir jornada/i }))
    await screen.findByRole('option', { name: 'Camioneta 1' })
    await u.selectOptions(screen.getByLabelText('Ubicación'), ID(3))
    await u.click(screen.getByRole('button', { name: 'Abrir jornada' }))
    expect(await screen.findByText(/Hola, Vendedor Uno/)).toBeInTheDocument()
    expect(servidor.llamadas).toContain('GET /api/v1/sync/bootstrap')

    // clientes y productos salen de la base local
    await u.click(screen.getAllByRole('link', { name: 'Clientes' })[0] as HTMLElement)
    expect(await screen.findByText('Almacén Norte')).toBeInTheDocument()
    expect(screen.getByText('Kiosco Sur')).toBeInTheDocument()
    await u.click(screen.getAllByRole('link', { name: 'Productos' })[0] as HTMLElement)
    expect(await screen.findByText('Gaseosa')).toBeInTheDocument()

    // sin red: recarga (arranque nuevo), pide el PIN y muestra los datos sin tocar la red
    conectado(servidor, false)
    const llamadasAntes = servidor.llamadas.length
    arranque1.unmount()
    const arranque2 = abrirAplicacion()
    await tipearPin(u, PIN)
    expect(await screen.findByText(/Hola, Vendedor Uno/)).toBeInTheDocument()
    await u.click(screen.getAllByRole('link', { name: 'Clientes' })[0] as HTMLElement)
    expect(await screen.findByText('Almacén Norte')).toBeInTheDocument()
    expect(servidor.llamadas.length).toBe(llamadasAntes)

    // diez PIN errados en un arranque nuevo: se borra el PIN y se pide el login, con los datos
    arranque2.unmount()
    const arranque3 = abrirAplicacion()
    for (let i = 1; i <= 10; i += 1) {
      await tipearPin(u, String(100000 + i))
      if (i < 10) await screen.findByText(i === 9 ? /te queda 1 intento/i : new RegExp(`te quedan ${10 - i} intentos`, 'i'))
    }
    expect(await screen.findByText(/intentos del PIN/i)).toBeInTheDocument()
    expect(await baseLocal.meta.get('pin_hash')).toBeUndefined()
    expect(await baseLocal.clientes.count()).toBe(2)
    arranque3.unmount()

    // con red vuelve a entrar: define un PIN nuevo y ve los mismos datos
    conectado(servidor, true)
    abrirAplicacion()
    await iniciarSesion(u)
    await definirPinEnPantalla(u, PIN_NUEVO)
    expect(await screen.findByText(/Hola, Vendedor Uno/)).toBeInTheDocument()
    await waitFor(async () => expect(await baseLocal.clientes.count()).toBe(2))
    expect(await baseLocal.meta.get('pin_hash')).toBeDefined()
  }, 240_000)
})
