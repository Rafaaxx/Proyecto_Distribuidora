import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }))
vi.mock('../../../../../src/lib/api/httpClient', () => ({ apiFetch: apiFetchMock }))

import { ConfiguracionArea } from '../../../../../src/areas/admin/configuracion/ConfiguracionArea'
import { ConfiguracionFiscalScreen } from '../../../../../src/areas/admin/configuracion/ConfiguracionFiscalScreen'
import { llamadas, enrutar, type ReglaDeApi } from '../../../utils/enrutarApi'
import { queryClientConYo, type RolDePrueba } from '../../../utils/permisosDePrueba'

type Condicion = 'RESPONSABLE_INSCRIPTO' | 'MONOTRIBUTO' | 'EXENTO'

function fiscal(condicion: Condicion) {
  const computa = condicion === 'RESPONSABLE_INSCRIPTO'
  return {
    condicion_iva: condicion,
    computa_credito_fiscal: computa,
    modo_impositivo: computa ? 'B' : 'A',
    modalidad_iva_default: computa ? 'CLIENTE' : null,
  }
}

/** La organización guarda su condición: el POST la cambia y el GET siguiente la devuelve. */
function montarApi(
  inicial: Condicion,
  resumen = { con_credito_fiscal: 0, sin_credito_fiscal: 12 },
  extra: ReglaDeApi[] = [],
) {
  let actual = inicial
  enrutar(apiFetchMock, [
    ...extra,
    { metodo: 'GET', ruta: '/configuracion/fiscal', responder: () => ({ status: 200, cuerpo: fiscal(actual) }) },
    {
      metodo: 'GET',
      ruta: '/costos/resumen-regla-iva',
      responder: () => ({ status: 200, cuerpo: { fecha: '2026-10-03', ...resumen } }),
    },
    {
      metodo: 'POST',
      ruta: '/configuracion/fiscal/condicion-iva',
      responder: (_url, init) => {
        actual = (JSON.parse(String(init?.body)) as { condicion_iva: Condicion }).condicion_iva
        return { status: 200, cuerpo: fiscal(actual) }
      },
    },
  ])
}

