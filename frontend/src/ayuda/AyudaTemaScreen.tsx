import { Link, useParams } from 'react-router-dom'

import { PageHeader } from '../components/ui/PageHeader'
import { TemaDeAyudaVista } from './TemaDeAyudaVista'
import { TEMAS, type TemaDeAyuda } from './textos'

function esTema(valor: string | undefined): valor is TemaDeAyuda {
  return valor !== undefined && Object.hasOwn(TEMAS, valor)
}

/** Un tema de ayuda (`/admin/ayuda/:tema`, `/ruta/ayuda/:tema`), o el aviso de que no existe. */
export function AyudaTemaScreen({ base = '/admin/ayuda' }: { base?: string }) {
  const { tema } = useParams()
  if (!esTema(tema)) {
    return (
      <div className="flex flex-col gap-3">
        <PageHeader titulo="No encontramos ese tema de ayuda" />
        <Link to={base} className="text-sm underline">
          Volver a Ayuda
        </Link>
      </div>
    )
  }
  return <TemaDeAyudaVista tema={tema} rutaIndice={base} />
}

export default AyudaTemaScreen
