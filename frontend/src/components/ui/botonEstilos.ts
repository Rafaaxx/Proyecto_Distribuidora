import { createContext } from 'react'

/**
 * Estilos del botón base, separados de `Button.tsx` para poder reusarlos en un `Link` estilado
 * como botón sin duplicar clases.
 *
 * Dos tamaños: `normal` (el de siempre, el de `/ruta`) y `grande` (borde marcado, alto táctil
 * mínimo de 44 px, texto base y foco visible), que usa `/admin`. En vez de pasar el tamaño botón
 * por botón, `AdminScreen` lo fija para toda su área con `TamanoDeBotonContext.Provider`; fuera de
 * ese proveedor todo queda como estaba.
 */
export type VarianteBoton = 'primario' | 'secundario' | 'peligro'
export type TamanoBoton = 'normal' | 'grande'

const CLASES_BASE =
  'inline-flex items-center justify-center rounded-md transition-colors disabled:cursor-not-allowed disabled:opacity-50'

const CLASES_NORMAL = 'px-3 py-2 text-sm font-medium'

const CLASES_GRANDE =
  'min-h-11 border-2 px-4 py-2 text-base font-semibold focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2'

const CLASES_POR_VARIANTE: Record<TamanoBoton, Record<VarianteBoton, string>> = {
  normal: {
    primario: 'bg-primary text-primary-foreground hover:opacity-90',
    secundario: 'bg-surface-muted text-primary border border-border hover:bg-surface',
    peligro: 'bg-danger text-danger-foreground hover:opacity-90',
  },
  grande: {
    primario: 'border-primary bg-primary text-primary-foreground hover:opacity-90',
    secundario: 'border-primary bg-surface-muted text-primary hover:bg-surface',
    peligro: 'border-danger bg-danger text-danger-foreground hover:opacity-90 focus-visible:ring-danger',
  },
}

/** Clases de un botón; sirve también para estilar como botón un `Link` (una acción que navega). */
export function clasesDeBoton(variante: VarianteBoton = 'primario', tamano: TamanoBoton = 'normal'): string {
  const medidas = tamano === 'grande' ? CLASES_GRANDE : CLASES_NORMAL
  return [CLASES_BASE, medidas, CLASES_POR_VARIANTE[tamano][variante]].join(' ')
}

export const TamanoDeBotonContext = createContext<TamanoBoton>('normal')