function renderPantalla(rol: RolDePrueba = 'ADM') {
  return render(
    <QueryClientProvider client={queryClientConYo(rol)}>
      <MemoryRouter initialEntries={['/admin/configuracion/fiscal']}>
        <Routes>
          <Route path="/admin/configuracion/fiscal" element={<ConfiguracionFiscalScreen />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('ConfiguracionFiscalScreen (11b, tarea 7.4)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
  })
  afterEach(() => {
    vi.clearAllMocks()
  })

  it('sin ADMIN_CONFIGURACION muestra la condición vigente en solo lectura y no pide el resumen (ADR-027)', async () => {
    montarApi('MONOTRIBUTO')
    renderPantalla('VEN')

    expect(await screen.findByText('Monotributo', { selector: 'strong' })).toBeInTheDocument()
    expect(screen.getByText(/no computa crédito fiscal/i)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /cambiar condici[oó]n/i })).not.toBeInTheDocument()
    expect(screen.queryByLabelText(/nueva condici[oó]n/i)).not.toBeInTheDocument()
    expect(llamadas(apiFetchMock, 'GET', '/costos/resumen-regla-iva')).toHaveLength(0)
  })

  it('un inscripto muestra que computa crédito fiscal', async () => {
    montarApi('RESPONSABLE_INSCRIPTO')
    renderPantalla('VEN')

    expect(await screen.findByText('Responsable inscripto', { selector: 'strong' })).toBeInTheDocument()
    expect(screen.getByText(/computa crédito fiscal/i)).not.toHaveTextContent(/no computa/i)
  })

  it('con el permiso, elegir otra condición abre una confirmación: no es retroactivo y hay 12 costos para revisar; nada se envía todavía', async () => {
    montarApi('MONOTRIBUTO', { con_credito_fiscal: 0, sin_credito_fiscal: 12 })
    const usuario = userEvent.setup()
    renderPantalla()
    await screen.findByText('Monotributo', { selector: 'strong' })

    await usuario.selectOptions(screen.getByLabelText(/nueva condici[oó]n/i), 'RESPONSABLE_INSCRIPTO')
    await usuario.click(screen.getByRole('button', { name: /cambiar condici[oó]n/i }))

    const dialogo = await screen.findByRole('dialog')
    expect(within(dialogo).getByText(/no es retroactivo/i)).toBeInTheDocument()
    expect(await within(dialogo).findByText(/12 costos vigentes/i)).toBeInTheDocument()
    expect(llamadas(apiFetchMock, 'POST', '/configuracion/fiscal/condicion-iva')).toHaveLength(0)
  })

  it('al confirmar envía el comando con Operation-Id y la pantalla muestra la condición nueva', async () => {
    montarApi('MONOTRIBUTO')
    const usuario = userEvent.setup()
    renderPantalla()
    await screen.findByText('Monotributo', { selector: 'strong' })
    await usuario.selectOptions(screen.getByLabelText(/nueva condici[oó]n/i), 'RESPONSABLE_INSCRIPTO')
    await usuario.click(screen.getByRole('button', { name: /cambiar condici[oó]n/i }))
    const dialogo = await screen.findByRole('dialog')
    await within(dialogo).findByText(/12 costos vigentes/i)

    await usuario.click(within(dialogo).getByRole('button', { name: /confirmar cambio/i }))

    await waitFor(() => expect(llamadas(apiFetchMock, 'POST', '/configuracion/fiscal/condicion-iva')).toHaveLength(1))
    const llamada = llamadas(apiFetchMock, 'POST', '/configuracion/fiscal/condicion-iva')[0]
    expect(JSON.parse(String(llamada?.init.body))).toEqual({ condicion_iva: 'RESPONSABLE_INSCRIPTO' })
    expect(new Headers(llamada?.init.headers).get('Operation-Id')).toBeTruthy()
    expect(await screen.findByText('Responsable inscripto', { selector: 'strong' })).toBeInTheDocument()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('cancelar la confirmación no envía nada', async () => {
    montarApi('MONOTRIBUTO')
    const usuario = userEvent.setup()
    renderPantalla()
    await screen.findByText('Monotributo', { selector: 'strong' })
    await usuario.selectOptions(screen.getByLabelText(/nueva condici[oó]n/i), 'EXENTO')
    await usuario.click(screen.getByRole('button', { name: /cambiar condici[oó]n/i }))
    const dialogo = await screen.findByRole('dialog')

    await usuario.click(within(dialogo).getByRole('button', { name: /^cancelar$/i }))

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(llamadas(apiFetchMock, 'POST', '/configuracion/fiscal/condicion-iva')).toHaveLength(0)
  })

  it('pasar de inscripto a monotributo avisa cuántos costos se calcularon descontando IVA (3)', async () => {
    montarApi('RESPONSABLE_INSCRIPTO', { con_credito_fiscal: 3, sin_credito_fiscal: 0 })
    const usuario = userEvent.setup()
    renderPantalla()
    await screen.findByText('Responsable inscripto', { selector: 'strong' })

    await usuario.selectOptions(screen.getByLabelText(/nueva condici[oó]n/i), 'MONOTRIBUTO')
    await usuario.click(screen.getByRole('button', { name: /cambiar condici[oó]n/i }))

    expect(await within(await screen.findByRole('dialog')).findByText(/3 costos vigentes/i)).toBeInTheDocument()
  })

  it('sin costos para revisar lo dice y la confirmación sigue siendo no retroactiva', async () => {
    montarApi('MONOTRIBUTO', { con_credito_fiscal: 0, sin_credito_fiscal: 0 })
    const usuario = userEvent.setup()
    renderPantalla()
    await screen.findByText('Monotributo', { selector: 'strong' })

    await usuario.selectOptions(screen.getByLabelText(/nueva condici[oó]n/i), 'RESPONSABLE_INSCRIPTO')
    await usuario.click(screen.getByRole('button', { name: /cambiar condici[oó]n/i }))

    const dialogo = await screen.findByRole('dialog')
    expect(await within(dialogo).findByText(/no hay costos vigentes para revisar/i)).toBeInTheDocument()
    expect(within(dialogo).getByText(/no es retroactivo/i)).toBeInTheDocument()
  })

  it('el cambio al mismo valor no se ofrece: el botón queda deshabilitado', async () => {
    montarApi('MONOTRIBUTO')
    renderPantalla()
    await screen.findByText('Monotributo', { selector: 'strong' })

    expect(screen.getByLabelText(/nueva condici[oó]n/i)).toHaveValue('MONOTRIBUTO')
    expect(screen.getByRole('button', { name: /cambiar condici[oó]n/i })).toBeDisabled()
  })

  it('un rechazo del servidor se muestra y la condición vigente no cambia', async () => {
    montarApi('RESPONSABLE_INSCRIPTO', undefined, [
      {
        metodo: 'POST',
        ruta: '/configuracion/fiscal/condicion-iva',
        responder: () => ({
          status: 409,
          cuerpo: { title: 'El modo impositivo no es compatible.', codigo: 'MODO_IMPOSITIVO_INCOMPATIBLE' },
        }),
      },
    ])
    const usuario = userEvent.setup()
    renderPantalla()
    await screen.findByText('Responsable inscripto', { selector: 'strong' })
    await usuario.selectOptions(screen.getByLabelText(/nueva condici[oó]n/i), 'MONOTRIBUTO')
    await usuario.click(screen.getByRole('button', { name: /cambiar condici[oó]n/i }))
    const dialogo = await screen.findByRole('dialog')

    await usuario.click(within(dialogo).getByRole('button', { name: /confirmar cambio/i }))

    expect(await within(dialogo).findByText('El modo impositivo no es compatible.')).toBeInTheDocument()
    expect(screen.getByText('Responsable inscripto', { selector: 'strong' })).toBeInTheDocument()
  })
})

describe('ConfiguracionArea (11b, tarea 7.4)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
  })

  it('la ruta índice /admin/configuracion lleva a /admin/configuracion/fiscal', async () => {
    montarApi('MONOTRIBUTO')
    render(
      <QueryClientProvider client={queryClientConYo('ADM')}>
        <MemoryRouter initialEntries={['/admin/configuracion']}>
          <Routes>
            <Route path="/admin/configuracion/*" element={<ConfiguracionArea />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    )

    expect(await screen.findByRole('heading', { name: /configuraci[oó]n fiscal/i })).toBeInTheDocument()
  })
})
