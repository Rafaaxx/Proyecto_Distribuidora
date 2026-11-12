import { describe, expect, it } from 'vitest'

import { esErrorDeCargaDeModulo } from '../../../src/lib/errorDeCargaDeModulo'

/**
 * Change 27a, D19: tras un despliegue nuevo los archivos con hash viejo desaparecen y quien tenga
 * la pestaña abierta falla al cargar una pantalla diferida. Cada navegador redacta distinto ese error.
 */
describe('esErrorDeCargaDeModulo', () => {
  it.each([
    ['Chrome / Edge', new TypeError('Failed to fetch dynamically imported module: https://x/assets/admin/Area-abc.js')],
    ['Safari', new TypeError('Importing a module script failed.')],
    ['Firefox', new TypeError('error loading dynamically imported module: https://x/a.js')],
    ['webpack / Vite antiguo', Object.assign(new Error('Loading chunk 7 failed.'), { name: 'ChunkLoadError' })],
  ])('reconoce el error de %s', (_navegador, error) => {
    expect(esErrorDeCargaDeModulo(error)).toBe(true)
  })

  it('ignora mayúsculas y minúsculas', () => {
    expect(esErrorDeCargaDeModulo(new Error('FAILED TO FETCH DYNAMICALLY IMPORTED MODULE'))).toBe(true)
  })

  it.each([
    ['un error común', new Error('Cannot read properties of undefined')],
    ['un fallo de red de la API', new TypeError('Failed to fetch')],
    ['un texto suelto', 'Importing a module script failed.'],
    ['null', null],
    ['undefined', undefined],
    ['un objeto sin mensaje', {}],
  ])('no confunde %s', (_nombre, error) => {
    expect(esErrorDeCargaDeModulo(error)).toBe(false)
  })
})
