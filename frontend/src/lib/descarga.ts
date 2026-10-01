/**
 * Guarda un archivo generado en el cliente (por ejemplo la plantilla CSV que devuelve la
 * API) con el nombre dado, como una descarga del navegador. Sin lógica de negocio: solo
 * el enlace temporal sobre un `Blob`.
 */
export function guardarArchivo(blob: Blob, nombre: string): void {
  const url = URL.createObjectURL(blob)
  const enlace = document.createElement('a')
  enlace.href = url
  enlace.download = nombre
  document.body.appendChild(enlace)
  enlace.click()
  enlace.remove()
  URL.revokeObjectURL(url)
}
