import type { Mock } from 'vitest'

/**
 * Auxiliar de prueba (change 09, grupo 8): hace que el mock de `apiFetch`
 * responda según método y ruta, en vez de depender del orden de las llamadas (las
 * pantallas de stock hacen varias consultas en paralelo). Una regla sin método
 * responde a cualquiera; `responder` puede devolver `{ status, cuerpo }` o
 * lanzar (un corte de red).
 */
export interface ReglaDeApi {
  metodo?: string
  /** Ruta exacta (sin la cadena de consulta) o expresión regular sobre ella. */
  ruta: string | RegExp
  responder: (url: URL, init: RequestInit | undefined) => { status: number; cuerpo: unknown }
}

export function respuestaJson(status: number, cuerpo: unknown) {
  return { ok: status >= 200 && status < 300, status, json: async () => cuerpo }
}

export function enrutar(apiFetchMock: Mock, reglas: ReglaDeApi[]): void {
  apiFetchMock.mockImplementation((ruta: string, init?: RequestInit) => {
    const url = new URL(ruta, 'http://x')
    const metodo = (init?.method ?? 'GET').toUpperCase()
    const regla = reglas.find(
      (r) =>
        (r.metodo === undefined || r.metodo.toUpperCase() === metodo) &&
        (typeof r.ruta === 'string' ? r.ruta === url.pathname : r.ruta.test(url.pathname)),
    )
    if (!regla) {
      return Promise.resolve(respuestaJson(404, { title: `Sin regla para ${metodo} ${url.pathname}`, codigo: 'SIN_REGLA' }))
    }
    const { status, cuerpo } = regla.responder(url, init)
    return Promise.resolve(respuestaJson(status, cuerpo))
  })
}

/** Llamadas hechas con un método y una ruta exacta, en orden. */
export function llamadas(apiFetchMock: Mock, metodo: string, ruta: string | RegExp): { url: URL; init: RequestInit }[] {
  return (apiFetchMock.mock.calls as [string, RequestInit | undefined][])
    .map(([r, init]) => ({ url: new URL(r, 'http://x'), init: init ?? {} }))
    .filter(
      ({ url, init }) =>
        (init.method ?? 'GET').toUpperCase() === metodo.toUpperCase() &&
        (typeof ruta === 'string' ? ruta === url.pathname : ruta.test(url.pathname)),
    )
}
