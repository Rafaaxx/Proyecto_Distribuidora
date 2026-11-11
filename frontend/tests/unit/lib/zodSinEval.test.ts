/**
 * Zod sin `eval` (change 28, Lote 4; D9; docs/02 §18). La política de contenido (CSP) de Caddy no
 * permite `unsafe-eval`. Zod 4 prueba si puede compilar validadores con `new Function("")`; el
 * navegador lo atrapa, pero igual lo informa como violación de la política (ruido en la consola
 * y falla de la suite de aceptación). Con `jitless` esa prueba no se hace.
 */
import { afterEach, describe, expect, it, vi } from 'vitest'

afterEach(() => {
  vi.unstubAllGlobals()
  vi.resetModules()
})

/** Reemplaza `Function` por un espía que anota cada texto con el que se lo construye. */
function espiarConstructorDeFunction(): string[] {
  const llamadas: string[] = []
  const Original = Function
  const Espia = function (...argumentos: string[]) {
    llamadas.push(argumentos.join(','))
    return Original(...argumentos)
  } as unknown as FunctionConstructor
  Espia.prototype = Original.prototype
  vi.stubGlobal('Function', Espia)
  return llamadas
}

describe('configuración de zod para una CSP sin unsafe-eval', () => {
  it('sin la configuración, zod prueba `new Function` al validar un objeto (la violación que hay que evitar)', async () => {
    const llamadas = espiarConstructorDeFunction()
    const { z } = await import('zod')

    z.object({ nombre: z.string() }).parse({ nombre: 'Ana' })

    expect(llamadas).toContain('')
  })

  it('con la configuración, validar objetos no construye funciones desde texto', async () => {
    const llamadas = espiarConstructorDeFunction()
    await import('../../../src/lib/zodSinEval')
    const { z } = await import('zod')

    const esquema = z.object({ nombre: z.string(), edad: z.number().int() })
    expect(esquema.parse({ nombre: 'Ana', edad: 30 })).toEqual({ nombre: 'Ana', edad: 30 })
    expect(esquema.safeParse({ nombre: 'Ana', edad: 'x' }).success).toBe(false)

    expect(llamadas).toEqual([])
  })
})
