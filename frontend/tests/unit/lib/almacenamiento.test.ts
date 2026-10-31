import { afterEach, describe, expect, it, vi } from 'vitest'

import { asegurarAlmacenamientoPersistente } from '../../../src/lib/almacenamiento'

/**
 * Change 21, tarea 12.1 (spec `sistema/aplicacion-instalable`, "Se pide almacenamiento
 * persistente"; `design.md` D18; `02` §13.3, `00` §11). Se pide tras el primer bootstrap y en cada
 * arranque mientras no esté concedido; negado o sin la API, el inicio advierte. Sin APIs solo de
 * Android: en Safari `navigator.storage` puede faltar o negar.
 */
function simularAlmacenamiento(storage: unknown) {
  vi.stubGlobal('navigator', { ...globalThis.navigator, storage })
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('almacenamiento persistente (tarea 12.1)', () => {
  it('ya concedido: no vuelve a pedirlo y no hay advertencia', async () => {
    const persist = vi.fn()
    simularAlmacenamiento({ persisted: vi.fn(async () => true), persist })

    expect(await asegurarAlmacenamientoPersistente()).toBe('concedido')
    expect(persist).not.toHaveBeenCalled()
  })

  it('no concedido todavía: lo pide y, si el navegador lo concede, no hay advertencia', async () => {
    const persist = vi.fn(async () => true)
    simularAlmacenamiento({ persisted: vi.fn(async () => false), persist })

    expect(await asegurarAlmacenamientoPersistente()).toBe('concedido')
    expect(persist).toHaveBeenCalledTimes(1)
  })

  it('el navegador lo niega: advierte, y el próximo arranque lo vuelve a pedir', async () => {
    const persist = vi.fn(async () => false)
    simularAlmacenamiento({ persisted: vi.fn(async () => false), persist })

    expect(await asegurarAlmacenamientoPersistente()).toBe('negado')
    expect(await asegurarAlmacenamientoPersistente()).toBe('negado')
    expect(persist).toHaveBeenCalledTimes(2)
  })

  it('concedido después (por ejemplo, al instalar la aplicación): la advertencia desaparece', async () => {
    const persisted = vi.fn(async () => false)
    simularAlmacenamiento({ persisted, persist: vi.fn(async () => false) })
    expect(await asegurarAlmacenamientoPersistente()).toBe('negado')

    persisted.mockResolvedValue(true)
    expect(await asegurarAlmacenamientoPersistente()).toBe('concedido')
  })

  it.each([undefined, {}, { persisted: undefined, persist: undefined }])(
    'sin la API (%j): advierte sin fallar',
    async (storage) => {
      simularAlmacenamiento(storage)
      expect(await asegurarAlmacenamientoPersistente()).toBe('no_disponible')
    },
  )

  it('si pedirlo falla, queda como negado y no rompe el arranque', async () => {
    simularAlmacenamiento({
      persisted: vi.fn(async () => false),
      persist: vi.fn(async () => {
        throw new Error('no permitido')
      }),
    })
    expect(await asegurarAlmacenamientoPersistente()).toBe('negado')
  })
})
