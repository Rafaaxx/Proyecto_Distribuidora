import { render } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { conEnfasis } from '../../../src/ayuda/formato'

function html(texto: string) {
  const { container } = render(<p>{conEnfasis(texto)}</p>)
  return container.innerHTML
}

describe('conEnfasis', () => {
  it('**x** es negrita y *x* es cursiva', () => {
    expect(html('gana la **más descuento da**, *No acumulable*: una')).toBe(
      '<p>gana la <strong>más descuento da</strong>, <em>No acumulable</em>: una</p>',
    )
  })

  it('un texto sin marcas queda igual y el HTML se escapa', () => {
    expect(html('8 % y después 2 % <b>no</b>')).toBe('<p>8 % y después 2 % &lt;b&gt;no&lt;/b&gt;</p>')
  })
})
