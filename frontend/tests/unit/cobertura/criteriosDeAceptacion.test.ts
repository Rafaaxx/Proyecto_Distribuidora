/**
 * Change 28, tarea 7.3 (D15): mapa de cobertura de los 12 criterios de éxito de `00` §9. Spec
 * `sistema/aceptacion-etapa-1`, escenario «Un criterio sin prueba hace fallar la verificación».
 * Regla: `02` §15 (punta a punta: criterios de `00` §9).
 */
import { existsSync, readFileSync } from 'node:fs'
import path from 'node:path'

import { describe, expect, it } from 'vitest'

import { CRITERIOS, criteriosSinPrueba, type Criterio } from '../../e2e/criterios'

const RAIZ = path.resolve(import.meta.dirname, '..', '..', '..', '..')

const completos: Criterio[] = Array.from({ length: 12 }, (_, i) => ({
  numero: i + 1,
  titulo: `criterio ${String(i + 1)}`,
  archivos: ['existe.ts'],
}))

describe('criteriosSinPrueba', () => {
  it('no informa nada cuando los 12 criterios tienen un archivo que existe', () => {
    expect(criteriosSinPrueba(completos, () => true)).toEqual([])
  })

  it('nombra el criterio que falta en la lista', () => {
    const sinElSiete = completos.filter((c) => c.numero !== 7)
    expect(criteriosSinPrueba(sinElSiete, () => true)).toEqual([7])
  })

  it('nombra el criterio cuyo archivo no existe', () => {
    const existe = (archivo: string) => archivo !== 'falta.ts'
    const conArchivoQueFalta = completos.map((c) => (c.numero === 3 ? { ...c, archivos: ['falta.ts'] } : c))
    expect(criteriosSinPrueba(conArchivoQueFalta, existe)).toEqual([3])
  })

  it('nombra el criterio sin ningún archivo, y varios a la vez en orden', () => {
    const rotos = completos.map((c) => (c.numero === 9 || c.numero === 2 ? { ...c, archivos: [] } : c))
    expect(criteriosSinPrueba(rotos, () => true)).toEqual([2, 9])
  })

  it('con un criterio con dos archivos exige que existan los dos', () => {
    const dos = completos.map((c) => (c.numero === 12 ? { ...c, archivos: ['a.py', 'b.py'] } : c))
    expect(criteriosSinPrueba(dos, (a) => a !== 'b.py')).toEqual([12])
  })
})

describe('mapa real de criterios de `00` §9', () => {
  it('lista los 12 criterios, del 1 al 12, sin repetir', () => {
    expect(CRITERIOS.map((c) => c.numero)).toEqual([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12])
  })

  it('cada criterio tiene un archivo de prueba que existe en el repositorio', () => {
    expect(criteriosSinPrueba(CRITERIOS, (archivo) => existsSync(path.join(RAIZ, archivo)))).toEqual([])
  })

  it('el criterio 12 se cubre con las pruebas de restauración de backups (D15)', () => {
    const doce = CRITERIOS.find((c) => c.numero === 12)
    expect(doce?.archivos).toEqual([
      'backend/tests/infra/test_restauracion.py',
      'backend/tests/infra/test_prueba_restauracion.py',
    ])
  })

  it('el archivo de cada criterio de la suite lo nombra por su número', () => {
    for (const criterio of CRITERIOS.filter((c) => c.numero <= 11)) {
      const archivo = criterio.archivos[0] ?? ''
      const texto = readFileSync(path.join(RAIZ, archivo), 'utf-8')
      expect(texto, archivo).toMatch(new RegExp(`Criterio ${String(criterio.numero)} —`))
    }
  })
})
