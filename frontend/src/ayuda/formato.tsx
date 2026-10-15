import type { ReactNode } from 'react'

/**
 * Convierte el texto plano de `textos.ts` en nodos de React: `**x**` es negrita y `*x*` es
 * cursiva. Todo lo demás se escribe como texto (React lo escapa): no hay HTML crudo.
 */
const MARCAS = /(\*\*[^*]+\*\*|\*[^*]+\*)/g

export function conEnfasis(texto: string): ReactNode[] {
  return texto
    .split(MARCAS)
    .filter((trozo) => trozo !== '')
    .map((trozo, indice) => {
      if (trozo.startsWith('**') && trozo.endsWith('**') && trozo.length > 4) {
        return <strong key={indice}>{trozo.slice(2, -2)}</strong>
      }
      if (trozo.startsWith('*') && trozo.endsWith('*') && trozo.length > 2) {
        return <em key={indice}>{trozo.slice(1, -1)}</em>
      }
      return trozo
    })
}
