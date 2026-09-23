import { Badge } from '../../../components/ui/Badge'
import { Boton } from '../../../components/ui/Button'
import { Card } from '../../../components/ui/Card'
import { PageHeader } from '../../../components/ui/PageHeader'
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
      <main className="flex flex-col gap-4">
        <PageHeader titulo="Dispositivos" />
        <p className="text-sm text-primary/70">Cargando…</p>
      </main>
    )
  }

  if (dispositivos.isError) {
    if (dispositivos.error instanceof PermisoRequeridoError) {
      return (
        <main className="flex flex-col gap-4">
          <PageHeader titulo="Dispositivos" />
          <p className="text-sm text-primary/70">No tenés permiso para gestionar dispositivos.</p>
        </main>
      )
    }
    return (
      <main className="flex flex-col gap-4">
        <PageHeader titulo="Dispositivos" />
        <p role="alert" className="text-sm text-danger">
          No se pudieron obtener los dispositivos.
        </p>
      </main>
    )
  }

  return (
    <main className="flex flex-col gap-4">
      <PageHeader titulo="Dispositivos" />
      <Card className="overflow-x-auto p-0">
        <table className="w-full border-collapse text-left text-sm">
          <thead>
            <tr className="border-b border-border">
              <th className="px-3 py-2 font-medium text-primary">Nombre</th>
              <th className="px-3 py-2 font-medium text-primary">Prefijo</th>
              <th className="px-3 py-2 font-medium text-primary">Estado</th>
              <th className="px-3 py-2 font-medium text-primary">Último correlativo</th>
              <th className="px-3 py-2"></th>
            </tr>
          </thead>
          <tbody>
            {dispositivos.data.map((dispositivo) => (
              <tr key={dispositivo.id} className="border-b border-border last:border-0">
                <td className="px-3 py-2">{dispositivo.nombre}</td>
                <td className="px-3 py-2">{dispositivo.prefijo}</td>
                <td className="px-3 py-2">
                  <Badge variante={dispositivo.estado === 'REVOCADO' ? 'negativo' : 'positivo'}>
                    {dispositivo.estado}
                  </Badge>
                </td>
                <td className="px-3 py-2">{dispositivo.ultimo_correlativo}</td>
                <td className="px-3 py-2">
                  <Boton
                    variante="peligro"
                    disabled={dispositivo.estado === 'REVOCADO' || revocar.isPending}
                    onClick={() => revocar.mutate(dispositivo.id)}
                  >
                    Revocar
                  </Boton>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </main>
  )
}

export default DispositivosScreen
