import { readFileSync } from 'node:fs'
import { relative } from 'node:path'
import { describe, expect, it } from 'vitest'

import { AYUDAS, TEMAS } from '../../../src/ayuda/textos'
import {
  archivosTsx,
  clavesUsadas,
  idsDeAdr,
  idsDeDominio,
  leerDominio,
  nombresDeAdr,
  raizDelRepositorio,
} from '../utils/trazabilidadAyuda'

/**
 * Trazabilidad de la ayuda (spec `ayuda-contextual`, requisito "Todos los textos viven en un
 * único archivo" y escenarios "Clave inexistente" y "Una ayuda sin regla citada no pasa las
 * pruebas"; ADR-051, D10 = A punto 2).
 *
 * Lee `frontend/src` y `docs/` desde la raíz del repositorio. Si `docs/` no se encuentra, la
 * prueba FALLA con un mensaje claro: no se saltea.
 */
const raiz = raizDelRepositorio()

function raizObligatoria(): string {
  if (!raiz) {
    throw new Error(
      'No se encontró docs/01-dominio.md subiendo desde tests/unit/ayuda: la prueba de trazabilidad ' +
        'necesita el repositorio completo (corré las pruebas desde un checkout, no desde la imagen del frontend).',
    )
  }
  return raiz
}

function clavesFaltantes(usos: { archivo: string; clave: string }[]): string[] {
  return usos.filter((uso) => !(uso.clave in AYUDAS)).map((uso) => `${uso.archivo}: ${uso.clave}`)
}

function idsInexistentes(reglas: readonly string[], dominio: Set<string>, adr: Set<string>): string[] {
  return reglas.filter((id) => !dominio.has(id) && !adr.has(id))
}

describe('claves usadas en src', () => {
  // Escenario: "Trazabilidad"
  it('cada clave de <Ayuda clave> y de ayuda= existe en AYUDAS (nombra archivo y clave si no)', () => {
    const base = raizObligatoria()
    const usos = archivosTsx(`${base}/frontend/src`).flatMap((archivo) =>
      clavesUsadas(readFileSync(archivo, 'utf-8'), relative(base, archivo).replaceAll('\\', '/')),
    )

    expect(clavesFaltantes(usos)).toEqual([])
  })

  it('detecta una clave mal escrita y nombra archivo y clave', () => {
    const usos = clavesUsadas('<Campo ayuda="descuentos.medidda"><Ayuda clave="descuentos.medida" /></Campo>', 'X.tsx')

    expect(clavesFaltantes(usos)).toEqual(['X.tsx: descuentos.medidda'])
  })

  it('toma las dos claves de un ternario en ayuda={...}', () => {
    const usos = clavesUsadas("<Campo ayuda={iva ? 'costos.valorConIva' : 'costos.valorPagado'} />", 'Y.tsx')

    expect(usos.map((uso) => uso.clave)).toEqual(['costos.valorConIva', 'costos.valorPagado'])
  })

  it('hay pantallas que usan la ayuda (la prueba no pasa en vacío)', () => {
    const base = raizObligatoria()
    const usadas = archivosTsx(`${base}/frontend/src`).flatMap((archivo) =>
      clavesUsadas(readFileSync(archivo, 'utf-8'), archivo),
    )

    expect(usadas.length).toBeGreaterThan(0)
  })
})

describe('IDs de regla citados', () => {
  // Escenario: "Trazabilidad"
  it('cada ID de AYUDAS y de TEMAS existe en docs/01-dominio.md o como ADR en docs/adr', () => {
    const base = raizObligatoria()
    const dominio = idsDeDominio(leerDominio(base))
    const adr = idsDeAdr(nombresDeAdr(base))
    const citados = [
      ...Object.entries(AYUDAS).map(([clave, entrada]) => ({ origen: clave, reglas: entrada.reglas })),
      ...Object.entries(TEMAS).map(([tema, entrada]) => ({ origen: `tema ${tema}`, reglas: entrada.reglas })),
    ]

    const problemas = citados.flatMap(({ origen, reglas }) =>
      idsInexistentes(reglas, dominio, adr).map((id) => `${origen}: ${id}`),
    )

    expect(problemas).toEqual([])
  })

  it('un ID mal escrito (DSC-6) o inexistente (ADR-999) falla y se nombra', () => {
    const base = raizObligatoria()
    const dominio = idsDeDominio(leerDominio(base))
    const adr = idsDeAdr(nombresDeAdr(base))

    expect(idsInexistentes(['DSC-03', 'DSC-6', 'ADR-050', 'ADR-999'], dominio, adr)).toEqual(['DSC-6', 'ADR-999'])
  })

  it('idsDeDominio solo toma primeras columnas de tabla, no menciones en el texto', () => {
    const ids = idsDeDominio('| DSC-03 | La condición cita DSC-99 | 1 |\nTexto con DSC-77 suelto\n')

    expect([...ids]).toEqual(['DSC-03'])
  })
})
