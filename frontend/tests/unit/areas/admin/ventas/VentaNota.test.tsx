/**
 * Change 20, tarea 7.2: la nota de venta en el detalle de una venta (spec `ventas/nota-de-venta`;
 * VTA-13, SEG-06, ADR-008, ADR-058, ADR-059; D6, D9, D14). La nota de una venta de modo C es una
 * respuesta fabricada: la confirmación rechaza ese modo hasta la etapa 4.
 */
import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { apiFetchMock, guardarArchivoMock, generarPdfMock } = vi.hoisted(() => ({
  apiFetchMock: vi.fn(),
  guardarArchivoMock: vi.fn(),
  generarPdfMock: vi.fn(),
}))
vi.mock('../../../../../src/lib/api/httpClient', () => ({ apiFetch: apiFetchMock }))
vi.mock('../../../../../src/lib/descarga', () => ({ guardarArchivo: guardarArchivoMock }))
vi.mock('../../../../../src/lib/nota/pdf', () => ({ generarPdfDeNota: generarPdfMock }))

import { VentaDetalleScreen } from '../../../../../src/areas/admin/ventas/VentaDetalleScreen'
import { llamadas, type ReglaDeApi } from '../../../utils/enrutarApi'
import { queryClientConYo, type RolDePrueba } from '../../../utils/permisosDePrueba'
import { VENTA_ID, montarApi, notaDeVenta, ventaDetalle } from './ventasDePrueba'

