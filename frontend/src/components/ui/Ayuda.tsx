import { useEffect, useId, useLayoutEffect, useRef, useState } from 'react'

import { conEnfasis } from '../../ayuda/formato'
import { AYUDAS, type ClaveDeAyuda } from '../../ayuda/textos'

/**
 * Botón "(?)" de ayuda contextual (change 16b, ADR-051, `design.md` D2 = A).
 *
 * - Es un `<button type="button">` nativo: Enter y Espacio abren sin enviar el formulario que
 *   lo contenga. Nombre accesible "Ayuda: <título>", `aria-expanded` y `aria-controls`.
 * - El panel (no modal) va justo después del botón en el orden del documento, así Tab llega
 *   al enlace "Ver más". Solo existe en el DOM mientras está abierto.
 * - Cierra con Escape (y devuelve el foco al botón), con un `pointerdown` fuera del botón y
 *   del panel, y al abrirse otra ayuda (queda un solo panel abierto).
 * - Ancho máximo relativo al viewport y `z-20`, por encima del `Dialogo` (`z-10`).
 * - Los textos no se escriben acá: salen de `ayuda/textos.ts` por clave.
 */
const EVENTO_AYUDA_ABIERTA = 'ayuda:abierta'
const MARGEN_PX = 8

export interface AyudaProps {
  clave: ClaveDeAyuda
}

export function Ayuda({ clave }: AyudaProps) {
  const entrada: { titulo: string; texto: string; ejemplo?: string; verMas?: string } = AYUDAS[clave]
  const idPanel = useId()
  const [abierta, setAbierta] = useState(false)
  const [desplazamiento, setDesplazamiento] = useState(0)
  const contenedor = useRef<HTMLSpanElement>(null)
  const boton = useRef<HTMLButtonElement>(null)
  const panel = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!abierta) {
      return undefined
    }
    const alPulsarFuera = (evento: PointerEvent) => {
      if (evento.target instanceof Node && !contenedor.current?.contains(evento.target)) {
        setAbierta(false)
      }
    }
    const alPulsarTecla = (evento: KeyboardEvent) => {
      if (evento.key === 'Escape') {
        setAbierta(false)
        boton.current?.focus()
      }
    }
    const alAbrirOtra = (evento: Event) => {
      if (evento instanceof CustomEvent && evento.detail !== idPanel) {
        setAbierta(false)
      }
    }
    document.addEventListener('pointerdown', alPulsarFuera)
    document.addEventListener('keydown', alPulsarTecla)
    document.addEventListener(EVENTO_AYUDA_ABIERTA, alAbrirOtra)
    return () => {
      document.removeEventListener('pointerdown', alPulsarFuera)
      document.removeEventListener('keydown', alPulsarTecla)
      document.removeEventListener(EVENTO_AYUDA_ABIERTA, alAbrirOtra)
    }
  }, [abierta, idPanel])

  // En un teléfono el botón puede estar cerca del borde derecho: se corre el panel para que
  // quede dentro de la pantalla, sin desplazamiento horizontal.
  useLayoutEffect(() => {
    if (!abierta || !panel.current) {
      return
    }
    // Se mide recién abierto (desplazamiento 0), una sola vez por apertura.
    const { left, width } = panel.current.getBoundingClientRect()
    if (width === 0) {
      return
    }
    const sobra = left + width - (window.innerWidth - MARGEN_PX)
    const corrimiento = -Math.max(0, sobra)
    setDesplazamiento(left + corrimiento < MARGEN_PX ? MARGEN_PX - left : corrimiento)
  }, [abierta])

  const alternar = () => {
    if (abierta) {
      setAbierta(false)
      return
    }
    document.dispatchEvent(new CustomEvent(EVENTO_AYUDA_ABIERTA, { detail: idPanel }))
    setDesplazamiento(0)
    setAbierta(true)
  }

  return (
    <span ref={contenedor} className="relative inline-block align-middle">
      <button
        ref={boton}
        type="button"
        aria-label={`Ayuda: ${entrada.titulo}`}
        aria-expanded={abierta}
        aria-controls={idPanel}
        onClick={alternar}
        className="inline-flex h-6 min-w-6 items-center justify-center rounded-full border border-border px-1 text-xs font-semibold text-primary/80 hover:bg-surface-muted"
      >
        (?)
      </button>
      {abierta && (
        <div
          ref={panel}
          id={idPanel}
          style={{ left: desplazamiento }}
          className="absolute top-full z-20 mt-1 w-72 max-w-[calc(100vw-2rem)] rounded-md border border-border bg-surface p-3 text-sm font-normal text-primary shadow-lg"
        >
          <p>{conEnfasis(entrada.texto)}</p>
          {entrada.ejemplo && (
            <p className="mt-2 rounded-md bg-surface-muted p-2 text-primary/80">{conEnfasis(entrada.ejemplo)}</p>
          )}
          {entrada.verMas && (
            <a
              href={`/admin/ayuda/${entrada.verMas}`}
              target="_blank"
              rel="noopener noreferrer"
              className="mt-2 inline-block font-medium underline"
            >
              Ver más
            </a>
          )}
        </div>
      )}
    </span>
  )
}

export default Ayuda
