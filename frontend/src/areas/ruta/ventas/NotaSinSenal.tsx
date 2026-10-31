import { useState } from 'react'

import { Alert } from '../../../components/ui/Alert'
import { Ayuda } from '../../../components/ui/Ayuda'
import { Boton } from '../../../components/ui/Button'
import { armarNotaDeVenta, NotaNoDisponibleParaModoC } from '../../../domain/ventas/notaDeVenta'
import { datosDeNotaDesdeLocal } from '../../../domain/ventas/notaDesdeLocal'
import type { VentaLocal } from '../../../lib/dispositivo/db'
import { compartirNota, descargarNota, nombreDeArchivoDeNota, puedeCompartirArchivos } from '../../../lib/nota/compartir'
import { generarPdfDeNota } from '../../../lib/nota/pdf'

const AVISO_DE_PDF = 'No se pudo generar el PDF de la nota. Podés reintentar.'
const AVISO_DE_COMPARTIR = 'No se pudo compartir la nota. Podés descargarla y enviarla desde ahí.'

/** El navegador comparte archivos PDF (Web Share API con archivos, ADR-008). */
function navegadorComparteArchivos(numero: string): boolean {
  return puedeCompartirArchivos(new File([], nombreDeArchivoDeNota(numero), { type: 'application/pdf' }))
}

/**
 * Acciones de la nota de una venta del teléfono (change 22a, tarea 12.2; `design.md` D15; VTA-13,
 * ADR-059, `00` §9 criterio 7): "Compartir nota" (solo si el navegador comparte archivos) y
 * "Descargar nota", sin conexión. El contenido sale de los datos congelados de la venta local
 * (`datosDeNotaDesdeLocal`) y se arma con la misma función que `/admin`; el PDF, con `lib/nota/`.
 * Sin lógica de negocio: solo orquesta.
 */
export function NotaSinSenal({ venta }: { venta: VentaLocal }) {
  const [ocupada, setOcupada] = useState(false)
  const [aviso, setAviso] = useState<string | null>(null)

  const generar = async (): Promise<Blob | null> => {
    try {
      return await generarPdfDeNota(armarNotaDeVenta(datosDeNotaDesdeLocal(venta)))
    } catch (error) {
      setAviso(error instanceof NotaNoDisponibleParaModoC ? error.message : AVISO_DE_PDF)
      return null
    }
  }

  const accion = async (hacer: (pdf: Blob) => Promise<string | null> | string | null) => {
    setOcupada(true)
    setAviso(null)
    try {
      const pdf = await generar()
      if (pdf !== null) setAviso(await hacer(pdf))
    } finally {
      setOcupada(false)
    }
  }

  const descargar = () =>
    accion((pdf) => {
      descargarNota(pdf, venta.numero)
      return null
    })
  const compartir = () =>
    accion(async (pdf) => ((await compartirNota(pdf, venta.numero)) === 'fallo' ? AVISO_DE_COMPARTIR : null))

  return (
    <div className="flex flex-col gap-2" data-testid="acciones-de-la-nota">
      {aviso && <Alert>{aviso}</Alert>}
      <div className="flex flex-wrap items-center gap-2">
        {navegadorComparteArchivos(venta.numero) && (
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
      </div>
    </div>
  )
}
