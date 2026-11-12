import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { Ayuda } from '../../../src/components/ui/Ayuda'
import { Dialogo } from '../../../src/components/ui/Dialog'

/**
 * Componente `Ayuda` (change 16b, ADR-051, spec `ayuda-contextual`: requisitos "El botón de
 * ayuda se abre con clic, tap o teclado" y "La ayuda es accesible con lector de pantalla").
 * Se usan claves reales del archivo único de textos.
 */
function botonDe(titulo: string) {
  return screen.getByRole('button', { name: `Ayuda: ${titulo}` })
}

describe('Ayuda: botón accesible', () => {
  it('tiene nombre "Ayuda: <título>", arranca contraído y no muestra el panel', () => {
    render(<Ayuda clave="descuentos.medida" />)

    const boton = botonDe('Medida')
    expect(boton).toHaveAttribute('aria-expanded', 'false')
    expect(boton).toHaveAttribute('type', 'button')
    expect(screen.queryByText(/cajas equivalentes/i)).not.toBeInTheDocument()
  })

  it('el nombre sale del título de cada clave (no es fijo)', () => {
    render(<Ayuda clave="descuentos.tope" />)

    expect(botonDe('Tope de descuento')).toBeInTheDocument()
  })

  it('abierto, aria-controls apunta al panel y aria-expanded es true', async () => {
    const usuario = userEvent.setup()
    render(<Ayuda clave="descuentos.medida" />)

    await usuario.click(botonDe('Medida'))

    const boton = botonDe('Medida')
    expect(boton).toHaveAttribute('aria-expanded', 'true')
    const idPanel = boton.getAttribute('aria-controls')
    expect(idPanel).toBeTruthy()
    const panel = document.getElementById(idPanel as string)
    expect(panel).not.toBeNull()
    expect(panel).toHaveTextContent(/cajas equivalentes/i)
  })
})

describe('Ayuda: abrir', () => {
  it('con clic muestra el texto y el ejemplo', async () => {
    const usuario = userEvent.setup()
    render(<Ayuda clave="descuentos.acumulable" />)

    await usuario.click(botonDe('Acumulable'))

    expect(screen.getByText(/se suma a las demás/i)).toBeVisible()
    expect(screen.getByText(/8 % y después 2 % dan 9,84 %/)).toBeVisible()
  })

  it('con Enter y con Espacio abre y no envía el formulario que lo contiene', async () => {
    const usuario = userEvent.setup()
    const alEnviar = vi.fn((evento: React.FormEvent) => evento.preventDefault())
    render(
      <form onSubmit={alEnviar}>
        <Ayuda clave="descuentos.prioridad" />
      </form>,
    )

    botonDe('Prioridad').focus()
    await usuario.keyboard('{Enter}')
    expect(botonDe('Prioridad')).toHaveAttribute('aria-expanded', 'true')

    await usuario.keyboard('{Enter}')
    expect(botonDe('Prioridad')).toHaveAttribute('aria-expanded', 'false')

    await usuario.keyboard(' ')
    expect(botonDe('Prioridad')).toHaveAttribute('aria-expanded', 'true')
    expect(alEnviar).not.toHaveBeenCalled()
  })

  it('el énfasis con asteriscos se ve como negrita y cursiva, sin asteriscos sueltos', async () => {
    const usuario = userEvent.setup()
    render(<Ayuda clave="descuentos.prioridad" />)

    await usuario.click(botonDe('Prioridad'))

    const negrita = screen.getByText('más descuento da')
    expect(negrita.tagName).toBe('STRONG')
    expect(document.body.textContent).not.toContain('*')
  })
})

