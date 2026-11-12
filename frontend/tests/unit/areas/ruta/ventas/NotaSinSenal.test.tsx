import 'fake-indexeddb/auto'

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({ generarPdfDeNota: vi.fn(), guardarArchivo: vi.fn() }))
vi.mock('../../../../../src/lib/nota/pdf', () => ({ generarPdfDeNota: mocks.generarPdfDeNota }))
vi.mock('../../../../../src/lib/descarga', () => ({ guardarArchivo: mocks.guardarArchivo }))

import { NotaSinSenal } from '../../../../../src/areas/ruta/ventas/NotaSinSenal'
import { baseLocal, type VentaLocal } from '../../../../../src/lib/dispositivo/db'
import { aplicarBootstrap } from '../../../../../src/sync/aplicarBootstrap'
import { bootstrapParaVender } from '../../../utils/datosParaVender'
import { sembrarVenta } from '../../../utils/sembrarVenta'

/**
 * Change 22a, tarea 12.2 (spec `ventas/nota-de-venta`; `design.md` D15; cita VTA-13, `00` §9
 * criterio 7): sin red, "Compartir nota" llama a Web Share con `nota-de-venta-<número>.pdf`;
 * cancelar no hace nada; una falla ofrece descargar. La nota sale de los datos congelados.
 */
const compartir = vi.fn()

function web(comparte: boolean) {
  Object.defineProperty(window.navigator, 'canShare', { configurable: true, value: comparte ? () => true : undefined })
  Object.defineProperty(window.navigator, 'share', { configurable: true, value: compartir })
}

async function ventaGuardada(): Promise<VentaLocal> {
  const venta = await baseLocal.ventas.get('venta-a')
  if (venta === undefined) throw new Error('falta la venta')
  return venta
}

describe('NotaSinSenal (tarea 12.2)', () => {
  beforeEach(async () => {
    mocks.generarPdfDeNota.mockReset().mockResolvedValue(new Blob(['pdf'], { type: 'application/pdf' }))
    mocks.guardarArchivo.mockReset()
    compartir.mockReset().mockResolvedValue(undefined)
    vi.spyOn(window.navigator, 'onLine', 'get').mockReturnValue(false)
    web(true)
    await Promise.all(baseLocal.tables.map((t) => t.clear()))
    await aplicarBootstrap(
      bootstrapParaVender((b) => {
        const c = b.clientes[0]
        if (c) c.razon_social = 'Almacén Uno SA'
      }),
    )
    await sembrarVenta('a')
  })

  afterEach(() => vi.restoreAllMocks())

  it('sin red, "Compartir nota" abre el menú de compartir con el archivo nota-de-venta-<número>.pdf', async () => {
    render(<NotaSinSenal venta={await ventaGuardada()} />)

    await userEvent.setup().click(screen.getByRole('button', { name: 'Compartir nota' }))

    await waitFor(() => expect(compartir).toHaveBeenCalledTimes(1))
    const datos = compartir.mock.calls[0]?.[0] as { files: File[]; title: string }
    expect(datos.files[0]?.name).toBe('nota-de-venta-0001-000008.pdf')
    expect(datos.title).toBe('Nota de venta 0001-000008')
  })

  it('si el usuario cierra el menú (cancelar) no pasa nada: sin aviso ni descarga', async () => {
    compartir.mockRejectedValue(new DOMException('cancelado', 'AbortError'))
    render(<NotaSinSenal venta={await ventaGuardada()} />)

    await userEvent.setup().click(screen.getByRole('button', { name: 'Compartir nota' }))

    await waitFor(() => expect(compartir).toHaveBeenCalled())
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(mocks.guardarArchivo).not.toHaveBeenCalled()
  })

  it('si compartir falla avisa y ofrece descargar la nota', async () => {
    compartir.mockRejectedValue(new Error('no se pudo'))
    render(<NotaSinSenal venta={await ventaGuardada()} />)
    const u = userEvent.setup()

    await u.click(screen.getByRole('button', { name: 'Compartir nota' }))

    expect(await screen.findByText('No se pudo compartir la nota. Podés descargarla y enviarla desde ahí.')).toBeInTheDocument()
    await u.click(screen.getByRole('button', { name: 'Descargar nota' }))
    await waitFor(() => expect(mocks.guardarArchivo).toHaveBeenCalledTimes(1))
    expect(mocks.guardarArchivo.mock.calls[0]?.[1]).toBe('nota-de-venta-0001-000008.pdf')
  })

  it('un bootstrap posterior que cambia la razón social no cambia la nota (VTA-13, ADR-059)', async () => {
    const u = userEvent.setup()
    await aplicarBootstrap(
      bootstrapParaVender((b) => {
        const c = b.clientes[0]
        if (c) c.razon_social = 'Otra Razón Social SRL'
      }),
    )
    render(<NotaSinSenal venta={await ventaGuardada()} />)

    await u.click(screen.getByRole('button', { name: 'Descargar nota' }))

    await waitFor(() => expect(mocks.generarPdfDeNota).toHaveBeenCalledTimes(1))
    const contenido = mocks.generarPdfDeNota.mock.calls[0]?.[0] as { cliente: { renglones: string[] }; saldo: { valor: string } | null }
    expect(contenido.cliente.renglones).toContain('Almacén Uno SA')
    expect(contenido.cliente.renglones).not.toContain('Otra Razón Social SRL')
  })

  it('sin Web Share con archivos no ofrece "Compartir nota"', async () => {
    web(false)
    render(<NotaSinSenal venta={await ventaGuardada()} />)

    expect(screen.queryByRole('button', { name: 'Compartir nota' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Descargar nota' })).toBeInTheDocument()
  })

  it('una falla al generar el PDF avisa y permite reintentar', async () => {
    mocks.generarPdfDeNota.mockRejectedValue(new Error('pdf'))
    render(<NotaSinSenal venta={await ventaGuardada()} />)

    await userEvent.setup().click(screen.getByRole('button', { name: 'Descargar nota' }))

    expect(await screen.findByText('No se pudo generar el PDF de la nota. Podés reintentar.')).toBeInTheDocument()
  })
})
