import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import { Campo } from '../../../src/components/ui/Field'

/** `Campo` con y sin ayuda (change 16b, `design.md` D8 = A, ADR-051). */
describe('Campo', () => {
  it('sin ayuda se ve como siempre: etiqueta asociada al control y sin botón (?)', () => {
    render(
      <Campo id="medida" etiqueta="Medida">
        <input id="medida" />
      </Campo>,
    )

    expect(screen.getByLabelText('Medida')).toBeInTheDocument()
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })

  it('con ayuda muestra el (?) fuera del label y la etiqueta sigue asociada al control', () => {
    render(
      <Campo id="medida" etiqueta="Medida" ayuda="descuentos.medida">
        <input id="medida" />
      </Campo>,
    )

    const boton = screen.getByRole('button', { name: 'Ayuda: Medida' })
    expect(boton.closest('label')).toBeNull()
    expect(screen.getByText('Medida').closest('label')).not.toBeNull()
    expect(screen.getByLabelText('Medida')).toBe(document.getElementById('medida'))
  })

  it('activar el botón no enfoca el control', async () => {
    const usuario = userEvent.setup()
    render(
      <Campo id="umbral" etiqueta="Umbral" ayuda="descuentos.umbral">
        <input id="umbral" />
      </Campo>,
    )

    await usuario.click(screen.getByRole('button', { name: 'Ayuda: Umbral' }))

    expect(screen.getByLabelText('Umbral')).not.toHaveFocus()
    expect(screen.getByText(/El número que hay que alcanzar/)).toBeVisible()
  })
})
