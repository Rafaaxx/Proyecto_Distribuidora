import { useRouteError } from 'react-router-dom'

import { Boton } from '../components/ui/Button'
import { esErrorDeCargaDeModulo } from '../lib/errorDeCargaDeModulo'

/**
 * Pantalla de error de ruta de `/admin` y de `/ruta` (change 27a, D19). Reemplaza la pantalla por
 * defecto de React Router («Unexpected Application Error!»). Si falló la carga de una pantalla
 * diferida es que hay una versión nueva del sistema: se pide recargar. La detección vive en
 * `lib/errorDeCargaDeModulo.ts`; acá solo se muestra el resultado.
 */
export function PantallaDeError() {
  const error = useRouteError()
  const versionNueva = esErrorDeCargaDeModulo(error)

  return (
    <main className="flex min-h-dvh items-center justify-center bg-surface-muted p-4">
      <div role="alert" className="w-full max-w-sm rounded-md border border-border bg-surface p-6 shadow-sm">
        <h1 className="mb-2 text-lg font-semibold text-primary">
          {versionNueva ? 'Hay una versión nueva del sistema' : 'Algo salió mal'}
        </h1>
        <p className="mb-4 text-sm text-primary">
          {versionNueva
            ? 'Para seguir, recargá la pantalla.'
            : 'Ocurrió un error inesperado. Recargá la pantalla; si sigue pasando, avisá a Administración.'}
        </p>
        <Boton onClick={() => window.location.reload()} className="w-full">
          Recargar
        </Boton>
      </div>
    </main>
  )
}

export default PantallaDeError
