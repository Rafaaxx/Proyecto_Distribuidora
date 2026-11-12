import { Link } from 'react-router-dom'

import { Boton } from '../../../components/ui/Button'
import { Card } from '../../../components/ui/Card'
import { useConectado } from '../../../lib/conexion'
import { CerrarSesionBoton } from '../sesion/CerrarSesionBoton'
import { useSesionRutaActiva } from '../sesion/contextoSesion'

/**
 * Mi cuenta de `/ruta` (change 21, `design.md` D16, D19; ADR-060, SEG-03): "Mi contraseña" (solo
 * con conexión), "Cambiar PIN" (con o sin conexión) y "Cerrar sesión" (solo con conexión).
 */
const CLASE_ENLACE =
  'inline-flex items-center justify-center rounded-md border border-border bg-surface-muted px-3 py-3 text-sm font-medium text-primary hover:bg-surface'

export function MiCuentaScreen() {
  const conectado = useConectado()
  const { alCerrarSesion } = useSesionRutaActiva()

  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-lg font-semibold text-primary">Mi cuenta</h1>
      <Card className="flex flex-col gap-4">
        {conectado ? (
          <Link to="/ruta/cuenta/contrasena" className={CLASE_ENLACE}>
            Mi contraseña
          </Link>
        ) : (
          <div className="flex flex-col gap-1">
            <Boton variante="secundario" disabled>
              Mi contraseña
            </Boton>
            <p className="text-sm text-primary/70">Cambiar la contraseña requiere conexión.</p>
          </div>
        )}
        <Link to="/ruta/cuenta/pin" className={CLASE_ENLACE}>
          Cambiar PIN
        </Link>
        <CerrarSesionBoton onCerrada={alCerrarSesion} />
      </Card>
    </div>
  )
}

export default MiCuentaScreen
