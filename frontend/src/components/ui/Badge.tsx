import type { HTMLAttributes } from 'react'

/**
 * Insignia de estado de `/admin` (tarea 10.11, D10): "Activo/Inactivo",
 * "Referencia", etc. Solo estilo -- quien la usa decide el texto y la
 * variante según el dato real del servidor.
 */
export type VarianteBadge = 'neutral' | 'positivo' | 'negativo'

export interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  variante?: VarianteBadge
}

const CLASES_POR_VARIANTE: Record<VarianteBadge, string> = {
  neutral: 'bg-surface-muted text-primary/70 border-border',
  positivo: 'bg-primary/10 text-primary border-primary/20',
  negativo: 'bg-danger/10 text-danger border-danger/20',
}

export function Badge({ variante = 'neutral', className, ...resto }: BadgeProps) {
  const clases = [
    'inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-medium',
    CLASES_POR_VARIANTE[variante],
    className,
  ]
    .filter(Boolean)
    .join(' ')
  return <span className={clases} {...resto} />
}

export default Badge
