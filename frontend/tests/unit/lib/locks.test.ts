import { afterEach, beforeEach, describe, expect, it } from 'vitest'

import { conCandado, conCandadoSiLibre } from '../../../src/lib/locks'
import { instalarCandadosDePrueba, type CandadosDePrueba } from '../utils/candadosDePrueba'

/**
 * Change 22b, tarea 1.1 (spec `sync/motor-de-sincronizacion`, «Una sola sincronización a la vez
 * en el teléfono»; `design.md` D2; cita `02` §13.3): envoltura de Web Locks con alternativa.
 */
function pausa() {
  let seguir!: () => void
  const espera = new Promise<void>((resolver) => {
    seguir = resolver
  })
  return { espera, seguir }
}

const turno = () => new Promise((resolver) => setTimeout(resolver, 0))

function pruebasDelContrato(descripcion: string, preparar: () => CandadosDePrueba | null) {
  describe(descripcion, () => {
    let candados: CandadosDePrueba | null = null
    beforeEach(() => {
      candados = preparar()
    })
    afterEach(() => {
      candados?.restaurar()
    })

    it('conCandado ejecuta en exclusión con el mismo nombre y en orden de pedido', async () => {
      const bitacora: string[] = []
      const primera = pausa()
      const a = conCandado('x', async () => {
        bitacora.push('a-entra')
        await primera.espera
        bitacora.push('a-sale')
      })
      await turno()
      const b = conCandado('x', async () => {
        bitacora.push('b-entra')
      })
      await turno()
      expect(bitacora).toEqual(['a-entra'])
      primera.seguir()
      await Promise.all([a, b])
      expect(bitacora).toEqual(['a-entra', 'a-sale', 'b-entra'])
    })

    it('nombres distintos no se bloquean entre sí', async () => {
      const primera = pausa()
      const a = conCandado('uno', () => primera.espera)
      const b = await conCandado('dos', async () => 'listo')
      expect(b).toBe('listo')
      primera.seguir()
      await a
    })

    it('conCandadoSiLibre con el candado tomado informa «ocupado» sin ejecutar la tarea', async () => {
      const primera = pausa()
      const a = conCandado('sync', () => primera.espera)
      await turno()
      let corrio = false
      const resultado = await conCandadoSiLibre('sync', async () => {
        corrio = true
        return 1
      })
      expect(resultado).toEqual({ obtenido: false })
      expect(corrio).toBe(false)
      primera.seguir()
      await a
    })

    it('conCandadoSiLibre libre ejecuta y devuelve el valor; se libera al terminar, aun con error', async () => {
      expect(await conCandadoSiLibre('sync', async () => 42)).toEqual({ obtenido: true, valor: 42 })
      await expect(
        conCandadoSiLibre('sync', async () => {
          throw new Error('falla')
        }),
      ).rejects.toThrow('falla')
      expect(await conCandadoSiLibre('sync', async () => 'otra vez')).toEqual({ obtenido: true, valor: 'otra vez' })
    })
  })
}

pruebasDelContrato('con navigator.locks', () => {
  const candados = instalarCandadosDePrueba()
  return candados
})

pruebasDelContrato('sin navigator.locks (candado de la pestaña)', () => {
  Object.defineProperty(window.navigator, 'locks', { configurable: true, value: undefined })
  return {
    pedidos: [],
    restaurar: () => {
      Reflect.deleteProperty(window.navigator, 'locks')
    },
  }
})

describe('uso del candado real del navegador', () => {
  it('con navigator.locks pide el nombre indicado', async () => {
    const candados = instalarCandadosDePrueba()
    try {
      await conCandadoSiLibre('distribuidora:sync', async () => undefined)
      expect(candados.pedidos).toEqual(['distribuidora:sync'])
    } finally {
      candados.restaurar()
    }
  })
})
