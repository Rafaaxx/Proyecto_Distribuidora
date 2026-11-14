import { useContext, type ButtonHTMLAttributes } from 'react'

import { clasesDeBoton, TamanoDeBotonContext, type TamanoBoton, type VarianteBoton } from './botonEstilos'

/**
 * Botón base (tarea 10.1, `design.md` D10). Sin lógica de negocio -- solo variantes visuales
 * sobre los tokens de `index.css`. Los estilos y los tamaños viven en `botonEstilos.ts`.
 */
export type { TamanoBoton, VarianteBoton }

export interface BotonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variante?: VarianteBoton
  /** Si se omite, toma el del `TamanoDeBotonContext` más cercano (`normal` sin proveedor). */
  tamano?: TamanoBoton
}

export function Boton({ variante = 'primario', tamano, className, type = 'button', ...resto }: BotonProps) {
  const tamanoDelArea = useContext(TamanoDeBotonContext)
  const clases = [clasesDeBoton(variante, tamano ?? tamanoDelArea), className].filter(Boolean).join(' ')
  return <button type={type} className={clases} {...resto} />
}

export default Boton
