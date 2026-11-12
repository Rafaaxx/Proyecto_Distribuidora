import { describe, expect, it } from 'vitest'

import { esquemaLogin } from '../../../../src/domain/identidad/loginSchema'

/**
 * Change 27a, ajuste de la prueba manual (D18, enmienda de ADR-057): el teclado del teléfono agrega
 * un espacio al final de lo escrito. Organización y usuario se recortan antes de enviarse; la
 * contraseña nunca se toca. El backend sigue comparando tal cual.
 */
describe('esquemaLogin: recorte de espacios', () => {
  it('recorta los espacios de los extremos de organización y usuario', () => {
    const r = esquemaLogin.parse({
      organizacionSlug: 'organizacion-inicial ',
      usuario: '  admin\t',
      contrasena: 'x',
    })
    expect(r.organizacionSlug).toBe('organizacion-inicial')
    expect(r.usuario).toBe('admin')
  })

  it('no recorta la contraseña', () => {
    const r = esquemaLogin.parse({ organizacionSlug: 'org', usuario: 'u', contrasena: ' clave con espacios ' })
    expect(r.contrasena).toBe(' clave con espacios ')
  })

  it('no toca los espacios del medio', () => {
    const r = esquemaLogin.parse({ organizacionSlug: 'org', usuario: 'juan perez ', contrasena: 'x' })
    expect(r.usuario).toBe('juan perez')
  })

  it('una organización o usuario de solo espacios cuenta como vacío', () => {
    const r = esquemaLogin.safeParse({ organizacionSlug: '   ', usuario: ' ', contrasena: 'x' })
    expect(r.success).toBe(false)
    expect(r.error?.issues.map((i) => i.message)).toEqual([
      'Ingresá el identificador de la organización.',
      'Ingresá el usuario.',
    ])
  })
})