describe('Ayuda: cerrar', () => {
  it('Escape cierra y devuelve el foco al botón', async () => {
    const usuario = userEvent.setup()
    render(<Ayuda clave="descuentos.medida" />)
    await usuario.click(botonDe('Medida'))
    // El foco se mueve al panel (por ejemplo, por un clic en su texto).
    await usuario.click(screen.getByText(/cajas equivalentes/i))

    await usuario.keyboard('{Escape}')

    expect(screen.queryByText(/cajas equivalentes/i)).not.toBeInTheDocument()
    expect(botonDe('Medida')).toHaveAttribute('aria-expanded', 'false')
    expect(botonDe('Medida')).toHaveFocus()
  })

  it('Escape con el panel cerrado no mueve el foco', async () => {
    const usuario = userEvent.setup()
    render(
      <>
        <input aria-label="Otro campo" />
        <Ayuda clave="descuentos.medida" />
      </>,
    )
    const otro = screen.getByLabelText('Otro campo')
    otro.focus()

    await usuario.keyboard('{Escape}')

    expect(otro).toHaveFocus()
  })

  it('un pointerdown fuera cierra; dentro del panel no cierra', async () => {
    const usuario = userEvent.setup()
    render(
      <>
        <p>Texto de la pantalla</p>
        <Ayuda clave="descuentos.acumulable" />
      </>,
    )
    await usuario.click(botonDe('Acumulable'))

    await usuario.click(screen.getByText(/se suma a las demás/i))
    expect(botonDe('Acumulable')).toHaveAttribute('aria-expanded', 'true')

    await usuario.click(screen.getByText('Texto de la pantalla'))
    expect(botonDe('Acumulable')).toHaveAttribute('aria-expanded', 'false')
  })

  it('volver a activar el botón cierra', async () => {
    const usuario = userEvent.setup()
    render(<Ayuda clave="descuentos.medida" />)

    await usuario.click(botonDe('Medida'))
    await usuario.click(botonDe('Medida'))

    expect(botonDe('Medida')).toHaveAttribute('aria-expanded', 'false')
  })
})

describe('Ayuda: un solo panel abierto', () => {
  it('abrir un segundo cierra el primero', async () => {
    const usuario = userEvent.setup()
    render(
      <>
        <Ayuda clave="descuentos.medida" />
        <Ayuda clave="descuentos.umbral" />
      </>,
    )

    await usuario.click(botonDe('Medida'))
    await usuario.click(botonDe('Umbral'))

    expect(botonDe('Medida')).toHaveAttribute('aria-expanded', 'false')
    expect(botonDe('Umbral')).toHaveAttribute('aria-expanded', 'true')
    expect(screen.queryByText(/cajas equivalentes/i)).not.toBeInTheDocument()
    expect(screen.getByText(/El número que hay que alcanzar/)).toBeVisible()
  })

  it('con teclado: Enter en el segundo también cierra el primero', async () => {
    const usuario = userEvent.setup()
    render(
      <>
        <Ayuda clave="descuentos.medida" />
        <Ayuda clave="descuentos.umbral" />
      </>,
    )
    botonDe('Medida').focus()
    await usuario.keyboard('{Enter}')

    botonDe('Umbral').focus()
    await usuario.keyboard('{Enter}')

    expect(botonDe('Medida')).toHaveAttribute('aria-expanded', 'false')
    expect(botonDe('Umbral')).toHaveAttribute('aria-expanded', 'true')
  })
})

describe('Ayuda: enlace "Ver más"', () => {
  it('con verMas muestra el enlace a /admin/ayuda/<tema> en otra pestaña con noopener', async () => {
    const usuario = userEvent.setup()
    render(<Ayuda clave="descuentos.tope" />)
    await usuario.click(botonDe('Tope de descuento'))

    const enlace = screen.getByRole('link', { name: /ver más/i })
    expect(enlace).toHaveAttribute('href', '/admin/ayuda/topes')
    expect(enlace).toHaveAttribute('target', '_blank')
    expect(enlace.getAttribute('rel')).toContain('noopener')
  })

  it('el enlace sigue a la clave: "Medida" apunta al tema de descuentos', async () => {
    const usuario = userEvent.setup()
    render(<Ayuda clave="descuentos.medida" />)
    await usuario.click(botonDe('Medida'))

    expect(screen.getByRole('link', { name: /ver más/i })).toHaveAttribute('href', '/admin/ayuda/descuentos')
  })

  it('sin verMas no hay enlace', async () => {
    const usuario = userEvent.setup()
    render(<Ayuda clave="descuentos.umbral" />)
    await usuario.click(botonDe('Umbral'))

    expect(screen.queryByRole('link', { name: /ver más/i })).not.toBeInTheDocument()
  })
})

