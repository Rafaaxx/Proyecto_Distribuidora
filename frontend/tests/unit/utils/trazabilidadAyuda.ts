import { existsSync, readdirSync, readFileSync, statSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

/**
 * Auxiliares de la prueba de trazabilidad de la ayuda (change 16b, ADR-051, D10 = A punto 2).
 * Son funciones puras sobre texto, salvo `raizDelRepositorio` y `archivosTsx`, que leen disco.
 */
export interface UsoDeClave {
  archivo: string
  clave: string
}

/** Busca hacia arriba la carpeta que contiene `docs/01-dominio.md`. `undefined` si no está. */
export function raizDelRepositorio(): string | undefined {
  let actual = dirname(fileURLToPath(import.meta.url))
  for (;;) {
    if (existsSync(join(actual, 'docs', '01-dominio.md'))) {
      return actual
    }
    const padre = resolve(actual, '..')
    if (padre === actual) {
      return undefined
    }
    actual = padre
  }
}

export function archivosTsx(carpeta: string): string[] {
  const resultado: string[] = []
  for (const nombre of readdirSync(carpeta)) {
    const ruta = join(carpeta, nombre)
    if (statSync(ruta).isDirectory()) {
      resultado.push(...archivosTsx(ruta))
    } else if (nombre.endsWith('.tsx')) {
      resultado.push(ruta)
    }
  }
  return resultado
}

const ATRIBUTO = /\b(?:clave|ayuda)=(?:"([^"]+)"|\{([^}]*)\})/g
const LITERAL = /['"`]([^'"`]+)['"`]/g

/**
 * Claves usadas en `<Ayuda clave="x" />` y `ayuda="x"` (o `ayuda={cond ? 'a' : 'b'}`): toma los
 * literales de texto de cada atributo. `clave=` solo cuenta si el literal parece una clave de
 * ayuda (`area.concepto`), para no confundirse con otros atributos `clave`.
 */
export function clavesUsadas(codigo: string, archivo: string): UsoDeClave[] {
  const usos: UsoDeClave[] = []
  for (const coincidencia of codigo.matchAll(ATRIBUTO)) {
    const crudos = coincidencia[1] !== undefined ? [coincidencia[1]] : [...coincidencia[2].matchAll(LITERAL)].map((m) => m[1])
    for (const crudo of crudos) {
      if (/^[a-z]+\.[A-Za-z]+$/.test(crudo)) {
        usos.push({ archivo, clave: crudo })
      }
    }
  }
  return usos
}

/** IDs de regla (`DSC-03`) que son primera columna de una tabla de `docs/01-dominio.md`. */
export function idsDeDominio(markdown: string): Set<string> {
  const ids = new Set<string>()
  for (const coincidencia of markdown.matchAll(/^\|\s*([A-Z]{3}-\d{2})\s*\|/gm)) {
    ids.add(coincidencia[1])
  }
  return ids
}

/** Números de ADR que existen como archivo `ADR-NNN-*.md`. */
export function idsDeAdr(nombres: readonly string[]): Set<string> {
  const ids = new Set<string>()
  for (const nombre of nombres) {
    const coincidencia = /^(ADR-\d{3})-.*\.md$/.exec(nombre)
    if (coincidencia) {
      ids.add(coincidencia[1])
    }
  }
  return ids
}

export function leerDominio(raiz: string): string {
  return readFileSync(join(raiz, 'docs', '01-dominio.md'), 'utf-8')
}

export function nombresDeAdr(raiz: string): string[] {
  return readdirSync(join(raiz, 'docs', 'adr'))
}
