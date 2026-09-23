import type { ReactNode } from 'react'

/**
 * Encabezado de pantalla de `/admin` (tarea 10.11, D10): título + acciones
 * opcionales a la derecha (por ejemplo, un enlace de navegación
 * secundaria). Sin lógica de negocio.
 */
export interface PageHeaderProps {
  titulo: ReactNode
  acciones?: ReactNode
}

export function PageHeader({ titulo, acciones }: PageHeaderProps) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-2">
      <h1 className="text-lg font-semibold text-primary">{titulo}</h1>
      {acciones && <div className="flex items-center gap-3">{acciones}</div>}
    </div>
  )
}

export default PageHeader
