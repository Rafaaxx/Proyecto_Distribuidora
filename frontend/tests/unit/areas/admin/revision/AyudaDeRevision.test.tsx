import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }))
vi.mock('../../../../../src/lib/api/httpClient', () => ({ apiFetch: apiFetchMock }))

import { RevisionArea } from '../../../../../src/areas/admin/revision/RevisionArea'
import { AvisoDeRechazosPendientes } from '../../../../../src/areas/admin/stock/AvisoDeRechazosPendientes'
import { queryClientConYo } from '../../../utils/permisosDePrueba'
import { CUARENTENA_ID, montarApi, operacion, pagina, rechazo } from './revisionDePrueba'

/**
 * Change 25, tarea 18.1 (spec `sistema/ayuda-contextual`, «Ayuda de la bandeja», «Ayuda de las
 * rechazadas», «Ayuda de las rechazadas de la jornada»; D13; cita SYN-08, SYN-06, RUT-05, ADR-051):
 * las claves de ayuda están cableadas en las pantallas de la revisión y en el aviso de la jornada.
 */
function renderRevision(ruta: string) {
  const cliente = queryClientConYo('GES', { permisos: ['REVISAR_OBSERVACIONES', 'VENDER', 'REGISTRAR_COBRANZA'] } as never)
  return render(
    <QueryClientProvider client={cliente}>
      <MemoryRouter initialEntries={[ruta]}>
        <Routes>
          <Route path="/admin/revision/*" element={<RevisionArea />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

const reglaDeObservaciones = {
  metodo: 'GET',
  ruta: '/observaciones',
  responder: () => ({ status: 200, cuerpo: pagina([operacion()]) }),
}
const reglaDeRechazos = (items: unknown[]) => ({
  metodo: 'GET',
  ruta: '/observaciones/rechazos',
  responder: () => ({ status: 200, cuerpo: pagina(items) }),
})

describe('ayuda en las pantallas de revisión (tarea 18.1)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
  })

  it('las pestañas «Observaciones» y «Rechazadas» tienen su ayuda', async () => {
    montarApi(apiFetchMock, [reglaDeObservaciones])
    renderRevision('/admin/revision')

    const nav = await screen.findByRole('navigation', { name: 'Pestañas de revisión' })
    expect(within(nav).getByRole('button', { name: 'Ayuda: Observaciones' })).toBeInTheDocument()
    expect(within(nav).getByRole('button', { name: 'Ayuda: Rechazadas' })).toBeInTheDocument()
  })

  it('al abrir la ayuda de la bandeja se lee que resolver no cambia la operación', async () => {
    montarApi(apiFetchMock, [reglaDeObservaciones])
    renderRevision('/admin/revision')

    await userEvent.click(await screen.findByRole('button', { name: 'Ayuda: Observaciones' }))
    expect(screen.getByText(/La operación ya vale y revisarla no la cambia/)).toBeInTheDocument()
  })

  it('el diálogo de resolución de avisos tiene la ayuda «Resolver»', async () => {
    montarApi(apiFetchMock, [reglaDeObservaciones])
    renderRevision('/admin/revision')
    const usuario = userEvent.setup()

    await screen.findByText('Venta 0001-00000012')
    await usuario.click(screen.getAllByRole('checkbox', { name: /^Elegir aviso/ })[0] as HTMLElement)
    await usuario.click(screen.getByRole('button', { name: 'Resolver 1 aviso' }))
    const dialogo = await screen.findByRole('dialog')

    expect(within(dialogo).getByRole('button', { name: 'Ayuda: Resolver' })).toBeInTheDocument()
  })

  it('«Rechazadas»: el diálogo de resolución tiene «Resolver» y «Vincular con» con su ayuda', async () => {
    montarApi(apiFetchMock, [reglaDeRechazos([rechazo()])])
    renderRevision('/admin/revision/rechazadas')
    const usuario = userEvent.setup()

    await screen.findByText('Kiosco La Esquina')
    await usuario.click(screen.getByRole('button', { name: 'Resolver' }))
    const dialogo = await screen.findByRole('dialog')

    expect(within(dialogo).getByRole('button', { name: 'Ayuda: Resolver' })).toBeInTheDocument()
    expect(within(dialogo).getByRole('button', { name: 'Ayuda: Vincular con' })).toBeInTheDocument()
  })

  it('«Teléfono dado de baja» tiene su ayuda y un rechazo común no', async () => {
    montarApi(apiFetchMock, [
      reglaDeRechazos([
        rechazo({ origen: 'CUARENTENA', id: CUARENTENA_ID, tipo: 'VENTA_CONFIRMAR', codigo: null }),
        rechazo(),
      ]),
    ])
    renderRevision('/admin/revision/rechazadas')

    await screen.findAllByText('Kiosco La Esquina')
    expect(screen.getAllByRole('button', { name: 'Ayuda: Teléfono dado de baja' })).toHaveLength(1)
  })
})

describe('ayuda del aviso de la jornada (tarea 18.1)', () => {
  function renderAviso(permisos: string[]) {
    const cliente = queryClientConYo('GES', { permisos } as never)
    return render(
      <QueryClientProvider client={cliente}>
        <MemoryRouter>
          <AvisoDeRechazosPendientes cantidad={2} jornadaId="j-1" />
        </MemoryRouter>
      </QueryClientProvider>,
    )
  }

  it('lleva la ayuda «Rechazadas de la jornada», con y sin permiso de revisión', async () => {
    const con = renderAviso(['REVISAR_OBSERVACIONES'])
    expect(await screen.findByRole('button', { name: 'Ayuda: Rechazadas de la jornada' })).toBeInTheDocument()
    con.unmount()

    renderAviso(['RENDIR_JORNADA'])
    expect(await screen.findByRole('button', { name: 'Ayuda: Rechazadas de la jornada' })).toBeInTheDocument()
  })
})
