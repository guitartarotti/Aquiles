import assert from 'node:assert/strict'
import { readFile, readdir } from 'node:fs/promises'
import path from 'node:path'
import test from 'node:test'
import { fileURLToPath } from 'node:url'

const frontendRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const repositoryRoot = path.resolve(frontendRoot, '..')
const textExtensions = new Set(['.html', '.js', '.json', '.md', '.py', '.toml', '.vue'])
const activeTargets = [
  path.join(repositoryRoot, 'aquiles.ps1'),
  path.join(repositoryRoot, 'backend', 'app'),
  path.join(repositoryRoot, 'backend', 'requirements.txt'),
  path.join(repositoryRoot, 'backend', 'run.py'),
  path.join(repositoryRoot, 'frontend', 'index.html'),
  path.join(repositoryRoot, 'frontend', 'src'),
  path.join(repositoryRoot, 'graphiti-local'),
  path.join(repositoryRoot, 'locales'),
]

async function collectTextFiles(target) {
  const entries = await readdir(target, { withFileTypes: true }).catch(() => null)
  if (!entries) return textExtensions.has(path.extname(target)) ? [target] : []

  const files = await Promise.all(entries.map(entry => {
    const entryPath = path.join(target, entry.name)
    return entry.isDirectory() ? collectTextFiles(entryPath) : [entryPath]
  }))
  return files.flat().filter(file => textExtensions.has(path.extname(file)))
}

test('active product surfaces use Aquiles as the only identity', async () => {
  const files = (await Promise.all(activeTargets.map(collectTextFiles))).flat()
  const violations = []

  for (const file of files) {
    const content = await readFile(file, 'utf8')
    if (/miro\s?fish/i.test(content)) {
      violations.push(path.relative(repositoryRoot, file))
    }
  }

  assert.deepEqual(violations, [])
})

test('historical attribution remains explicit and separate', async () => {
  const notice = await readFile(path.join(repositoryRoot, 'NOTICE.md'), 'utf8')
  const readme = await readFile(path.join(repositoryRoot, 'README.md'), 'utf8')

  assert.match(notice, /MiroFish project/)
  assert.match(notice, /historical attribution only/)
  assert.match(readme, /Aquiles é a identidade única/)
  assert.match(readme, /NOTICE\.md/)
})