function renderPantalla(rol: RolDePrueba) {
  return render(
    <QueryClientProvider client={queryClientConYo(rol)}>
      <MemoryRouter initialEntries={[`/admin/ventas/${VENTA_ID}`]}>
        <Routes>
          <Route path="/admin/ventas/:ventaId" element={<VentaDetalleScreen />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

function detalle(campos: Partial<Record<string, unknown>> = {}): ReglaDeApi {
  return { metodo: 'GET', ruta: `/ventas/${VENTA_ID}`, responder: () => ({ status: 200, cuerpo: ventaDetalle(campos) }) }
}

function nota(campos: Partial<Record<string, unknown>> = {}, status = 200): ReglaDeApi {
  return {
    metodo: 'GET',
    ruta: `/ventas/${VENTA_ID}/nota`,
    responder: () => ({ status, cuerpo: status === 200 ? notaDeVenta(campos) : { title: 'Falla', codigo: 'ERROR' } }),
  }
}

const PDF = new Blob(['%PDF-1.7'], { type: 'application/pdf' })

function simularNavegador(compartir: { canShare?: (datos: ShareData) => boolean; share?: (datos: ShareData) => Promise<void> }) {
  Object.defineProperty(navigator, 'canShare', { value: compartir.canShare, configurable: true, writable: true })
  Object.defineProperty(navigator, 'share', { value: compartir.share, configurable: true, writable: true })
}

describe('Nota de venta en el detalle (7.2)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
    guardarArchivoMock.mockReset()
    generarPdfMock.mockReset()
    generarPdfMock.mockResolvedValue(PDF)
    simularNavegador({})
  })
  afterEach(() => {
    vi.clearAllMocks()
  })

  it('"Descargar nota" genera el PDF y lo guarda con el nombre de la venta; sin soporte no hay "Compartir nota" (D9, ADR-008)', async () => {
    montarApi(apiFetchMock, [detalle(), nota()])
    const usuario = userEvent.setup()
    renderPantalla('SUP')

    await usuario.click(await screen.findByRole('button', { name: /^descargar nota$/i }))

    expect(guardarArchivoMock).toHaveBeenCalledWith(PDF, 'nota-de-venta-V01-000042.pdf')
    expect(screen.queryByRole('button', { name: /^compartir nota$/i })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /ayuda: nota de venta/i })).toBeInTheDocument()
  })

  it('con un navegador que comparte archivos muestra "Compartir nota" y comparte el PDF (D9)', async () => {
    const share = vi.fn().mockResolvedValue(undefined)
    simularNavegador({ canShare: () => true, share })
    montarApi(apiFetchMock, [detalle(), nota()])
    const usuario = userEvent.setup()
    renderPantalla('VEN')

    await usuario.click(await screen.findByRole('button', { name: /^compartir nota$/i }))

    expect(share).toHaveBeenCalledTimes(1)
    const datos = share.mock.calls[0]?.[0] as ShareData
    expect(datos.files?.[0]?.name).toBe('nota-de-venta-V01-000042.pdf')
    expect(guardarArchivoMock).not.toHaveBeenCalled()
    expect(screen.queryByRole('button', { name: /ayuda: compartir o descargar/i })).not.toBeInTheDocument()
  })

  it('si compartir falla avisa y deja la descarga; si el usuario cancela no avisa nada', async () => {
    const share = vi
      .fn()
      .mockRejectedValueOnce(new DOMException('no', 'NotAllowedError'))
      .mockRejectedValueOnce(new DOMException('cancelado', 'AbortError'))
    simularNavegador({ canShare: () => true, share })
    montarApi(apiFetchMock, [detalle(), nota()])
    const usuario = userEvent.setup()
    renderPantalla('VEN')

    await usuario.click(await screen.findByRole('button', { name: /^compartir nota$/i }))
    expect(await screen.findByText(/no se pudo compartir la nota/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /^descargar nota$/i })).toBeInTheDocument()

    await usuario.click(screen.getByRole('button', { name: /^compartir nota$/i }))
    expect(screen.queryByText(/no se pudo compartir la nota/i)).not.toBeInTheDocument()
  })

  it('un error de lectura muestra el aviso y "Reintentar" sin perder la venta; reintentar trae la nota', async () => {
    montarApi(apiFetchMock, [detalle(), nota({}, 500)])
    const usuario = userEvent.setup()
    renderPantalla('VEN')

    expect(await screen.findByText(/no se pudo preparar la nota de venta/i)).toBeInTheDocument()
    expect(screen.getByTestId('total-de-la-venta')).toHaveTextContent('$ 31.250,00')
    expect(screen.queryByRole('button', { name: /^descargar nota$/i })).not.toBeInTheDocument()

    montarApi(apiFetchMock, [detalle(), nota()])
    await usuario.click(screen.getByRole('button', { name: /^reintentar$/i }))

    expect(await screen.findByRole('button', { name: /^descargar nota$/i })).toBeInTheDocument()
    expect(screen.queryByText(/no se pudo preparar la nota de venta/i)).not.toBeInTheDocument()
  })

  it('un error al generar el PDF se avisa y no guarda nada', async () => {
    generarPdfMock.mockRejectedValue(new Error('pdfmake'))
    montarApi(apiFetchMock, [detalle(), nota()])
    const usuario = userEvent.setup()
    renderPantalla('SUP')

    await usuario.click(await screen.findByRole('button', { name: /^descargar nota$/i }))

    expect(await screen.findByText(/no se pudo generar el pdf/i)).toBeInTheDocument()
    expect(guardarArchivoMock).not.toHaveBeenCalled()
  })

  it('el detalle de una venta anulada ofrece la nota con su ayuda de anulada (D5, ADR-059)', async () => {
    montarApi(apiFetchMock, [
      detalle({ estado: 'ANULADA' }),
      nota({
        estado: 'ANULADA',
        anulacion: { anulada_en: '2026-10-21T10:00:00Z', motivo_nombre: 'Error de carga', devuelve_dinero: true },
      }),
    ])
    renderPantalla('SUP')

    expect(await screen.findByRole('button', { name: /^descargar nota$/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /ayuda: nota de una venta anulada/i })).toBeInTheDocument()
  })

  it('una venta vigente no muestra la ayuda de la nota anulada', async () => {
    montarApi(apiFetchMock, [detalle(), nota()])
    renderPantalla('SUP')

    await screen.findByRole('button', { name: /^descargar nota$/i })
    expect(screen.queryByRole('button', { name: /ayuda: nota de una venta anulada/i })).not.toBeInTheDocument()
  })

  it('una venta de modo C no ofrece Compartir ni Descargar y avisa que todavía no está disponible (D14)', async () => {
    simularNavegador({ canShare: () => true, share: vi.fn() })
    montarApi(apiFetchMock, [detalle({ modo_impositivo: 'C' }), nota({ modo_impositivo: 'C' })])
    renderPantalla('SUP')

    expect(
      await screen.findByText('La nota de venta todavía no está disponible para ventas con IVA incluido (modo C).'),
    ).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /descargar nota/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /compartir nota/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /reintentar/i })).not.toBeInTheDocument()
  })

  it('sin VENDER ni ANULAR_VENTA no se ve la nota y no se pide (SEG-06)', async () => {
    montarApi(apiFetchMock, [detalle(), nota()])
    renderPantalla('CON')

    expect(await screen.findByText(/no ten[eé]s permiso/i)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /descargar nota/i })).not.toBeInTheDocument()
    expect(llamadas(apiFetchMock, 'GET', `/ventas/${VENTA_ID}/nota`)).toHaveLength(0)
  })
})
