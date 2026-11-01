import 'fake-indexeddb/auto'

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { instalarCandadosDePrueba, type CandadosDePrueba } from '../../utils/candadosDePrueba'

/**
 * Change 22b, tarea 6.1 (spec `identidad/pin-de-autorizacion`, «Intentos simultáneos desde dos
 * pestañas», «El bloqueo llega mientras otra pestaña verifica», «Dos supervisores a la vez»;
 * `design.md` D9 = A; cita SEG-05, `02` §12.4). Dos «pestañas» = dos copias del módulo
 * (`vi.resetModules`), cada una con su conexión Dexie sobre la misma base de `fake-indexeddb`, con
 * derivación lenta simulada y `navigator.locks` de prueba con exclusión real compartida.
 */
const PIN_BUENO = '123456'
const PIN_MALO = '000000'
const PIN_COMPUERTA = '999999'
const HASH_BUENO = 'derivado:123456'
const USUARIO = 'u1'
const SUP01 = 'sup01'
const SUP02 = 'sup02'

const derivacion = {
  llamadas: 0,
  compuerta: null as Promise<void> | null,
}

vi.mock('../../../../src/lib/sesionLocal/derivacion', async (importarOriginal) => {
  const original = await importarOriginal<typeof import('../../../../src/lib/sesionLocal/derivacion')>()
  return {
    ...original,
    derivarPin: vi.fn(async (pin: string) => {
      derivacion.llamadas += 1
      if (pin === PIN_COMPUERTA && derivacion.compuerta !== null) await derivacion.compuerta
      // El correcto es más lento que el incorrecto para forzar la intercalación entre pestañas.
      await new Promise((resolver) => setTimeout(resolver, pin === PIN_BUENO ? 250 : 10))
      return `derivado:${pin}`
    }),
  }
})

type Resultado = { tipo: string; restantes?: number }
interface Pestana {
  intentar: (autorizadorId: string, pin: string) => Promise<Resultado>
  filas: () => Promise<{ fallos: number; bloqueado: boolean } | undefined>
  sembrar: () => Promise<void>
}

async function abrirPestana(): Promise<Pestana> {
  vi.resetModules()
  const { baseLocal } = await import('../../../../src/lib/dispositivo/db')
  const { verificarPinDeSupervisor } = await import('../../../../src/lib/sesionLocal/pinSupervisor')
  return {
    intentar: (autorizadorId, pin) =>
      verificarPinDeSupervisor({ usuarioId: USUARIO, autorizadorId, permisoRequerido: 'AUTORIZAR_DESCUENTO', pin }),
    filas: async () => {
      const fila = await baseLocal.intentos_pin.get([USUARIO, SUP01])
      return fila === undefined ? undefined : { fallos: fila.fallos, bloqueado: fila.bloqueado }
    },
    sembrar: async () => {
      await Promise.all(baseLocal.tables.map((t) => t.clear()))
      await baseLocal.configuracion.put({ clave: 'organizacion', intentos_pin_max: 5 } as never)
      await baseLocal.autorizadores.bulkPut(
        [SUP01, SUP02].map((id) => ({
          id,
          nombre: id,
          permisos: ['AUTORIZAR_DESCUENTO'],
          pin_hash: HASH_BUENO,
          pin_sal: 'aa',
          iteraciones: 1,
        })),
      )
    },
  }
}

function contar(resultados: Resultado[], tipo: string): number {
  return resultados.filter((r) => r.tipo === tipo).length
}

describe('PIN de supervisor entre pestañas (tarea 6.1; D9 = A; SEG-05, 02 §12.4)', () => {
  let candados: CandadosDePrueba | null = null

  beforeEach(() => {
    derivacion.llamadas = 0
    derivacion.compuerta = null
  })
  afterEach(() => {
    candados?.restaurar()
    candados = null
    Reflect.deleteProperty(window.navigator, 'locks')
  })

  describe('con Web Locks', () => {
    beforeEach(() => {
      candados = instalarCandadosDePrueba()
    })

    it('tres fallos simultáneos por pestaña con máximo 5: exactamente 5 fallos contados, 4 «incorrecto», el resto «bloqueado» y ninguna derivación más allá de la quinta', async () => {
      const a = await abrirPestana()
      const b = await abrirPestana()
      await a.sembrar()

      const resultados = await Promise.all([
        ...[1, 2, 3].map(() => a.intentar(SUP01, PIN_MALO)),
        ...[1, 2, 3].map(() => b.intentar(SUP01, PIN_MALO)),
      ])

      expect(await a.filas()).toEqual({ fallos: 5, bloqueado: true })
      expect(contar(resultados, 'incorrecto')).toBe(4)
      expect(contar(resultados, 'bloqueado')).toBe(2)
      expect(derivacion.llamadas).toBe(5)
    })

    it('el correcto que llega después del quinto fallo responde «bloqueado» y no verifica', async () => {
      const a = await abrirPestana()
      const b = await abrirPestana()
      await a.sembrar()

      const fallos = [1, 2, 3, 4, 5].map((i) => (i % 2 === 0 ? a : b).intentar(SUP01, PIN_MALO))
      const correcto = a.intentar(SUP01, PIN_BUENO)
      await Promise.all(fallos)

      expect(await correcto).toEqual({ tipo: 'bloqueado' })
      expect(derivacion.llamadas).toBe(5)
    })

    it('dos supervisores distintos no se esperan entre sí', async () => {
      const a = await abrirPestana()
      const b = await abrirPestana()
      await a.sembrar()
      let abrir!: () => void
      derivacion.compuerta = new Promise<void>((resolver) => {
        abrir = resolver
      })

      const lento = a.intentar(SUP01, PIN_COMPUERTA)
      const rapido = await b.intentar(SUP02, PIN_BUENO)

      expect(rapido).toEqual({ tipo: 'ok', autorizadorId: SUP02 })
      abrir()
      expect(await lento).toEqual({ tipo: 'incorrecto', restantes: 4 })
    })
  })

  describe('sin Web Locks (TRIANGULATE)', () => {
    beforeEach(() => {
      Object.defineProperty(window.navigator, 'locks', { configurable: true, value: undefined })
    })

    it('ningún fallo se pierde: 6 fallos simultáneos desde dos pestañas dejan 5 contados y bloqueado', async () => {
      const a = await abrirPestana()
      const b = await abrirPestana()
      await a.sembrar()

      const resultados = await Promise.all([
        ...[1, 2, 3].map(() => a.intentar(SUP01, PIN_MALO)),
        ...[1, 2, 3].map(() => b.intentar(SUP01, PIN_MALO)),
      ])

      expect(await a.filas()).toEqual({ fallos: 5, bloqueado: true })
      expect(contar(resultados, 'incorrecto')).toBe(4)
      expect(contar(resultados, 'bloqueado')).toBe(2)
    })

    it('toda derivación de más responde «bloqueado»: el correcto que termina después del bloqueo de otra pestaña no pasa', async () => {
      const a = await abrirPestana()
      const b = await abrirPestana()
      await a.sembrar()

      const correcto = a.intentar(SUP01, PIN_BUENO)
      const fallos: Resultado[] = []
      for (let i = 0; i < 5; i += 1) fallos.push(await b.intentar(SUP01, PIN_MALO))

      expect(fallos.at(-1)).toEqual({ tipo: 'bloqueado' })
      expect(await correcto).toEqual({ tipo: 'bloqueado' })
    })
  })
})
