import { useRegisterSW } from 'virtual:pwa-register/react'

import { Boton } from '../../../components/ui/Button'
import { useGuardaDelCarrito } from '../ventas/contextoGuarda'

/**
 * Aviso de versión nueva (change 21, `design.md` D17; `02` §13.5). Registra el service worker
 * (`registerType: 'prompt'`): una versión nueva se instala en segundo plano y espera. La pantalla
 * actual NO se recarga sola; "Actualizar" activa la versión nueva y recarga. Con un carrito
 * abierto (change 22a, D12; `02` §13.5) no se ofrece "Actualizar": se instala al terminar la venta.
 */
export function AvisoDeVersion() {
  const {
    needRefresh: [hayVersionNueva],
    updateServiceWorker,
  } = useRegisterSW({ immediate: true })

  const { ocupado } = useGuardaDelCarrito()

  if (!hayVersionNueva) return null

  return (
    <div
      role="status"
      className="fixed inset-x-3 bottom-3 z-30 flex items-center justify-between gap-3 rounded-md border border-border bg-surface p-3 text-sm text-primary shadow-lg"
    >
      {ocupado ? (
        <span>Hay una versión nueva: se instala al terminar la venta</span>
      ) : (
        <>
          <span>Hay una versión nueva</span>
          <Boton onClick={() => void updateServiceWorker(true)}>Actualizar</Boton>
        </>
      )}
    </div>
  )
}

export default AvisoDeVersion
