import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }))
vi.mock('../../../../src/lib/api/httpClient', () => ({ apiFetch: apiFetchMock }))

import { AvisoDeConsistencia } from '../../../../src/areas/admin/AvisoDeConsistencia'
import { AYUDAS } from '../../../../src/ayuda/textos'
import { queryClientConYo, type RolDePrueba } from '../../utils/permisosDePrueba'

function montar(rol: RolDePrueba) {
  return render(
    <QueryClientProvider client={queryClientConYo(rol)}>
      <MemoryRouter>
        <AvisoDeConsistencia />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

const MOMENTO = '2026-11-10T05:00:00Z'

const diferencia = (campos: Record<string, unknown>) => ({
  tipo: 'SALDO_CUENTA',
  cuenta_tipo: null,
  entidad_id: null,
  entidad_nombre: null,
  saldo_materializado: null,
  suma_del_libro: null,
  producto_id: null,
  producto_nombre: null,
  ubicacion_id: null,
  ubicacion_nombre: null,
  materializado: null,
  esperado: null,
  promedio_vigente: null,
  promedio_historia: null,
  ...campos,
})

const CON_DIFERENCIA_EN_UNA_CUENTA = {
  ejecutada_en: MOMENTO,
  resultado: 'CON_DIFERENCIAS',
  diferencias: [
    diferencia({
      cuenta_tipo: 'CLIENTE',
      entidad_nombre: 'Kiosco La Esquina',
      saldo_materializado: '31250.00',
      suma_del_libro: '1450.50',
    }),
    diferencia({ tipo: 'STOCK_SALDO', producto_nombre: 'Vino A', ubicacion_nombre: 'Depósito', materializado: 7, esperado: 5 }),
  ],
}

function responderCon(cuerpo: unknown) {
  apiFetchMock.mockImplementation(() => Promise.resolve({ ok: true, status: 200, json: async () => cuerpo }))
}

const llamadasALaConsistencia = () => apiFetchMock.mock.calls.filter(([ruta]) => ruta === '/sistema/consistencia')

/**
 * Change 28, tarea 3.2 (spec `sistema/verificacion-de-consistencia`, «El administrador ve el aviso», «Un usuario
 * sin el permiso no ve el aviso ni lee el resultado» y «El aviso desaparece cuando una corrida posterior no
 * encuentra diferencias»; D5, D17; SEG-06, ADR-015): el aviso del inicio de `/admin`.
 */
describe('AvisoDeConsistencia (tarea 3.2, D5, D17)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
  })

  it('con el permiso y diferencias muestra el momento de la corrida y el detalle de cada una', async () => {
    responderCon(CON_DIFERENCIA_EN_UNA_CUENTA)
    montar('ADM')

    const aviso = await screen.findByRole('alert')
    expect(within(aviso).getByText(/diferencias de consistencia/i)).toBeInTheDocument()
    expect(within(aviso).getByText(/Última verificación: \d{2}\/\d{2}\/\d{4} \d{2}:\d{2}/)).toBeInTheDocument()
    expect(
      within(aviso).getByText('Cuenta del cliente Kiosco La Esquina: saldo guardado $ 31.250,00, suma de sus movimientos $ 1.450,50.'),
    ).toBeInTheDocument()
    expect(within(aviso).getByText('Stock de Vino A en Depósito: guardado 7, según sus movimientos 5.')).toBeInTheDocument()
    expect(llamadasALaConsistencia()).toHaveLength(1)
  })

  it('Administración (con el permiso, sin ADMIN_CONFIGURACION) también lo ve', async () => {
    responderCon(CON_DIFERENCIA_EN_UNA_CUENTA)
    montar('GES')

    expect(await screen.findByRole('alert')).toBeInTheDocument()
  })

  it('trae su «(?)» con el texto aprobado y sin ejemplo', async () => {
    responderCon(CON_DIFERENCIA_EN_UNA_CUENTA)
    montar('ADM')
    const aviso = await screen.findByRole('alert')

    await userEvent.click(within(aviso).getByRole('button', { name: /Ayuda:/ }))

    expect(AYUDAS.consistenciaDiferencias.texto).toBe(
      'El sistema compara todas las noches los saldos de clientes, proveedores y stock con sus movimientos. Si no coinciden, hay un error del sistema: los saldos no se corrigen solos para no tapar el problema. Avisale a quien da soporte; mientras tanto se puede seguir operando.',
    )
    expect('ejemplo' in AYUDAS.consistenciaDiferencias).toBe(false)
    expect(await screen.findByText(/los saldos no se corrigen solos/)).toBeInTheDocument()
  })

  it('no ofrece ningún botón que modifique saldos (solo la ayuda)', async () => {
    responderCon(CON_DIFERENCIA_EN_UNA_CUENTA)
    montar('ADM')
    const aviso = await screen.findByRole('alert')

    const botones = within(aviso).getAllByRole('button')
    expect(botones.map((boton) => boton.getAttribute('aria-label') ?? boton.textContent)).toEqual([
      expect.stringMatching(/^Ayuda:/),
    ])
    expect(within(aviso).queryByRole('link')).not.toBeInTheDocument()
  })

  it('sin diferencias en la última corrida no muestra nada', async () => {
    responderCon({ ejecutada_en: MOMENTO, resultado: 'SIN_DIFERENCIAS', diferencias: [] })
    montar('ADM')

    await waitFor(() => {
      expect(llamadasALaConsistencia()).toHaveLength(1)
    })
    await waitFor(() => {
      expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    })
  })

  it('sin ninguna corrida todavía no muestra nada', async () => {
    responderCon({ ejecutada_en: null, resultado: null, diferencias: [] })
    montar('GES')

    await waitFor(() => {
      expect(llamadasALaConsistencia()).toHaveLength(1)
    })
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it.each<RolDePrueba>(['VEN', 'SUP', 'CON'])('un %s no ve el aviso y ni siquiera pide el resultado (SEG-06)', async (rol) => {
    responderCon(CON_DIFERENCIA_EN_UNA_CUENTA)
    montar(rol)

    await new Promise((resolver) => setTimeout(resolver, 20))
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(llamadasALaConsistencia()).toHaveLength(0)
  })

  it('si la consulta falla no afirma nada: no muestra el aviso', async () => {
    apiFetchMock.mockImplementation(() => Promise.resolve({ ok: false, status: 500, json: async () => ({}) }))
    montar('ADM')

    await waitFor(() => {
      expect(llamadasALaConsistencia().length).toBeGreaterThan(0)
    })
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })
})
