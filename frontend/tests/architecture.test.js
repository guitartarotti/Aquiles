import assert from 'node:assert/strict'
import { readdirSync, readFileSync, statSync } from 'node:fs'
import path from 'node:path'
import test from 'node:test'

import { parse } from 'espree'

const frontendRoot = path.resolve(import.meta.dirname, '..')
const srcRoot = path.join(frontendRoot, 'src')
const featureRoot = path.join(srcRoot, 'features')

function walk(root, extensions = new Set(['.js', '.vue'])) {
  return readdirSync(root, { withFileTypes: true }).flatMap(entry => {
    const target = path.join(root, entry.name)
    if (entry.isDirectory()) {
      return entry.name === 'vendor' ? [] : walk(target, extensions)
    }
    return extensions.has(path.extname(entry.name)) ? [target] : []
  })
}

function scriptSource(file) {
  const source = readFileSync(file, 'utf8')
  if (!file.endsWith('.vue')) return source
  return [...source.matchAll(/<script(?:\s+setup)?[^>]*>([\s\S]*?)<\/script>/gi)]
    .map(match => match[1])
    .join('\n')
}

function importsFor(file) {
  const source = scriptSource(file)
  const tree = parse(source, { ecmaVersion: 'latest', sourceType: 'module' })
  const imports = []

  function visit(node) {
    if (!node || typeof node !== 'object') return
    if (
      ['ImportDeclaration', 'ExportNamedDeclaration', 'ExportAllDeclaration'].includes(node.type)
      && typeof node.source?.value === 'string'
    ) {
      imports.push(node.source.value)
    }
    if (node.type === 'ImportExpression' && typeof node.source?.value === 'string') {
      imports.push(node.source.value)
    }
    for (const value of Object.values(node)) {
      if (Array.isArray(value)) value.forEach(visit)
      else if (value && typeof value === 'object') visit(value)
    }
  }

  visit(tree)
  return imports
}

function resolveLocalImport(fromFile, specifier) {
  let target
  if (specifier.startsWith('@/')) {
    target = path.join(srcRoot, specifier.slice(2))
  } else if (specifier.startsWith('.')) {
    target = path.resolve(path.dirname(fromFile), specifier)
  } else {
    return null
  }

  const candidates = [
    target,
    `${target}.js`,
    `${target}.vue`,
    path.join(target, 'index.js'),
  ]
  return candidates.find(candidate => {
    try {
      return statSync(candidate).isFile()
    } catch {
      return false
    }
  }) || null
}

test('feature folders own their API, components, and models', () => {
  for (const feature of ['funds-flow', 'macro-heatmap']) {
    const root = path.join(featureRoot, feature)
    for (const layer of ['api', 'components', 'models', 'tests']) {
      assert.equal(statSync(path.join(root, layer)).isDirectory(), true)
    }
  }

  for (const facade of [
    path.join(srcRoot, 'views', 'MacroHeatmapView.vue'),
    path.join(srcRoot, 'components', 'discovery', 'widgets', 'FundsFlowLocalWidget.vue'),
  ]) {
    assert.ok(readFileSync(facade, 'utf8').split(/\r?\n/).length <= 10)
  }
})

test('feature components respect progressive file-size budgets', () => {
  const legacyBudgets = new Map([
    ['features/funds-flow/components/EtfDailyFlowPanel.vue', 767],
    ['features/funds-flow/components/FundsFlowLocalWidget.vue', 6645],
    ['features/macro-heatmap/components/MacroHeatmapView.vue', 6691],
  ])
  const offenders = []

  for (const file of walk(featureRoot).filter(candidate => candidate.endsWith('.vue'))) {
    const relativePath = path.relative(srcRoot, file).replaceAll(path.sep, '/')
    const lines = readFileSync(file, 'utf8').split(/\r?\n/).length
    const budget = legacyBudgets.get(relativePath) ?? 500
    if (lines > budget) offenders.push(`${relativePath}: ${lines} > ${budget}`)
  }

  assert.deepEqual(offenders, [])
})

test('feature components do not call transports or global API modules directly', () => {
  const componentFiles = walk(featureRoot).filter(file => file.includes(`${path.sep}components${path.sep}`))
  const offenders = []

  for (const file of componentFiles) {
    const source = scriptSource(file)
    const forbiddenImports = importsFor(file).filter(specifier =>
      specifier === 'axios' || specifier === '@/api' || specifier.startsWith('@/api/'),
    )
    if (/\bfetch\s*\(|\baxios\s*\(/.test(source) || forbiddenImports.length) {
      offenders.push(path.relative(srcRoot, file))
    }
  }

  assert.deepEqual(offenders, [])
})

test('feature models remain pure and independent from UI and transport layers', () => {
  const modelFiles = walk(featureRoot).filter(file => file.includes(`${path.sep}models${path.sep}`))
  const offenders = []

  for (const file of modelFiles) {
    const forbidden = importsFor(file).filter(specifier =>
      specifier === 'vue'
      || specifier === 'vue-router'
      || specifier.includes('/api')
      || specifier.includes('/components'),
    )
    if (forbidden.length) {
      offenders.push(`${path.relative(srcRoot, file)} -> ${forbidden.join(', ')}`)
    }
  }

  assert.deepEqual(offenders, [])
})

test('frontend source dependency graph has no circular imports', () => {
  const files = walk(srcRoot)
  const graph = new Map(
    files.map(file => [file, importsFor(file).map(specifier => resolveLocalImport(file, specifier)).filter(Boolean)]),
  )
  const visited = new Set()
  const active = new Set()
  const stack = []
  const cycles = []

  function visit(file) {
    if (active.has(file)) {
      const start = stack.indexOf(file)
      cycles.push([...stack.slice(start), file].map(item => path.relative(srcRoot, item)).join(' -> '))
      return
    }
    if (visited.has(file)) return
    visited.add(file)
    active.add(file)
    stack.push(file)
    for (const dependency of graph.get(file) || []) visit(dependency)
    stack.pop()
    active.delete(file)
  }

  for (const file of files) visit(file)
  assert.deepEqual(cycles, [])
})
