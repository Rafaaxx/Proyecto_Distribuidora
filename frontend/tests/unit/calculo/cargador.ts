/**
 * Cargador de casos de cálculo compartidos entre pytest y Vitest.
 *
 * Lee `shared/fixtures/calculo/*.json` con `fs` (entorno Node/jsdom, no a
 * través del grafo de módulos de Vite -- `design.md` D1), valida el formato
 * de caso de `docs/02-arquitectura.md` §10.4 (`id`, `reglas`, `entrada`,
 * `salida_esperada`) y falla nombrando el archivo y el campo faltante si un
 * caso está incompleto (spec `calculo-compartido`).
 *
 * La ruta al directorio de casos se resuelve desde este archivo hacia la
 * raíz del repo, nunca desde el directorio de trabajo, para que Vitest
 * funcione invocado desde cualquier lugar.
 */

import { readdirSync, readFileSync, statSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

// frontend/tests/unit/calculo/cargador.ts -> sube 3 niveles hasta la raíz
// del repo (calculo -> unit -> tests -> frontend -> raíz).
const __dirname = dirname(fileURLToPath(import.meta.url))
const REPO_ROOT = join(__dirname, '..', '..', '..', '..')
export const DIRECTORIO_CASOS = join(REPO_ROOT, 'shared', 'fixtures', 'calculo')

const CAMPOS_REQUERIDOS = ['id', 'reglas', 'entrada', 'salida_esperada'] as const

export class CasoInvalidoError extends Error {
  constructor(mensaje: string) {
    super(mensaje)
    this.name = 'CasoInvalidoError'
  }
}

export class SinCasosError extends Error {
  constructor(mensaje: string) {
    super(mensaje)
    this.name = 'SinCasosError'
  }
}

export interface CasoCalculo {
  id: string
  reglas: string[]
  entrada: Record<string, unknown>
  salida_esperada: Record<string, unknown>
  archivo: string
}

function validarCaso(bruto: unknown, archivo: string): CasoCalculo {
  if (typeof bruto !== 'object' || bruto === null) {
    throw new CasoInvalidoError(`${archivo}: cada caso debe ser un objeto JSON`)
  }

  const registro = bruto as Record<string, unknown>
  for (const campo of CAMPOS_REQUERIDOS) {
    if (!(campo in registro)) {
      throw new CasoInvalidoError(
        `${archivo}: falta el campo requerido '${campo}' en un caso de cálculo`,
      )
    }
  }

  return {
    id: registro['id'] as string,
    reglas: registro['reglas'] as string[],
    entrada: registro['entrada'] as Record<string, unknown>,
    salida_esperada: registro['salida_esperada'] as Record<string, unknown>,
    archivo,
  }
}

/**
 * Descubre y valida todos los casos del directorio dado (o del canónico).
 *
 * Un archivo puede contener un único objeto de caso o una lista de casos.
 * Lanza `SinCasosError` si el directorio no existe o no aporta ningún caso,
 * y `CasoInvalidoError` si algún caso no tiene los campos requeridos.
 */
export function descubrirCasos(directorio: string = DIRECTORIO_CASOS): CasoCalculo[] {
  let existe: boolean
  try {
    existe = statSync(directorio).isDirectory()
  } catch {
    existe = false
  }

  if (!existe) {
    throw new SinCasosError(
      `No existe el directorio de casos de cálculo compartidos: ${directorio}`,
    )
  }

  const casos: CasoCalculo[] = []
  const archivos = readdirSync(directorio)
    .filter((nombre) => nombre.endsWith('.json'))
    .sort()

  for (const nombre of archivos) {
    const ruta = join(directorio, nombre)
    const contenido = JSON.parse(readFileSync(ruta, 'utf-8')) as unknown
    const elementos = Array.isArray(contenido) ? contenido : [contenido]
    for (const elemento of elementos) {
      casos.push(validarCaso(elemento, ruta))
    }
  }

  if (casos.length === 0) {
    throw new SinCasosError(`No se descubrió ningún caso de cálculo compartido en ${directorio}`)
  }

  return casos
}
