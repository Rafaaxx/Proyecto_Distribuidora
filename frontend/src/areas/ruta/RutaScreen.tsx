import { AvisoDeVersion } from './pwa/AvisoDeVersion'
import { RutaLayout } from './RutaLayout'
import { SesionRuta } from './sesion/SesionRuta'

/**
 * Área de ruta. La sesión local (login, PIN, bootstrap) la gestiona `SesionRuta`; con la sesión
 * desbloqueada se muestran las pantallas de `RutaLayout`. El aviso de versión nueva (service
 * worker) va fuera de la sesión: también se ve en el login y en el PIN (change 21, D17).
 */
export function RutaScreen() {
  return (
    <>
      <SesionRuta>
        <RutaLayout />
      </SesionRuta>
      <AvisoDeVersion />
    </>
  )
}

export default RutaScreen
