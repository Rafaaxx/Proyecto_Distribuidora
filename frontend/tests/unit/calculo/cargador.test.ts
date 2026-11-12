import { mkdtempSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

import { afterEach, beforeEach, describe, expect, it } from 'vitest'

import { CasoInvalidoError, descubrirCasos, DIRECTORIO_CASOS, SinCasosError } from './cargador'

let dirTemporal: string

beforeEach(() => {
  dirTemporal = mkdtempSync(join(tmpdir(), 'calculo-casos-'))
})

afterEach(() => {
  rmSync(dirTemporal, { recursive: true, force: true })
})

function escribir(nombre: string, contenido: unknown): string {
  const ruta = join(dirTemporal, nombre)
  writeFileSync(ruta, JSON.stringify(contenido), 'utf-8')
  return ruta
}

describe('descubrirCasos', () => {
  it('descubre un caso válido', () => {
    escribir('caso.json', {
      id: 'X-1',
      reglas: ['INV-03'],
      entrada: { a: 1 },
      salida_esperada: { b: 2 },
    })

    const casos = descubrirCasos(dirTemporal)

    expect(casos.map((c) => c.id)).toEqual(['X-1'])
  })

  it('descubre varios casos dentro de un archivo lista', () => {
    escribir('casos.json', [
      { id: 'A', reglas: [], entrada: {}, salida_esperada: {} },
      { id: 'B', reglas: [], entrada: {}, salida_esperada: {} },
    ])

    const casos = descubrirCasos(dirTemporal)

    expect(casos.map((c) => c.id).sort()).toEqual(['A', 'B'])
  })

  it.each(['id', 'reglas', 'entrada', 'salida_esperada'])(
    'falla nombrando archivo y campo si falta "%s"',
    (campoFaltante) => {
      const caso: Record<string, unknown> = {
        id: 'X-1',
        reglas: ['INV-03'],
        entrada: {},
        salida_esperada: {},
      }
      delete caso[campoFaltante]
      const ruta = escribir('invalido.json', caso)

      let error: unknown
      try {
        descubrirCasos(dirTemporal)
      } catch (e) {
        error = e
      }

      expect(error).toBeInstanceOf(CasoInvalidoError)
      expect((error as Error).message).toContain(ruta)
      expect((error as Error).message).toContain(campoFaltante)
    },
  )

  it('falla con un mensaje que nombra la ruta si el directorio no existe', () => {
    const inexistente = join(dirTemporal, 'no-existe')

    expect(() => descubrirCasos(inexistente)).toThrow(SinCasosError)
    expect(() => descubrirCasos(inexistente)).toThrow(inexistente)
  })

  it('falla si el directorio existe pero no tiene casos', () => {
    expect(() => descubrirCasos(dirTemporal)).toThrow(SinCasosError)
  })

  it('el directorio canónico del repo existe y tiene casos', () => {
    // Guardia de deriva: si esto falla, la suite de TypeScript no puede
    // descubrir ningún caso compartido.
    const casos = descubrirCasos(DIRECTORIO_CASOS)

    expect(casos.length).toBeGreaterThan(0)
  })
})
