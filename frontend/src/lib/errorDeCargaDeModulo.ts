/**
 * Detecta el error que aparece cuando el navegador no consigue descargar un fragmento de código
 * diferido (`lazy(() => import(...))`). Pasa tras un despliegue nuevo: los archivos con hash viejo
 * ya no existen y quien tenía la pestaña abierta pide uno que desapareció (change 27a, D19).
 * Cada navegador redacta el mensaje a su modo.
 */
const MARCAS = [
  'failed to fetch dynamically imported module', // Chrome, Edge
  'importing a module script failed', // Safari
  'error loading dynamically imported module', // Firefox
  'loading chunk', // empaquetadores con fragmentos numerados
  'loading css chunk',
]

export function esErrorDeCargaDeModulo(error: unknown): boolean {
  if (typeof error !== 'object' || error === null) return false
  const { name, message } = error as { name?: unknown; message?: unknown }
  if (name === 'ChunkLoadError') return true
  if (typeof message !== 'string') return false
  const texto = message.toLowerCase()
  return MARCAS.some((marca) => texto.includes(marca))
}
