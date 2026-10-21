import { PageHeader } from '../../../components/ui/PageHeader'

export const SIN_PERMISO_DE_LECTURA_DE_VENTAS = 'No tenés permiso para ver las ventas.'
export const SIN_PERMISO_PARA_VENDER = 'No tenés permiso para vender.'

/** Falta de permiso del listado y del detalle (D19: `VENDER` o `ANULAR_VENTA`). */
export function VentasSinPermiso({ titulo, mensaje = SIN_PERMISO_DE_LECTURA_DE_VENTAS }: { titulo: string; mensaje?: string }) {
  return (
    <main className="flex flex-col gap-4">
      <PageHeader titulo={titulo} />
      <p className="text-sm text-primary/70">{mensaje}</p>
    </main>
  )
}
