import { describe, expect, it } from 'vitest'

import type { CodigoPermiso } from '../../../../src/domain/identidad/permisos'

/**
 * `design.md` D8-A (tarea 6.1): `CodigoPermiso` es una unión literal, no
 * `string` libre. Esta prueba es de tipos: no hay comportamiento en
 * tiempo de ejecución que ejercitar, así que se limita a comprobar que un
 * código real del catálogo de `01` §19 compila y que uno inexistente no
 * compila (`@ts-expect-error`, exigido por `npm run typecheck`).
 */
describe('CodigoPermiso (01 §19, D8-A, tarea 6.1)', () => {
  it('acepta un código real del catálogo', () => {
    const permiso: CodigoPermiso = 'GESTIONAR_CATALOGO'
    expect(permiso).toBe('GESTIONAR_CATALOGO')
  })

  it('rechaza en tiempo de compilación un código inexistente', () => {
    // @ts-expect-error 'PERMISO_INEXISTENTE' no está en el catálogo de `01` §19.
    const permiso: CodigoPermiso = 'PERMISO_INEXISTENTE'
    expect(permiso).toBe('PERMISO_INEXISTENTE')
  })
})
