import { Link } from 'react-router-dom'

import { PageHeader } from '../components/ui/PageHeader'
import { conEnfasis } from './formato'
import { TEMAS, type TemaDeAyuda, type TemaDeAyudaDef } from './textos'

/**
 * Contenido de una página "Ver más" (change 16b, ADR-051, D5 y D7 = A). Reutilizable: `/admin`
 * la monta en `/admin/ayuda/:tema` y `/ruta` podrá montarla en su propia ruta. No pide datos ni
 * depende de permisos: todo sale del archivo de textos.
 */
export interface TemaDeAyudaVistaProps {
  tema: TemaDeAyuda
  /** Dirección del índice de ayuda del área que la monta. */
  rutaIndice: string
}

export function TemaDeAyudaVista({ tema, rutaIndice }: TemaDeAyudaVistaProps) {
  const contenido: TemaDeAyudaDef = TEMAS[tema]
  return (
    <article className="flex max-w-3xl flex-col gap-4">
      <Link to={rutaIndice} className="text-sm underline">
        Volver a Ayuda
      </Link>
      <PageHeader titulo={contenido.titulo} />
      {contenido.secciones.map((seccion) => (
        <section key={seccion.titulo} className="flex flex-col gap-2">
          <h2 className="text-base font-semibold text-primary">{seccion.titulo}</h2>
          {seccion.parrafos.map((parrafo) => (
            <p key={parrafo} className="text-sm text-primary">
              {conEnfasis(parrafo)}
            </p>
          ))}
          {seccion.ejemplo && (
            <p className="rounded-md bg-surface-muted p-3 text-sm text-primary/80">{conEnfasis(seccion.ejemplo)}</p>
          )}
        </section>
      ))}
    </article>
  )
}

export default TemaDeAyudaVista
