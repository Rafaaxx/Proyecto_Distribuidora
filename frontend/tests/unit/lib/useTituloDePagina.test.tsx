import { render } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'

import { useTituloDePagina } from '../../../src/lib/useTituloDePagina'

function Pantalla({ titulo }: { titulo: string | null }) {
  useTituloDePagina(titulo)
  return null
}

describe('useTituloDePagina', () => {
  beforeEach(() => {
    document.title = 'Distribuidora'
  })
  afterEach(() => {
    document.title = ''
  })

  it('pone «{titulo} · Distribuidora» y restaura el título anterior al desmontar', () => {
    const { unmount } = render(<Pantalla titulo="Ventas" />)
    expect(document.title).toBe('Ventas · Distribuidora')

    unmount()
    expect(document.title).toBe('Distribuidora')
  })

  it('al cambiar el título lo reemplaza y al desmontar vuelve al original, no al intermedio', () => {
    const { rerender, unmount } = render(<Pantalla titulo="Ventas" />)
    rerender(<Pantalla titulo="Clientes" />)
    expect(document.title).toBe('Clientes · Distribuidora')

    unmount()
    expect(document.title).toBe('Distribuidora')
  })

  it('con título nulo no toca document.title', () => {
    render(<Pantalla titulo={null} />)
    expect(document.title).toBe('Distribuidora')
  })
})
