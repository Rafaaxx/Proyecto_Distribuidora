import { PermisoRequeridoError, useDispositivos } from './useDispositivos'
import { useRevocarDispositivo } from './useRevocarDispositivo'

/**
 * Pantalla de dispositivos de `/admin` (tarea 13.5, spec `identidad/dispositivos`).
 *
 * La visibilidad depende de la respuesta real de `GET /identidad/dispositivos`
 * (200 vs 403 `PERMISO_REQUERIDO`), no de una copia local del permiso: no
 * existe en este change un endpoint que liste "mis permisos", y ADR-017
 * dice explícitamente que los permisos no viajan en el access token. Ocultar
 * la tabla ante un 403 es cosmético (SEG-06) -- el servidor vuelve a validar
 * el permiso en cada petición, incluida la de revocar.
 */
export function DispositivosScreen() {
  const dispositivos = useDispositivos()
  const revocar = useRevocarDispositivo()

  if (dispositivos.isPending) {
    return (
      <main>
        <h1>Dispositivos</h1>
        <p>Cargando…</p>
      </main>
    )
  }

  if (dispositivos.isError) {
    if (dispositivos.error instanceof PermisoRequeridoError) {
      return (
        <main>
          <h1>Dispositivos</h1>
          <p>No tenés permiso para gestionar dispositivos.</p>
        </main>
      )
    }
    return (
      <main>
        <h1>Dispositivos</h1>
        <p role="alert">No se pudieron obtener los dispositivos.</p>
      </main>
    )
  }

  return (
    <main>
      <h1>Dispositivos</h1>
      <table>
        <thead>
          <tr>
            <th>Nombre</th>
            <th>Prefijo</th>
            <th>Estado</th>
            <th>Último correlativo</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {dispositivos.data.map((dispositivo) => (
            <tr key={dispositivo.id}>
              <td>{dispositivo.nombre}</td>
              <td>{dispositivo.prefijo}</td>
              <td>{dispositivo.estado}</td>
              <td>{dispositivo.ultimo_correlativo}</td>
              <td>
                <button
                  type="button"
                  disabled={dispositivo.estado === 'REVOCADO' || revocar.isPending}
                  onClick={() => revocar.mutate(dispositivo.id)}
                >
                  Revocar
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </main>
  )
}

export default DispositivosScreen
