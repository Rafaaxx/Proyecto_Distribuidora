import { renderHook } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { useOperationIdDeEnvio } from '../../../../src/features/precios/useOperationIdDeEnvio'

/**
 * `Operation-Id` de un envío manual (INV-06, change 13 tarea 12.2): se conserva mientras el
 * contenido no cambia Y el envío no se completó (el reintento tras un error de red reenvía la
 * MISMA operación); cambia al cambiar el contenido y después de un envío completado (la
 * misma acción pedida otra vez es otra operación).
 */
describe('useOperationIdDeEnvio', () => {
  it('devuelve el mismo id mientras el contenido no cambia', () => {
    const { result } = renderHook(({ contenido }) => useOperationIdDeEnvio(contenido), {
      initialProps: { contenido: { listaId: 'a' } },
    })

    const primero = result.current.obtener()

    expect(primero).toBeTruthy()
    expect(result.current.obtener()).toBe(primero)
  })

  it('compara el contenido por valor, no por referencia', () => {
    const { result, rerender } = renderHook(({ contenido }) => useOperationIdDeEnvio(contenido), {
      initialProps: { contenido: { productoId: 'p', precio: '9000.00' } },
    })
    const primero = result.current.obtener()

    rerender({ contenido: { productoId: 'p', precio: '9000.00' } })

    expect(result.current.obtener()).toBe(primero)
  })

  it('genera uno nuevo cuando cambia el contenido', () => {
    const { result, rerender } = renderHook(({ contenido }) => useOperationIdDeEnvio(contenido), {
      initialProps: { contenido: { productoId: 'p', precio: '9000.00' } },
    })
    const primero = result.current.obtener()

    rerender({ contenido: { productoId: 'p', precio: '9100.00' } })

    expect(result.current.obtener()).not.toBe(primero)
  })

  it('genera uno nuevo tras completar el envío, aunque el contenido sea el mismo', () => {
    const { result } = renderHook(() => useOperationIdDeEnvio({ listaId: 'a' }))
    const primero = result.current.obtener()

    result.current.completar()

    expect(result.current.obtener()).not.toBe(primero)
  })

  it('un error no lo completa: el reintento reenvía el mismo id', () => {
    const { result } = renderHook(() => useOperationIdDeEnvio({ listaId: 'a' }))
    const primero = result.current.obtener()

    // (un envío que falló por la red no llama a `completar`)
    expect(result.current.obtener()).toBe(primero)
  })
})
