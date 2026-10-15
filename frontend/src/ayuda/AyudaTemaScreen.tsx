import { Link, useParams } from 'react-router-dom'

import { PageHeader } from '../components/ui/PageHeader'
import { TemaDeAyudaVista } from './TemaDeAyudaVista'
import { TEMAS, type TemaDeAyuda } from './textos'

const RUTA_INDICE = '/admin/ayuda'

function esTema(valor: string | undefined): valor is TemaDeAyuda {
  return valor !== undefined && Object.hasOwn(TEMAS, valor)
}

/** `/admin/ayuda/:tema`: un tema de ayuda, o el aviso de que no existe. */
export function AyudaTemaScreen() {
  const { tema } = useParams()
  if (!esTema(tema)) {
    return (
      <div className="flex flex-col gap-3">
        <PageHeader titulo="No encontramos ese tema de ayuda" />
        <Link to={RUTA_INDICE} className="text-sm underline">
          Volver a Ayuda
        </Link>
      </div>
    )
  }
  return <TemaDeAyudaVista tema={tema} rutaIndice={RUTA_INDICE} />
}

export default AyudaTemaScreen
