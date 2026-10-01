import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }))
vi.mock('../../../../../src/lib/api/httpClient', () => ({ apiFetch: apiFetchMock }))

import ImportacionArea from '../../../../../src/areas/admin/importacion/ImportacionArea'
import { enrutar } from '../../../utils/enrutarApi'
import { queryClientConYo } from '../../../utils/permisosDePrueba'

describe('ruta de importación en /admin (change 10)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
    enrutar(apiFetchMock, [
      { ruta: '/importaciones', responder: () => ({ status: 200, cuerpo: { items: [], cursor_siguiente: null, zona_horaria: 'UTC' } }) },
    ])
  })
  afterEach(() => {
    vi.clearAllMocks()
  })

  it('/admin/importacion se resuelve a la pantalla de importación', async () => {
    render(
      <QueryClientProvider client={queryClientConYo('ADM')}>
        <MemoryRouter initialEntries={['/admin/importacion']}>
          <Routes>
            <Route path="/admin/importacion/*" element={<ImportacionArea />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    )

    expect(await screen.findByRole('button', { name: 'Descargar plantilla' })).toBeInTheDocument()
    expect(screen.getByText('Historial de importaciones', { selector: 'h2' })).toBeInTheDocument()
  })
})
