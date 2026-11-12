import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { instalarCandadosDePrueba, type CandadosDePrueba } from '../../utils/candadosDePrueba'

/**
 * Change 22b, tarea 7.1 (spec `identidad/sesion-local`, «Las pestañas del teléfono no renuevan la
 * sesión a la vez»; `design.md` D11 = A; cita `02` §12.1, ADR-017). Un servidor simulado rota el
 * refresh token en cada uso y revoca la familia si llega uno ya rotado (como el real); la cookie
 * es del «navegador» y la comparten las dos «pestañas» (dos copias de los módulos). La cookie se
 * lee al ENVIAR y se reemplaza cuando LLEGA la respuesta, como un navegador.
 */
vi.mock('../../../../src/lib/dispositivo/dispositivoId', () => ({
  obtenerOGenerarDispositivoId: vi.fn(async () => 'dispositivo-de-prueba'),
}))

const servidor = {
  cookie: 'refresh-0',
  validoAhora: 'refresh-0',
  accesosValidos: new Set<string>(['access-0']),
  familiaRevocada: false,
  contador: 0,
  refrescos: 0,
}

function responder(status: number, cuerpo: unknown): Response {
  return new Response(JSON.stringify(cuerpo), { status, headers: { 'Content-Type': 'application/json' } })
}

/** `POST /auth/refresh` (rota y revoca ante reuso) y un recurso protegido por el access token. */
async function servidorSimulado(url: string, init: RequestInit): Promise<Response> {
  if (url.endsWith('/auth/refresh')) {
    servidor.refrescos += 1
    const presentado = servidor.cookie // el navegador lee la cookie al enviar
    if (servidor.familiaRevocada || presentado !== servidor.validoAhora) {
      servidor.familiaRevocada = true
      await new Promise((resolver) => setTimeout(resolver, 5))
      return responder(401, { codigo: 'SESION_REVOCADA' })
    }
    servidor.contador += 1
    const nuevoRefresh = `refresh-${servidor.contador}`
    const nuevoAccess = `access-${servidor.contador}`
    servidor.validoAhora = nuevoRefresh
    servidor.accesosValidos.add(nuevoAccess) // los access son JWT sin estado: los anteriores no se invalidan
    await new Promise((resolver) => setTimeout(resolver, 30)) // la respuesta tarda en llegar
    servidor.cookie = nuevoRefresh // Set-Cookie al llegar la respuesta
    return responder(200, { access_token: nuevoAccess })
  }
  const bearer = new Headers(init.headers).get('Authorization')
  return [...servidor.accesosValidos].some((t) => bearer === `Bearer ${t}`) ? responder(200, { ok: true }) : responder(401, { codigo: 'NO_AUTENTICADO' })
}

interface Pestana {
  renovarSesion: () => Promise<string>
  apiFetch: (ruta: string) => Promise<Response>
  fijarAccessToken: (token: string) => void
}

async function abrirPestana(): Promise<Pestana> {
  vi.resetModules()
  const http = await import('../../../../src/lib/api/httpClient')
  const store = await import('../../../../src/lib/auth/tokenStore')
  return { renovarSesion: http.renovarSesion, apiFetch: http.apiFetch, fijarAccessToken: store.fijarAccessToken }
}

describe('renovación de sesión entre pestañas (tarea 7.1; D11 = A; 02 §12.1, ADR-017)', () => {
  let candados: CandadosDePrueba | null = null

  beforeEach(() => {
    Object.assign(servidor, {
      cookie: 'refresh-0',
      validoAhora: 'refresh-0',
      accesosValidos: new Set<string>(['access-0']),
      familiaRevocada: false,
      contador: 0,
      refrescos: 0,
    })
    vi.stubGlobal('fetch', vi.fn(servidorSimulado))
  })
  afterEach(() => {
    vi.unstubAllGlobals()
    candados?.restaurar()
    candados = null
    Reflect.deleteProperty(window.navigator, 'locks')
  })

  describe('con Web Locks', () => {
    beforeEach(() => {
      candados = instalarCandadosDePrueba()
    })

    it('dos pestañas con el access vencido piden a la vez: renuevan en serie, las dos siguen con sesión y la familia no se revoca', async () => {
      const a = await abrirPestana()
      const b = await abrirPestana()
      a.fijarAccessToken('access-vencido')
      b.fijarAccessToken('access-vencido')

      const [ra, rb] = await Promise.all([a.apiFetch('/recurso'), b.apiFetch('/recurso')])

      expect(servidor.familiaRevocada).toBe(false)
      expect(ra.status).toBe(200)
      expect(rb.status).toBe(200)
      expect(servidor.refrescos).toBe(2)
      expect(candados?.pedidos.filter((n) => n === 'distribuidora:renovacion')).toHaveLength(2)
    })

    it('renovarSesion desde dos pestañas a la vez: las dos «renovada»', async () => {
      const a = await abrirPestana()
      const b = await abrirPestana()

      const resultados = await Promise.all([a.renovarSesion(), b.renovarSesion()])

      expect(resultados).toEqual(['renovada', 'renovada'])
      expect(servidor.familiaRevocada).toBe(false)
    })

    it('un reuso real de un refresh ya rotado sigue revocando la familia', async () => {
      const a = await abrirPestana()
      expect(await a.renovarSesion()).toBe('renovada') // refresh-0 queda rotado

      servidor.cookie = 'refresh-0' // alguien presenta el viejo desde fuera
      expect(await a.renovarSesion()).toBe('rechazada')

      expect(servidor.familiaRevocada).toBe(true)
      servidor.cookie = servidor.validoAhora // aun con el vigente, la familia ya no vive
      expect(await a.renovarSesion()).toBe('rechazada')
    })
  })

  describe('sin Web Locks (como hoy)', () => {
    beforeEach(() => {
      Object.defineProperty(window.navigator, 'locks', { configurable: true, value: undefined })
    })

    it('dentro de una pestaña la renovación sigue siendo una sola en vuelo', async () => {
      const a = await abrirPestana()

      const resultados = await Promise.all([a.renovarSesion(), a.renovarSesion()])

      expect(resultados).toEqual(['renovada', 'renovada'])
      expect(servidor.refrescos).toBe(1)
    })

    it('dos pestañas a la vez siguen chocando: el servidor revoca la familia (el riesgo que el candado evita)', async () => {
      const a = await abrirPestana()
      const b = await abrirPestana()

      await Promise.all([a.renovarSesion(), b.renovarSesion()])

      expect(servidor.familiaRevocada).toBe(true)
    })
  })
})