describe('Ayuda: dentro de un Dialogo (tarea 6.1)', () => {
  it('el panel lleva ancho máximo relativo al viewport y un z-index mayor que el de Dialogo', async () => {
    const usuario = userEvent.setup()
    render(
      <Dialogo abierto titulo="Regla" onCerrar={() => {}}>
        <Ayuda clave="descuentos.medida" />
      </Dialogo>,
    )
    await usuario.click(botonDe('Medida'))

    const panel = document.getElementById(botonDe('Medida').getAttribute('aria-controls') as string)
    expect(panel?.className).toContain('max-w-[calc(100vw-2rem)]')
    const zPanel = Number(/z-(\d+)/.exec(panel?.className ?? '')?.[1])
    const zDialogo = Number(/z-(\d+)/.exec(screen.getByRole('dialog').parentElement?.className ?? '')?.[1])
    expect(zPanel).toBeGreaterThan(zDialogo)
  })

  it('Escape cierra la ayuda sin cerrar el diálogo', async () => {
    const usuario = userEvent.setup()
    const alCerrar = vi.fn()
    render(
      <Dialogo abierto titulo="Regla" onCerrar={alCerrar}>
        <Ayuda clave="descuentos.medida" />
      </Dialogo>,
    )
    await usuario.click(botonDe('Medida'))

    await usuario.keyboard('{Escape}')

    expect(screen.queryByText(/cajas equivalentes/i)).not.toBeInTheDocument()
    expect(screen.getByRole('dialog', { name: 'Regla' })).toBeInTheDocument()
    expect(alCerrar).not.toHaveBeenCalled()
  })
})

describe('Ayuda: el panel queda dentro del área visible (change 21, prueba manual 20.2)', () => {
  /**
   * jsdom no mide layout: se fija el rectángulo del panel recién abierto (pegado al botón, cerca
   * del borde derecho) y el ancho visible del documento. `window.innerWidth` incluye la barra de
   * desplazamiento vertical; el panel tiene que caber en `clientWidth`, que no la incluye.
   */
  function fijarMedidas({ izquierda, anchoVisible, anchoVentana }: { izquierda: number; anchoVisible: number; anchoVentana: number }) {
    vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockImplementation(function (this: HTMLElement) {
      const ancho = this.id ? 288 : 24
      return { left: izquierda, width: ancho, right: izquierda + ancho, top: 0, bottom: 0, height: 0, x: izquierda, y: 0, toJSON: () => ({}) }
    })
    vi.spyOn(document.documentElement, 'clientWidth', 'get').mockReturnValue(anchoVisible)
    vi.stubGlobal('innerWidth', anchoVentana)
  }

  async function abrirYLeerCorrimiento(): Promise<string> {
    const usuario = userEvent.setup()
    render(<Ayuda clave="ruta.almacenamiento" />)
    await usuario.click(botonDe('Almacenamiento del teléfono'))
    const panel = document.getElementById(botonDe('Almacenamiento del teléfono').getAttribute('aria-controls') ?? '')
    return panel?.style.left ?? ''
  }

  afterEach(() => {
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  it('con barra de desplazamiento, se corre contando solo el ancho visible', async () => {
    fijarMedidas({ izquierda: 360, anchoVisible: 385, anchoVentana: 400 })

    // 360 + 288 − (385 − 8) = 271
    expect(await abrirYLeerCorrimiento()).toBe('-271px')
  })

  it('sin barra de desplazamiento, el corrimiento usa el mismo ancho', async () => {
    fijarMedidas({ izquierda: 360, anchoVisible: 400, anchoVentana: 400 })

    // 360 + 288 − (400 − 8) = 256
    expect(await abrirYLeerCorrimiento()).toBe('-256px')
  })

  it('lejos del borde no se corre', async () => {
    fijarMedidas({ izquierda: 20, anchoVisible: 385, anchoVentana: 400 })

    expect(await abrirYLeerCorrimiento()).toBe('0px')
  })
})
