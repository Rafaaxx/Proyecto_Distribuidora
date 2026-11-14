import { Link } from 'react-router-dom'

import { clasesDeBoton } from '../components/ui/botonEstilos'
import { useTituloDePagina } from '../lib/useTituloDePagina'

/**
 * Página 404 reutilizable. Cada nivel (dirección suelta, `/admin`, `/ruta`) indica a dónde vuelve
 * el botón; dentro de `/admin` y `/ruta` se muestra dentro del layout, con el menú a la vista.
 */
export function PaginaNoEncontrada({
  destino,
  textoDelBoton = 'Volver al inicio',
}: {
  destino: string
  textoDelBoton?: string
}) {
  useTituloDePagina('Esta página no existe')

  return (
    <main className="flex min-h-[60dvh] items-center justify-center p-4">
      <div className="w-full max-w-md rounded-lg border border-border bg-surface p-6 text-center shadow-sm">
        <h1 className="text-2xl font-bold tracking-tight text-primary">Esta página no existe</h1>
        <p className="mt-3 text-base text-primary">
          La dirección que abriste no corresponde a ninguna pantalla. Puede que esté mal escrita o que ya no esté
          disponible.
        </p>
        <Link to={destino} className={`${clasesDeBoton('primario', 'grande')} mt-6 w-full`}>
          {textoDelBoton}
        </Link>
      </div>
    </main>
  )
}

export default PaginaNoEncontrada
