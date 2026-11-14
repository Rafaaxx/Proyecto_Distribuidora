import { Link } from 'react-router-dom'

import { clasesDeBoton } from '../components/ui/botonEstilos'
import { useTituloDePagina } from '../lib/useTituloDePagina'

/** Documento legal público todavía sin redactar: «Próximamente» y un botón para volver a `/`. */
function PaginaLegalPendiente({ titulo }: { titulo: string }) {
  useTituloDePagina(titulo)

  return (
    <div className="min-h-screen bg-gradient-to-b from-surface-muted to-surface text-base">
      <main className="mx-auto flex w-full max-w-3xl flex-col gap-6 px-4 py-16 md:py-28">
        <p className="text-sm font-semibold uppercase tracking-wider text-primary">Distribuidora</p>
        <h1 className="text-3xl font-bold tracking-tight text-primary md:text-5xl">{titulo}</h1>
        <div className="rounded-lg border border-border bg-surface p-6 shadow-sm">
          <p className="text-xl font-semibold text-primary">Próximamente</p>
          <p className="mt-2">Estamos preparando este documento.</p>
        </div>
        <Link to="/" className={`${clasesDeBoton('primario', 'grande')} px-6 py-3 sm:self-start`}>
          Volver al inicio
        </Link>
      </main>
    </div>
  )
}

export function PaginaPrivacidad() {
  return <PaginaLegalPendiente titulo="Política de privacidad" />
}

export function PaginaTerminos() {
  return <PaginaLegalPendiente titulo="Términos y condiciones" />
}
