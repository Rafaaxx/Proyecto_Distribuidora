import type { ButtonHTMLAttributes } from 'react'

/**
 * Botón base de `/admin` (tarea 10.1, `design.md` D10). Sin lógica de
 * negocio -- solo variantes visuales sobre los tokens de `index.css`.
 */
export type VarianteBoton = 'primario' | 'secundario' | 'peligro'

export interface BotonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variante?: VarianteBoton
}

const CLASES_BASE =
  'inline-flex items-center justify-center rounded-md px-3 py-2 text-sm font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50'

const CLASES_POR_VARIANTE: Record<VarianteBoton, string> = {
  primario: 'bg-primary text-primary-foreground hover:opacity-90',
  secundario: 'bg-surface-muted text-primary border border-border hover:bg-surface',
  peligro: 'bg-danger text-danger-foreground hover:opacity-90',
}

export function Boton({ variante = 'primario', className, type = 'button', ...resto }: BotonProps) {
  const clases = [CLASES_BASE, CLASES_POR_VARIANTE[variante], className].filter(Boolean).join(' ')
  return <button type={type} className={clases} {...resto} />
}

export default Boton
