import { Link, Navigate } from 'react-router-dom'

import { Card } from '../../components/ui/Card'
import { CODIGO_DE_EXCESO_AL_SINCRONIZAR, lineasDeAviso, type LineaDeAviso } from '../../domain/revision/aviso'
import { primeraSeccionPermitida } from '../../features/identidad/secciones'
import { usePermisos } from '../../features/identidad/usePermisos'
import { useResumenDePendientes } from '../../features/revision/hooks'
import { AvisoDeConsistencia } from './AvisoDeConsistencia'

/**
 * Ruta índice de `/admin` (`/admin/inicio`, tarea 7.6, `design.md` D5-A,
 * **B3**): es adonde lleva el login. Para quien no revisa observaciones no es
 * una pantalla con datos propios, sino el punto que decide a qué sección lleva
 * a cada usuario.
 *
 * Antes de `/admin/dispositivos` el login mandaba a todo el mundo a
 * Dispositivos, así que un usuario de Administración o un Vendedor veían
 * "No tenés permiso" apenas entraban (`01` §19: solo Administración y
 * Supervisor tienen `GESTIONAR_DISPOSITIVOS`). Ahora la ruta espera la
 * consulta de sesión y salta a la primera sección permitida, en el orden
 * de `features/identidad/secciones.ts` -- la misma lista que arma el menú,
 * así que el aterrizaje no puede desincronizarse de él.
 *
 * Falla cerrada (**B1**): mientras `/yo` está pendiente no salta a ninguna
 * parte, y si la consulta falla no afirma que el usuario no tiene
 * secciones (informar eso sería mentir: lo que no se sabe es si las tiene).
 * El aviso con **Reintentar** o el enlace a iniciar sesión lo muestra el
 * layout, que envuelve esta ruta.
 *
 * Change 25 (tarea 15.1, D5, CRE-09): quien tiene `REVISAR_OBSERVACIONES` aterriza en la tarjeta «Para revisar»
 * —avisos, operaciones rechazadas y, aparte, los excesos de crédito detectados al sincronizar— en vez de saltar
 * a una sección; desde el menú llega a todas las demás.
 *
 * Change 28 (tarea 3.2, D5): encima de esa tarjeta, el aviso de diferencias de consistencia, solo para quien tiene
 * `VER_CONSISTENCIA` y mientras la última verificación haya encontrado diferencias.
 */
const SIN_SECCIONES = 'Tu usuario no tiene secciones de administración disponibles'
const SIN_AVISOS = 'Sin avisos pendientes.'

export function AdminInicio() {
  const permisos = usePermisos()

  if (permisos.estado === 'cargando') {
    return <p className="text-sm text-primary/70">Cargando…</p>
  }

  if (permisos.estado === 'error') {
    return null
  }

  if (permisos.tiene('REVISAR_OBSERVACIONES')) {
    return (
      <div className="flex flex-col gap-4">
        <AvisoDeConsistencia />
        <ParaRevisar />
      </div>
    )
  }

  const primera = primeraSeccionPermitida(permisos.tiene)

  if (!primera) {
    return <p className="text-sm text-primary/70">{SIN_SECCIONES}</p>
  }

  return <Navigate to={primera.ruta} replace />
}

const CLASE_ENLACE = 'text-primary hover:underline'

function Linea({ linea, a, destacada = false }: { linea: LineaDeAviso; a: string; destacada?: boolean }) {
  return (
    <li>
      <Link to={a} className={destacada ? 'font-semibold text-danger hover:underline' : CLASE_ENLACE}>
        {linea.texto}
      </Link>
    </li>
  )
}

/** La tarjeta «Para revisar» (D5): se actualiza sola cada 60 s y al volver a la pestaña. */
function ParaRevisar() {
  const resumen = useResumenDePendientes(true)
  const lineas = resumen.data === undefined ? null : lineasDeAviso(resumen.data)
  const hayAlgo = lineas !== null && (lineas.avisos !== null || lineas.rechazadas !== null || lineas.excesos !== null)

  return (
    <section aria-labelledby="para-revisar" className="max-w-xl">
      <Card className="flex flex-col gap-3">
        <h1 id="para-revisar" className="text-lg font-semibold text-primary">
          Para revisar
        </h1>
        {resumen.isPending && <p className="text-sm text-primary/70">Cargando…</p>}
        {lineas !== null && !hayAlgo && <p className="text-sm text-primary/70">{SIN_AVISOS}</p>}
        {lineas !== null && hayAlgo && (
          <ul className="flex flex-col gap-2 text-sm">
            {lineas.excesos !== null && (
              <Linea linea={lineas.excesos} a={`/admin/revision?codigo=${CODIGO_DE_EXCESO_AL_SINCRONIZAR}`} destacada />
            )}
            {lineas.avisos !== null && <Linea linea={lineas.avisos} a="/admin/revision" />}
            {lineas.rechazadas !== null && <Linea linea={lineas.rechazadas} a="/admin/revision/rechazadas" />}
          </ul>
        )}
      </Card>
    </section>
  )
}

export default AdminInicio
