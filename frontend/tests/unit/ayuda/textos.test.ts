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
  it('tiene las 32 claves aprobadas (27 del 16b y 5 de cobranzas; la de "Operador" se eliminó)', () => {
    expect(claves).toHaveLength(32)
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
      expect(id).toMatch(/^([A-Z]{2,3}-\d{2}|ADR-\d{3})$/)
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
  it('son exactamente cobranzas-observaciones, descuentos, topes y precio', () => {
    expect([...temas].sort()).toEqual(['cobranzas-observaciones', 'descuentos', 'precio', 'topes'])
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

describe('ayuda de cobranzas (change 17, D20; variante 5b)', () => {
  const clavesDeCobranzas = [
    'cobranzas.medios',
    'cobranzas.saldoAFavor',
    'cobranzas.jornada',
    'cobranzas.anulacion',
    'cobranzas.observaciones',
  ] as const

  it('las cinco claves existen y citan las reglas aprobadas', () => {
    expect(clavesDeCobranzas.map((clave) => [clave, [...AYUDAS[clave].reglas]])).toEqual([
      ['cobranzas.medios', ['COB-01', 'COB-02', 'INV-08']],
      ['cobranzas.saldoAFavor', ['COB-03', 'CC-04']],
      ['cobranzas.jornada', ['RUT-07']],
      ['cobranzas.anulacion', ['COB-05', 'CC-02']],
      ['cobranzas.observaciones', ['SYN-05', 'SYN-07', 'SYN-10', 'RUT-09']],
    ])
  })

  it.each([
    ['cobranzas.medios', '$30.000 en efectivo y $20.000 por transferencia (n.º 0042)'],
    ['cobranzas.saldoAFavor', 'debe $150.000 y paga $160.000 → le quedan $10.000 a favor'],
    ['cobranzas.jornada', 'Juan cobra $50.000 en Kiosco La Esquina desde la camioneta 2'],
    ['cobranzas.anulacion', 'un cheque de $20.000 de Almacén Don Pedro vuelve rechazado'],
  ] as const)('%s trae su ejemplo aprobado', (clave, fragmento) => {
    const entrada: { texto: string; ejemplo?: string } = AYUDAS[clave]
    expect(`${entrada.texto} ${entrada.ejemplo ?? ''}`).toContain(fragmento)
  })

  it('las observaciones quedan en un panel corto con "Ver más" al tema cobranzas-observaciones (5b)', () => {
    const entrada: { texto: string; verMas?: string } = AYUDAS['cobranzas.observaciones']
    expect(entrada.verMas).toBe('cobranzas-observaciones')
    expect(entrada.texto).toContain('porque la plata ya se cobró')
    expect(entrada.texto.split('.').length).toBeLessThanOrEqual(4)
  })

  it('el tema explica las cinco marcas con su ejemplo y avisa que la bandeja llega más adelante', () => {
    const tema = TEMAS['cobranzas-observaciones']
    const titulos = tema.secciones.map((seccion) => seccion.titulo)

    expect(tema.titulo).toBe('Avisos de los pagos cargados sin señal')
    expect(titulos).toEqual(
      expect.arrayContaining(['Medio inactivo', 'Falta la referencia', 'Permiso revocado', 'Jornada liberada', 'Cliente no habilitado']),
    )
    const marcas = tema.secciones.filter((seccion) => seccion.titulo !== 'Por qué el pago se toma igual' && seccion.titulo !== 'Qué hacer con los avisos')
    expect(marcas).toHaveLength(5)
    for (const marca of marcas) {
      expect(marca.ejemplo?.startsWith('Ej.:')).toBe(true)
    }
    expect(tema.secciones.flatMap((seccion) => seccion.parrafos).join(' ')).toContain('La bandeja para darlos por revisados llega más adelante')
  })
})

describe('ClaveDeAyuda: el compilador rechaza una clave inexistente', () => {
  it('una clave mal escrita no compila (verificado por `npm run typecheck`)', () => {
    // @ts-expect-error `descuentos.medidda` no existe en AYUDAS
    const mala: ClaveDeAyuda = 'descuentos.medidda'
    expect(claves).not.toContain(mala)
  })
})
