import { Link } from 'react-router-dom'

import { PageHeader } from '../components/ui/PageHeader'
import { TEMAS, type TemaDeAyuda } from './textos'

/** Índice de los temas "Ver más" (`/admin/ayuda`, `/ruta/ayuda`). Sin datos del servidor ni permisos. */
export function AyudaIndiceScreen({ base = '/admin/ayuda' }: { base?: string }) {
  const temas = Object.keys(TEMAS) as TemaDeAyuda[]
  return (
    <div className="flex max-w-3xl flex-col gap-4">
      <PageHeader titulo="Ayuda" />
      <ul className="flex flex-col gap-2">
        {temas.map((tema) => (
          <li key={tema}>
            <Link to={`${base}/${tema}`} className="text-sm font-medium underline">
              {TEMAS[tema].titulo}
            </Link>
          </li>
        ))}
      </ul>
    </div>
  )
}

export default AyudaIndiceScreen
