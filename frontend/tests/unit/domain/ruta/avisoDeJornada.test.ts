/**
 * Change 22d, tarea 13.1 (spec `ruta/area-de-ruta`, «Vender y anular se cortan cuando la jornada
 * ya no está abierta»; `design.md` D9, aprobado en 0.2; cita RUT-05, RUT-09): el aviso según el
 * estado, siempre seguido de que lo vendido se sigue enviando.
 */
import { describe, expect, it } from 'vitest'

import {
  AVISO_FALTA_ENVIAR_ANTES_DE_LA_ENTREGA,
  AVISO_LO_YA_VENDIDO,
  textoDeJornadaNoAbierta,
} from '../../../../src/domain/ruta/avisoDeJornada'

describe('textoDeJornadaNoAbierta (D9)', () => {
  it.each([
    ['LIBERADA', 'Tu jornada fue liberada.'],
    ['EN_RENDICION', 'Tu jornada está en rendición.'],
    ['CERRADA', 'Tu jornada fue cerrada.'],
    ['DESCONOCIDO', 'Tu jornada ya no está abierta.'],
    // Change 24 (D10, aprobado en 0.2; RUT-05): el vendedor terminó el día en el teléfono.
    ['ENTREGADA', 'Terminaste el día. Pasá a rendir con tu supervisor.'],
  ] as const)('%s dice «%s»', (estado, esperado) => {
    expect(textoDeJornadaNoAbierta(estado)).toBe(esperado)
  })

  it('lo que falta enviar se envía antes de la entrega (change 24, D10)', () => {
    expect(AVISO_FALTA_ENVIAR_ANTES_DE_LA_ENTREGA).toBe('Lo que falta enviar se envía antes de la entrega.')
  })

  it('lo ya vendido se sigue enviando', () => {
    expect(AVISO_LO_YA_VENDIDO).toBe('Lo que ya vendiste y cobraste se sigue enviando.')
  })
})
