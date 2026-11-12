/**
 * Change 20b, tarea 10.3 (D15): `useVendedoresElegibles` lee `GET /clientes/vendedores`
 * (`GESTIONAR_CLIENTES`), sin `ADMIN_USUARIOS`. Sin ese permiso no pide nada y queda `sin-acceso`.
 */

import { QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }))
vi.mock('../../../../src/lib/api/httpClient', () => ({ apiFetch: apiFetchMock }))

import { useVendedoresElegibles } from '../../../../src/features/clientes/useVendedores'
import { enrutar, llamadas } from '../../utils/enrutarApi'
import { queryClientConYo } from '../../utils/permisosDePrueba'

const ANA = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'

function montar(permisos: string[]) {
  const cliente = queryClientConYo('GES', { permisos } as never)
  const envoltorio = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={cliente}>{children}</QueryClientProvider>
  )
  return renderHook(() => useVendedoresElegibles(), { wrapper: envoltorio })
}

describe('useVendedoresElegibles (tarea 10.3)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
    enrutar(apiFetchMock, [
      { metodo: 'GET', ruta: '/clientes/vendedores', responder: () => ({ status: 200, cuerpo: [{ id: ANA, nombre: 'Ana' }] }) },
    ])
  })

  it('con GESTIONAR_CLIENTES y sin ADMIN_USUARIOS trae la lista del endpoint de clientes', async () => {
    const { result } = montar(['GESTIONAR_CLIENTES'])

    await waitFor(() => expect(result.current.estado).toBe('listo'))
    expect(result.current.vendedores).toEqual([{ id: ANA, nombre: 'Ana' }])
    expect(llamadas(apiFetchMock, 'GET', '/identidad/usuarios')).toHaveLength(0)
    expect(llamadas(apiFetchMock, 'GET', '/identidad/roles')).toHaveLength(0)
  })

  it('sin GESTIONAR_CLIENTES queda sin-acceso y no pide nada', async () => {
    const { result } = montar(['ADMIN_USUARIOS'])

    expect(result.current).toEqual({ vendedores: [], estado: 'sin-acceso' })
    expect(llamadas(apiFetchMock, 'GET', '/clientes/vendedores')).toHaveLength(0)
  })
})
