import { PageHeader } from '../../../components/ui/PageHeader'

export const SIN_PERMISO_DE_LECTURA_DE_COBRANZAS = 'No tenés permiso para ver las cobranzas.'

/** Falta de permiso del listado y del detalle (D14: `REGISTRAR_COBRANZA` o `ANULAR_COBRANZA`). */
export function CobranzasSinPermiso({ titulo }: { titulo: string }) {
  return (
    <main className="flex flex-col gap-4">
      <PageHeader titulo={titulo} />
      <p className="text-sm text-primary/70">{SIN_PERMISO_DE_LECTURA_DE_COBRANZAS}</p>
    </main>
  )
}
