import type { ReactNode } from 'react'

/**
 * Tabla base de `/admin` (tarea 10.1): solo estilo, sin paginación ni
 * lógica -- eso lo maneja cada pantalla (tarea 10.4).
 */
export interface ColumnaTabla<T> {
  clave: string
  encabezado: string
  render: (fila: T) => ReactNode
}

export interface TablaProps<T> {
  filas: T[]
  columnas: ColumnaTabla<T>[]
  obtenerClave: (fila: T) => string
  /** Grupo 8, tarea 8.3 (decisión del usuario 2026-09-29): cuando se pasa,
   * toda la fila navega al hacer clic, salvo que el clic haya empezado en
   * un elemento interactivo propio (link, botón, input, select) -- así el
   * nombre sigue siendo un `<Link>` real para el teclado y los lectores de
   * pantalla, y la fila no se convierte en un botón falso. Opcional: las
   * tablas que no lo pasan (por ejemplo `ProductosListScreen`) no cambian. */
  onFilaClick?: (fila: T) => void
}

const SELECTOR_ELEMENTOS_INTERACTIVOS = 'a, button, input, select, textarea'

export function Tabla<T>({ filas, columnas, obtenerClave, onFilaClick }: TablaProps<T>) {
  return (
    <table className="w-full border-collapse text-left text-sm">
      <thead>
        <tr className="border-b border-border">
          {columnas.map((columna) => (
            <th key={columna.clave} className="px-3 py-2 font-medium text-primary">
              {columna.encabezado}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {filas.map((fila) => (
          <tr
            key={obtenerClave(fila)}
            className={
              onFilaClick
                ? 'cursor-pointer border-b border-border last:border-0 hover:bg-surface-muted'
                : 'border-b border-border last:border-0'
            }
            onClick={
              onFilaClick
                ? (evento) => {
                    const objetivo = evento.target as HTMLElement
                    if (objetivo.closest(SELECTOR_ELEMENTOS_INTERACTIVOS)) return
                    onFilaClick(fila)
                  }
                : undefined
            }
          >
            {columnas.map((columna) => (
              <td key={columna.clave} className="px-3 py-2">
                {columna.render(fila)}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  )
}

export default Tabla
