import type { HTMLAttributes } from 'react'

/**
 * Mensaje de error/alerta de `/admin` (tarea 10.11, D10). Mantiene
 * `role="alert"` para no romper las pruebas existentes que ya buscan ese
 * rol -- solo agrega estilo alrededor del texto que cada pantalla ya
 * calculaba.
 */
export function Alert({ className, ...resto }: HTMLAttributes<HTMLParagraphElement>) {
  const clases = [
    'rounded-md border border-danger/30 bg-danger/10 px-3 py-2 text-sm text-danger',
    className,
  ]
    .filter(Boolean)
    .join(' ')
  return <p role="alert" className={clases} {...resto} />
}

export default Alert
