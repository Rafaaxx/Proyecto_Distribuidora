import { describe, expect, it, vi } from 'vitest'

import { resolverOperationId, type EnvioPendiente } from '../../../../src/features/importacion/envio'

const archivo = () => new File(['x'], 'a.csv')

describe('resolverOperationId (INV-06, SYN-02)', () => {
  it('sin envío pendiente genera uno nuevo', () => {
    const generar = vi.fn(() => 'nuevo')

    expect(resolverOperationId(null, 'CLIENTES', archivo(), generar)).toBe('nuevo')
    expect(generar).toHaveBeenCalledTimes(1)
  })

  it('reutiliza el del pendiente si es el mismo tipo y el mismo archivo', () => {
    const f = archivo()
    const pendiente: EnvioPendiente = { tipo: 'CLIENTES', archivo: f, operationId: 'viejo' }
    const generar = vi.fn(() => 'nuevo')

    expect(resolverOperationId(pendiente, 'CLIENTES', f, generar)).toBe('viejo')
    expect(generar).not.toHaveBeenCalled()
  })

  it.each([
    ['otro archivo', 'CLIENTES', archivo()],
    ['otro tipo con el mismo archivo', 'PROVEEDORES', undefined],
  ])('genera uno nuevo con %s', (_nombre, tipo, otroArchivo) => {
    const f = archivo()
    const pendiente: EnvioPendiente = { tipo: 'CLIENTES', archivo: f, operationId: 'viejo' }

    expect(resolverOperationId(pendiente, tipo, otroArchivo ?? f, () => 'nuevo')).toBe('nuevo')
  })
})
