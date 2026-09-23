import type { ReactNode } from 'react'

/**
 * Campo de formulario base de `/admin` (tarea 10.1): etiqueta + control +
 * mensaje de error, con el `id`/`htmlFor` ya conectados. El control se pasa
 * como children (viene de `register(...)` de React Hook Form) para no
 * imponerle un tipo de `input` fijo -- lo necesitan `<select>` y checkboxes
 * además de `<input>` (tarea 10.5, 10.6).
 */
export interface CampoProps {
  id: string
  etiqueta: string
  error?: string
  children: ReactNode
}

export function Campo({ id, etiqueta, error, children }: CampoProps) {
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={id} className="text-sm font-medium text-primary">
        {etiqueta}
      </label>
      {children}
      {error && (
        <p role="alert" className="text-sm text-danger">
          {error}
        </p>
      )}
    </div>
  )
}

export default Campo
