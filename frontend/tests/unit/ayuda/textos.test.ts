import { describe, expect, it } from 'vitest'

import { AYUDAS, TEMAS, type ClaveDeAyuda, type TemaDeAyuda } from '../../../src/ayuda/textos'

/**
 * Forma del archivo único de textos de ayuda (spec `ayuda-contextual`,
 * requisito "El texto es corto, trae un ejemplo y cita su regla"; ADR-051).
 * La existencia de cada ID en `docs/` la comprueba `trazabilidad.test.ts`.
 */
const claves = Object.keys(AYUDAS) as ClaveDeAyuda[]
const temas = Object.keys(TEMAS) as TemaDeAyuda[]

describe('AYUDAS: cada entrada tiene título, texto y regla citada', () => {
  it('tiene las 27 claves aprobadas (la de "Operador" se eliminó)', () => {
    expect(claves).toHaveLength(27)
    expect(claves).not.toContain('descuentos.operador')
  })

  it.each(claves)('%s: título y texto no vacíos', (clave) => {
    const entrada = AYUDAS[clave]
    expect(entrada.titulo.trim()).not.toBe('')
    expect(entrada.texto.trim()).not.toBe('')
  })

  it.each(claves)('%s: cita al menos un ID con formato de regla o ADR', (clave) => {
    const { reglas } = AYUDAS[clave]
    expect(reglas.length).toBeGreaterThan(0)
    for (const id of reglas) {
      expect(id).toMatch(/^([A-Z]{3}-\d{2}|ADR-\d{3})$/)
    }
  })

  it('todo "verMas" apunta a un tema de TEMAS', () => {
    const conVerMas = claves.filter((clave) => 'verMas' in AYUDAS[clave])
    expect(conVerMas.length).toBeGreaterThan(0)
    for (const clave of conVerMas) {
      const entrada: { verMas?: string } = AYUDAS[clave]
      expect(temas).toContain(entrada.verMas)
    }
  })

  it('el texto de "Medida" conserva el ejemplo aprobado de 2,5 cajas', () => {
    expect(AYUDAS['descuentos.medida'].texto).toContain('15 botellas de un vino que viene x6 = 2,5 cajas')
  })
})

describe('TEMAS: páginas "Ver más"', () => {
  it('son exactamente descuentos, topes y precio', () => {
    expect([...temas].sort()).toEqual(['descuentos', 'precio', 'topes'])
  })

  it.each(temas)('%s: título, al menos una sección con párrafos y al menos un ID', (tema) => {
    const entrada = TEMAS[tema]
    expect(entrada.titulo.trim()).not.toBe('')
    expect(entrada.reglas.length).toBeGreaterThan(0)
    expect(entrada.secciones.length).toBeGreaterThan(0)
    for (const seccion of entrada.secciones) {
      expect(seccion.titulo.trim()).not.toBe('')
      expect(seccion.parrafos.length).toBeGreaterThan(0)
    }
  })
})

describe('ClaveDeAyuda: el compilador rechaza una clave inexistente', () => {
  it('una clave mal escrita no compila (verificado por `npm run typecheck`)', () => {
    // @ts-expect-error `descuentos.medidda` no existe en AYUDAS
    const mala: ClaveDeAyuda = 'descuentos.medidda'
    expect(claves).not.toContain(mala)
  })
})
