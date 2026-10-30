/**
 * Change 20c, tarea 14.2: las pestañas de Configuración se ofrecen según permiso (ADR-027;
 * "Fiscal" solo con `ADMIN_CONFIGURACION`, "Lista predeterminada" con cualquiera de
 * `ADMIN_CONFIGURACION`, `GESTIONAR_LISTAS` o `PUBLICAR_LISTAS`, igual que su GET) y la ruta
 * índice lleva a una pestaña que el usuario puede usar.
 */

import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }))
vi.mock('../../../../../src/lib/api/httpClient', () => ({ apiFetch: apiFetchMock }))

import ConfiguracionArea from '../../../../../src/areas/admin/configuracion/ConfiguracionArea'
import type { CodigoPermiso } from '../../../../../src/domain/identidad/permisos'
import { queryClientConYo, type RolDePrueba } from '../../../utils/permisosDePrueba'

function montar(rol: RolDePrueba, permisos?: CodigoPermiso[], ruta = '/admin/configuracion/inexistente') {
  const queryClient = queryClientConYo(rol, permisos ? { permisos } : {})
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[ruta]}>
        <Routes>
          <Route path="/admin/configuracion/*" element={<ConfiguracionArea />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

const ETIQUETAS = [
  'Fiscal',
  'Lista predeterminada',
  'Medios de pago',
  'Descuento y crédito',
  'Nota de venta',
  'Datos de la organización',
  'Motivos',
  'Alícuotas de IVA',
  'Redondeo por defecto',
]

function pestanas(): string[] {
  const nav = screen.queryByRole('navigation', { name: 'Secciones de configuración' })
  return nav ? Array.from(nav.querySelectorAll('a')).map((a) => a.textContent ?? '') : []
}

beforeEach(() => {
  apiFetchMock.mockReset()
  apiFetchMock.mockImplementation(() => new Promise(() => {}))
})

describe('pestañas de Configuración según permiso (14.2)', () => {
  it('el vendedor, sin ningún permiso de configuración ni de listas, no ve ninguna pestaña', () => {
    montar('VEN')
    expect(pestanas()).toEqual([])
    expect(screen.queryByRole('link', { name: 'Fiscal' })).toBeNull()
    expect(screen.queryByRole('link', { name: 'Lista predeterminada' })).toBeNull()
  })

  it('el supervisor tampoco ve pestañas', () => {
    montar('SUP')
    expect(pestanas()).toEqual([])
  })

  it('con solo GESTIONAR_LISTAS ve únicamente "Lista predeterminada"', () => {
    montar('GES', ['GESTIONAR_LISTAS'])
    expect(pestanas()).toEqual(['Lista predeterminada'])
  })

  it('con solo PUBLICAR_LISTAS ve únicamente "Lista predeterminada"', () => {
    montar('GES', ['PUBLICAR_LISTAS'])
    expect(pestanas()).toEqual(['Lista predeterminada'])
  })

  it('el rol Administración (GESTIONAR_LISTAS) no ve "Fiscal"', () => {
    montar('GES')
    expect(pestanas()).toEqual(['Lista predeterminada'])
  })

  it('el administrador ve todas las pestañas', () => {
    montar('ADM')
    expect(pestanas()).toEqual(ETIQUETAS)
  })

  it('con solo ADMIN_CONFIGURACION también ve "Fiscal" y "Lista predeterminada"', () => {
    montar('GES', ['ADMIN_CONFIGURACION'])
    expect(pestanas()).toEqual(ETIQUETAS)
  })
})

describe('ruta índice de Configuración (14.2)', () => {
  it('lleva a "Fiscal" al administrador', () => {
    montar('ADM', undefined, '/admin/configuracion')
    expect(screen.getByRole('link', { name: 'Fiscal' }).getAttribute('aria-current')).toBe('page')
  })

  it('lleva a "Lista predeterminada" a quien solo tiene permisos de listas', () => {
    montar('GES', undefined, '/admin/configuracion')
    expect(screen.getByRole('link', { name: 'Lista predeterminada' }).getAttribute('aria-current')).toBe('page')
  })

  it('lleva a "Lista predeterminada" a quien solo tiene PUBLICAR_LISTAS', () => {
    montar('GES', ['PUBLICAR_LISTAS'], '/admin/configuracion')
    expect(screen.getByRole('link', { name: 'Lista predeterminada' }).getAttribute('aria-current')).toBe('page')
  })
})
