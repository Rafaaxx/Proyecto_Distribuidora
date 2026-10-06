import { PageHeader } from '../../../components/ui/PageHeader'

export const SIN_PERMISO_DE_LECTURA_DE_PAGOS = 'No tenés permiso para ver los pagos a proveedores.'

/** Falta de permiso del listado y del detalle (D7: `REGISTRAR_PAGO_PROVEEDOR` o `ANULAR_PAGO_PROVEEDOR`). */
export function PagosSinPermiso({ titulo }: { titulo: string }) {
  return (
    <main className="flex flex-col gap-4">
      <PageHeader titulo={titulo} />
      <p className="text-sm text-primary/70">{SIN_PERMISO_DE_LECTURA_DE_PAGOS}</p>
    </main>
  )
}
