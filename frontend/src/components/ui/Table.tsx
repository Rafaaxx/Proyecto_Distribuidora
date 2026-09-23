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
}

export function Tabla<T>({ filas, columnas, obtenerClave }: TablaProps<T>) {
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
          <tr key={obtenerClave(fila)} className="border-b border-border last:border-0">
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
