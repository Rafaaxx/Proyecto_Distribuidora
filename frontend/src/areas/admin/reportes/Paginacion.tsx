import { Boton } from '../../../components/ui/Button'
import { navegacionDe } from '../../../domain/reportes/paginacion'

/**
 * Navegación de una lista paginada de los reportes (change 26, D14): «Anterior», «Página {n} de {m}» y
 * «Siguiente». Todo lo que decide (si se muestra, qué botón se habilita, el texto) sale de `navegacionDe`; acá solo
 * se dibuja. `etiqueta` es el nombre de la lista, para distinguir las navegaciones de una pestaña con varias.
 */
export function Paginacion({
  pagina,
  paginas,
  alCambiar,
  etiqueta,
}: {
  pagina: number
  paginas: number
  alCambiar: (pagina: number) => void
  etiqueta: string
}) {
  const navegacion = navegacionDe({ pagina, paginas })
  if (!navegacion.visible) return null
  return (
    <nav aria-label={`Paginación de ${etiqueta}`} className="flex items-center justify-end gap-3 text-sm">
      <Boton variante="secundario" disabled={!navegacion.anteriorHabilitado} onClick={() => alCambiar(pagina - 1)}>
        Anterior
      </Boton>
      <span>{navegacion.texto}</span>
      <Boton variante="secundario" disabled={!navegacion.siguienteHabilitado} onClick={() => alCambiar(pagina + 1)}>
        Siguiente
      </Boton>
    </nav>
  )
}
