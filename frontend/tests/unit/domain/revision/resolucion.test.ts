import { describe, expect, it } from 'vitest'

import {
  LIMITE_DE_COMENTARIO,
  comentarioDeResolucion,
  textoDeConfirmacionDeAvisos,
  textoDeResolucion,
  textoDeResolverAvisos,
} from '../../../../src/domain/revision/resolucion'

/** Change 25, tareas 13.2 y 15.2 (D1, D11, D12; SYN-08): textos y reglas de la resolución. */
describe('resolución de observaciones (SYN-08)', () => {
  it('el comentario se recorta y debe tener de 1 a 500 caracteres', () => {
    expect(LIMITE_DE_COMENTARIO).toBe(500)
    expect(comentarioDeResolucion('  Se corrigió  ')).toBe('Se corrigió')
    expect(comentarioDeResolucion('   ')).toBeNull()
    expect(comentarioDeResolucion('')).toBeNull()
    expect(comentarioDeResolucion('x'.repeat(500))).toBe('x'.repeat(500))
    expect(comentarioDeResolucion('x'.repeat(501))).toBeNull()
  })

  it('«Resolver {N} avisos» y su confirmación, con el singular de uno', () => {
    expect(textoDeResolverAvisos(3)).toBe('Resolver 3 avisos')
    expect(textoDeResolverAvisos(1)).toBe('Resolver 1 aviso')
    expect(textoDeConfirmacionDeAvisos(2)).toBe('¿Resolver 2 avisos con este comentario? No se puede deshacer.')
    expect(textoDeConfirmacionDeAvisos(1)).toBe('¿Resolver 1 aviso con este comentario? No se puede deshacer.')
  })

  it('«Resuelta por {usuario} el {fecha}: {comentario}»', () => {
    const texto = textoDeResolucion({
      resuelto_por_nombre: 'Marta',
      resuelto_en: '2026-11-05T12:00:00Z',
      comentario: 'Se corrigió con un ajuste',
    })
    expect(texto).toMatch(/^Resuelta por Marta el \d{2}\/\d{2}\/\d{4} \d{2}:\d{2}: Se corrigió con un ajuste$/)
  })

  it('sin nombre del usuario o sin datos, no inventa', () => {
    expect(textoDeResolucion({ resuelto_por_nombre: null, resuelto_en: '2026-11-05T12:00:00Z', comentario: 'Listo' })).toMatch(
      /^Resuelta el \d{2}\/\d{2}\/\d{4} \d{2}:\d{2}: Listo$/,
    )
    expect(textoDeResolucion({ resuelto_por_nombre: 'Marta', resuelto_en: null, comentario: null })).toBe('Resuelta por Marta')
  })
})
