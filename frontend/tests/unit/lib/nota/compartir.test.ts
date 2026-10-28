/**
 * Compartir y descargar la nota (change 20, tarea 3.1; ADR-008; `design.md` D9), con `navigator`
 * simulado.
 */
import { afterEach, describe, expect, it, vi } from 'vitest'

import { compartirNota, descargarNota, nombreDeArchivoDeNota, puedeCompartirArchivos } from '../../../../src/lib/nota/compartir'

const pdf = new Blob(['%PDF-1.7'], { type: 'application/pdf' })

function archivo(nombre = 'nota-de-venta-V03-000142.pdf'): File {
  return new File([pdf], nombre, { type: 'application/pdf' })
}

function simularNavegador(navegador: Partial<Navigator>): void {
  vi.stubGlobal('navigator', navegador)
}

afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

describe('nombreDeArchivoDeNota', () => {
  it('es nota-de-venta-{numero}.pdf', () => {
    expect(nombreDeArchivoDeNota('V03-000142')).toBe('nota-de-venta-V03-000142.pdf')
    expect(nombreDeArchivoDeNota('V01-000007')).toBe('nota-de-venta-V01-000007.pdf')
  })
})

describe('puedeCompartirArchivos', () => {
  it('es verdadero solo si el navegador tiene canShare y acepta el archivo', () => {
    const canShare = vi.fn(() => true)
    simularNavegador({ canShare })
    const a = archivo()
    expect(puedeCompartirArchivos(a)).toBe(true)
    expect(canShare).toHaveBeenCalledWith({ files: [a] })
  })

  it('es falso en un navegador sin canShare', () => {
    simularNavegador({})
    expect(puedeCompartirArchivos(archivo())).toBe(false)
  })

  it('es falso si canShare rechaza archivos', () => {
    simularNavegador({ canShare: vi.fn(() => false) })
    expect(puedeCompartirArchivos(archivo())).toBe(false)
  })
})

describe('compartirNota', () => {
  it('llama a share con el archivo nota-de-venta-V03-000142.pdf', async () => {
    const share = vi.fn(() => Promise.resolve())
    simularNavegador({ canShare: vi.fn(() => true), share })

    const resultado = await compartirNota(pdf, 'V03-000142')

    expect(resultado).toBe('compartida')
    const llamada = share.mock.calls[0] as unknown as [ShareData]
    expect(llamada[0].files).toHaveLength(1)
    expect(llamada[0].files?.[0]?.name).toBe('nota-de-venta-V03-000142.pdf')
    expect(llamada[0].files?.[0]?.type).toBe('application/pdf')
    expect(llamada[0].title).toBe('Nota de venta V03-000142')
  })

  it('una cancelación (AbortError) no es un error ni descarga', async () => {
    const share = vi.fn(() => Promise.reject(new DOMException('cancelada', 'AbortError')))
    simularNavegador({ canShare: vi.fn(() => true), share })
    const crear = vi.fn(() => 'blob:x')
    vi.stubGlobal('URL', { createObjectURL: crear, revokeObjectURL: vi.fn() })

    const resultado = await compartirNota(pdf, 'V03-000142')

    expect(resultado).toBe('cancelada')
    expect(crear).not.toHaveBeenCalled()
  })

  it('otro error se informa como fallo para ofrecer la descarga', async () => {
    const share = vi.fn(() => Promise.reject(new DOMException('sin permiso', 'NotAllowedError')))
    simularNavegador({ canShare: vi.fn(() => true), share })

    expect(await compartirNota(pdf, 'V03-000142')).toBe('fallo')
  })

  it('un error que no es de DOM también es fallo', async () => {
    simularNavegador({ canShare: vi.fn(() => true), share: vi.fn(() => Promise.reject(new Error('boom'))) })
    expect(await compartirNota(pdf, 'V01-000007')).toBe('fallo')
  })

  it('en un navegador sin canShare no comparte: devuelve fallo sin llamar a share', async () => {
    const share = vi.fn(() => Promise.resolve())
    simularNavegador({ share })
    expect(await compartirNota(pdf, 'V03-000142')).toBe('fallo')
    expect(share).not.toHaveBeenCalled()
  })

  it('en un navegador que rechaza archivos no comparte', async () => {
    const share = vi.fn(() => Promise.resolve())
    simularNavegador({ canShare: vi.fn(() => false), share })
    expect(await compartirNota(pdf, 'V03-000142')).toBe('fallo')
    expect(share).not.toHaveBeenCalled()
  })
})

describe('descargarNota', () => {
  it('descarga el PDF con el nombre nota-de-venta-{numero}.pdf', () => {
    const descargas: string[] = []
    vi.stubGlobal('URL', { createObjectURL: vi.fn(() => 'blob:nota'), revokeObjectURL: vi.fn() })
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {
      descargas.push(this.download)
    })

    descargarNota(pdf, 'V03-000142')
    descargarNota(pdf, 'V01-000007')

    expect(descargas).toEqual(['nota-de-venta-V03-000142.pdf', 'nota-de-venta-V01-000007.pdf'])
  })
})
