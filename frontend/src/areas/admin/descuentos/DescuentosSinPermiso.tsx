import { PageHeader } from '../../../components/ui/PageHeader'

export const SIN_PERMISO_DE_DESCUENTOS = 'No tenés permiso para ver los descuentos.'
export const SIN_PERMISO_DE_TOPES = 'No tenés permiso para definir los topes de descuento.'

/** Falta de permiso de las pantallas de `/admin/descuentos` (`GESTIONAR_DESCUENTOS` o `ADMIN_USUARIOS`). */
export function DescuentosSinPermiso({
  titulo,
  mensaje = SIN_PERMISO_DE_DESCUENTOS,
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
