import { Badge } from '../../../components/ui/Badge'
import { Boton } from '../../../components/ui/Button'
import { Card } from '../../../components/ui/Card'
import { PageHeader } from '../../../components/ui/PageHeader'
import { SiTienePermiso } from '../../../features/identidad/SiTienePermiso'
import { PermisoRequeridoError, useDispositivos } from './useDispositivos'
import { useRevocarDispositivo } from './useRevocarDispositivo'

/**
 * Pantalla de dispositivos de `/admin` (spec `identidad/dispositivos`, tarea
 * 8.1 del change 06b).
 *
 * Qué se muestra lo decide **solo** la consulta de sesión `['yo']`, a través
 * del mecanismo compartido `<SiTienePermiso>` (ADR-027, `design.md` D4-A
 * opción A / **B2**). Sin `GESTIONAR_DISPOSITIVOS` los hijos no se montan:
 * React nunca evalúa el componente interno, así que la pantalla no pide el
 * listado para averiguar si el usuario puede verlo.
 *
 * El 403 del servidor sigue tratándose, pero **solo como red de seguridad**:
 * ocurre cuando el permiso se quitó del rol entre dos renovaciones del
 * access token, mientras `['yo']` todavía lo informaba. Ya no decide
 * visibilidad (ADR-027 "Retiro del patrón reactivo"), y el servidor sigue
 * validando cada petición, incluida la de revocar (SEG-06: ocultar en la
 * interfaz es cosmético).
 */
export function DispositivosScreen() {
  return (
    <SiTienePermiso permiso="GESTIONAR_DISPOSITIVOS" fallback={<FaltaPermisoDeDispositivos />}>
      <DispositivosPermitidos />
    </SiTienePermiso>
  )
}

/** Estado sin permiso: mismo texto que el 403, para que el usuario no
 * distinga por el mensaje de por qué no ve la pantalla. */
function FaltaPermisoDeDispositivos() {
  return (
    <main className="flex flex-col gap-4">
      <PageHeader titulo="Dispositivos" />
      <p className="text-sm text-primary/70">No tenés permiso para gestionar dispositivos.</p>
    </main>
  )
}

/** Componente interno: es el único que consulta datos, y solo existe si hay
 * permiso. Por eso los hooks no están en `DispositivosScreen`. */
function DispositivosPermitidos() {
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
      return <FaltaPermisoDeDispositivos />
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
