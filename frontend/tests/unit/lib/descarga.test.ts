import { afterEach, describe, expect, it, vi } from 'vitest'

import { guardarArchivo } from '../../../src/lib/descarga'

describe('guardarArchivo', () => {
  afterEach(() => {
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  it('descarga el blob con el nombre dado y libera la URL temporal', () => {
    const crear = vi.fn(() => 'blob:fake')
    const liberar = vi.fn()
    vi.stubGlobal('URL', { createObjectURL: crear, revokeObjectURL: liberar })
    let descargado: { href: string; download: string } | null = null
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {
      descargado = { href: this.href, download: this.download }
    })
    const blob = new Blob(['a;b'], { type: 'text/csv' })

    guardarArchivo(blob, 'plantilla-clientes.csv')

    expect(crear).toHaveBeenCalledWith(blob)
    expect(descargado).toEqual({ href: 'blob:fake', download: 'plantilla-clientes.csv' })
    expect(liberar).toHaveBeenCalledWith('blob:fake')
    expect(document.querySelector('a[download]')).toBeNull()
  })

  it('con otro nombre y otro blob usa los suyos', () => {
    const crear = vi.fn(() => 'blob:otra')
    vi.stubGlobal('URL', { createObjectURL: crear, revokeObjectURL: vi.fn() })
    const nombres: string[] = []
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {
      nombres.push(this.download)
    })

    guardarArchivo(new Blob(['x']), 'otro.csv')

    expect(nombres).toEqual(['otro.csv'])
  })
})
