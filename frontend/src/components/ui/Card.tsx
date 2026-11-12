import type { HTMLAttributes } from 'react'

/**
 * Contenedor visual base de `/admin` (tarea 10.11, D10): superficie
 * elevada sobre `bg-surface-muted` del layout, sin lógica -- mismo
 * criterio que el resto de `components/ui/`.
 */
export function Card({ className, ...resto }: HTMLAttributes<HTMLDivElement>) {
  const clases = ['rounded-md border border-border bg-surface p-4 shadow-sm', className].filter(Boolean).join(' ')
  return <div className={clases} {...resto} />
}

export default Card
