import { useState } from 'react'

import { Alert } from '../../../components/ui/Alert'
import { Ayuda } from '../../../components/ui/Ayuda'
import { Boton } from '../../../components/ui/Button'
import { usePermisos } from '../../../features/identidad/usePermisos'
import { useNotaDeVenta } from '../../../features/ventas/hooks'
import { compartirNota, descargarNota, nombreDeArchivoDeNota, puedeCompartirArchivos } from '../../../lib/nota/compartir'

export const AVISO_NOTA_MODO_C = 'La nota de venta todavía no está disponible para ventas con IVA incluido (modo C).'
const AVISO_DE_LECTURA = 'No se pudo preparar la nota de venta.'
const AVISO_DE_PDF = 'No se pudo generar el PDF de la nota. Podés reintentar.'
const AVISO_DE_COMPARTIR = 'No se pudo compartir la nota. Podés descargarla y enviarla desde ahí.'

/** El navegador comparte archivos PDF (Web Share API con archivos, ADR-008, D9). */
function navegadorComparteArchivos(numero: string): boolean {
  return puedeCompartirArchivos(new File([], nombreDeArchivoDeNota(numero), { type: 'application/pdf' }))
}

/**
 * Acciones de la nota de venta de una venta (change 20, tarea 7.2; VTA-13, SEG-06, ADR-008,
 * ADR-059; D6, D9, D14): "Compartir nota" (solo si el navegador comparte archivos) y "Descargar
 * nota". Sin `VENDER` ni `ANULAR_VENTA` no se monta ni pide nada. La nota de una venta de modo C
 * todavía no está disponible: se avisa y no hay botones. Sin lógica de negocio: el contenido se
 * arma en `domain/ventas/notaDeVenta.ts` y el PDF en `lib/nota/`.
 */
export function NotaDeVentaAcciones({ ventaId }: { ventaId: string }) {
  const { tiene } = usePermisos()
  const permitida = tiene('VENDER') || tiene('ANULAR_VENTA')
  const nota = useNotaDeVenta(ventaId, permitida)
  const [ocupada, setOcupada] = useState(false)
  const [aviso, setAviso] = useState<string | null>(null)

  if (!permitida) return null
  if (nota.estado === 'cargando') return <p className="text-sm text-primary/70">Preparando la nota de venta…</p>
  if (nota.estado === 'no-disponible') {
    return (
      <p className="text-sm text-primary/70" data-testid="nota-no-disponible">
        {AVISO_NOTA_MODO_C}
      </p>
    )
  }
  if (nota.estado === 'error') {
    return (
      <div className="flex flex-col gap-2" data-testid="nota-con-error">
        <Alert>{AVISO_DE_LECTURA}</Alert>
        <div>
          <Boton variante="secundario" onClick={nota.reintentar}>
            Reintentar
          </Boton>
        </div>
      </div>
    )
  }

  const { numero, anulada, generarPdf } = nota
  const accion = async (hacer: (pdf: Blob) => Promise<string | null> | string | null) => {
    setOcupada(true)
    setAviso(null)
    try {
      const pdf = await generarPdf().catch(() => null)
      if (pdf === null) setAviso(AVISO_DE_PDF)
      else setAviso(await hacer(pdf))
    } finally {
      setOcupada(false)
    }
  }
  const descargar = () =>
    accion((pdf) => {
      descargarNota(pdf, numero)
      return null
    })
  const compartir = () => accion(async (pdf) => ((await compartirNota(pdf, numero)) === 'fallo' ? AVISO_DE_COMPARTIR : null))

  return (
    <div className="flex flex-col gap-2" data-testid="acciones-de-la-nota">
      {aviso && <Alert>{aviso}</Alert>}
      <div className="flex flex-wrap items-center gap-2">
        {navegadorComparteArchivos(numero) && (
          <Boton variante="secundario" disabled={ocupada} onClick={() => void compartir()}>
            Compartir nota
          </Boton>
        )}
        <span className="flex items-center gap-1">
          <Boton variante="secundario" disabled={ocupada} onClick={() => void descargar()}>
            Descargar nota
          </Boton>
          <Ayuda clave="ventas.notaDeVenta" />
        </span>
        {anulada && <Ayuda clave="ventas.notaAnulada" />}
      </div>
    </div>
  )
}
