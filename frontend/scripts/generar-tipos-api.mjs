#!/usr/bin/env node
/**
 * Regenera `src/api/schema.gen.ts` desde el OpenAPI del backend
 * (`docs/02-arquitectura.md` §11, tarea 13.1 del change 03).
 *
 * Reemplaza el uso directo de `python` en `package.json`: en esta máquina
 * (y en general fuera de CI) `python` puede resolver a un Python de
 * sistema sin las dependencias del backend (p.ej. psycopg), mientras que
 * `backend/.venv` sí las tiene. Este script prefiere el intérprete del
 * venv del backend si existe y cae a `python` del PATH si no (caso de
 * CI: el workflow instala las dependencias globalmente con
 * `pip install -r requirements-dev.txt`, sin crear un venv).
 */
import { spawn } from 'node:child_process'
import { existsSync } from 'node:fs'
import { platform } from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const directorioFrontend = path.dirname(path.dirname(fileURLToPath(import.meta.url)))
const directorioBackend = path.join(directorioFrontend, '..', 'backend')

function resolverPythonDelVenv() {
  const ejecutable = platform() === 'win32' ? path.join('Scripts', 'python.exe') : path.join('bin', 'python')
  const candidato = path.join(directorioBackend, '.venv', ejecutable)
  return existsSync(candidato) ? candidato : 'python'
}

function ejecutar(comando, args, opciones) {
  return new Promise((resolve, reject) => {
    const proceso = spawn(comando, args, { stdio: 'inherit', shell: false, ...opciones })
    proceso.on('error', reject)
    proceso.on('exit', (codigo) => {
      if (codigo === 0) {
        resolve(undefined)
      } else {
        reject(new Error(`${comando} ${args.join(' ')} terminó con código ${codigo}`))
      }
    })
  })
}

async function main() {
  const python = resolverPythonDelVenv()

  await ejecutar(python, ['-m', 'scripts.export_openapi'], { cwd: directorioBackend })

  await ejecutar(
    'npx',
    ['openapi-typescript', path.join('..', 'backend', 'openapi.json'), '-o', path.join('src', 'api', 'schema.gen.ts')],
    { cwd: directorioFrontend, shell: platform() === 'win32' },
  )
}

main().catch((error) => {
  console.error(error.message)
  process.exitCode = 1
})
