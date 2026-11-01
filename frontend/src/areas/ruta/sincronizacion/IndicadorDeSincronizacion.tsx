import { Link } from 'react-router-dom'

import { Ayuda } from '../../../components/ui/Ayuda'
import { useConectado } from '../../../lib/conexion'
import { useResumenDeSincronizacion } from '../datos/sincronizacion'
import { textoDeCabecera, textoDeRechazadas } from './presentacion'

const CLASE_ENLACE = 'font-medium text-primary underline'

/**
 * Cabecera de `/ruta` en toda pantalla (change 22b, `design.md` D8; SYN-09, `02` §13.3): conexión,
 * «N sin enviar» (o «Todo enviado») y un aviso si hay ventas rechazadas. Tocarlo abre
 * «Sincronización».
 */
export function IndicadorDeSincronizacion() {
  const conectado = useConectado()
  const resumen = useResumenDeSincronizacion()
  return (
    <header className="flex flex-wrap items-center justify-between gap-2 border-b border-border bg-surface px-4 py-2 text-xs text-primary">
      <span>{conectado ? 'Con conexión' : 'Sin conexión'}</span>
      <span className="flex items-center gap-3">
        <Link to="/ruta/sincronizacion" className={CLASE_ENLACE}>
          {textoDeCabecera(resumen.sinEnviar)}
        </Link>
        <Ayuda clave="ruta.sincronizar" />
        {resumen.rechazadas > 0 && (
          <Link to="/ruta/sincronizacion" className="font-medium text-danger underline">
            {textoDeRechazadas(resumen.rechazadas)}
          </Link>
        )}
      </span>
    </header>
  )
}
