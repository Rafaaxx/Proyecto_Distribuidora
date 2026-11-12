import { PageHeader } from '../../../components/ui/PageHeader'

export const SIN_PERMISO_DE_LISTAS = 'No tenés permiso para ver las listas de precios.'
export const SIN_PERMISO_PARA_GESTIONAR_LISTAS = 'No tenés permiso para gestionar listas de precios.'

/** Falta de permiso de las pantallas de `/admin/precios` (`GESTIONAR_LISTAS` o `PUBLICAR_LISTAS`). */
export function PreciosSinPermiso({
  titulo,
  mensaje = SIN_PERMISO_DE_LISTAS,
}: {
  titulo: string
  mensaje?: string
}) {
  return (
    <main className="flex flex-col gap-4">
      <PageHeader titulo={titulo} />
      <p className="text-sm text-primary/70">{mensaje}</p>
    </main>
  )
}
