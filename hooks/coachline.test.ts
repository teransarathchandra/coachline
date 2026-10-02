import { expect, mock, test } from 'claude-code/testing'
import type { On } from 'claude-code'

const STATE = (over = {}) =>
  JSON.stringify({ ai: true, auto_open: true, session: 's1', entries: [], patterns: [], skill: null, notice: null, ...over })

function world(on: On, opts: { os?: string; out?: string; exit?: number } = {}) {
  const opened: string[] = []
  const ran: string[][] = []
  mock.env(on, opts.os ? { OS: opts.os } : {})
  on('session.start', ($, e) => ({ cwd: e.cwd }))
  on('prompt.submit', ($, e) => ({ text: e.text }))
  on('turn.complete', () => ({ text: '' }))
  on('session.id', () => ({ value: 's1' }))
  on('ui.panes', () => ({ value: [] }))
  on('ui.open', ($, e) => {
    opened.push(e.id)
    return { value: { isPlaced: true } }
  })
  on('process.run', ($, e) => {
    ran.push([...e.argv])
    const version = e.argv.includes('--version')
    return {
      value: {
        exitCode: version ? 0 : (opts.exit ?? 0),
        stdout: version ? 'Python 3.13.0' : (opts.out ?? STATE()),
        stderr: opts.exit ? 'Traceback\nboom' : '',
        isStdoutTruncated: false,
        isStderrTruncated: false,
      },
    }
  })
  return { opened, ran }
}

const START = { cwd: '/w', surface: 'terminal', isInteractive: true } as const

test('opens the pane at session start on macOS', async ($, on) => {
  const w = world(on)
  await $.session.start(START)
  expect(w.opened).toEqual(['coachline'])
  expect(w.ran.some(a => a.includes('--json') && a.includes('s1'))).toBe(true)
})

test('does nothing on Windows', async ($, on) => {
  const w = world(on, { os: 'Windows_NT' })
  await $.session.start(START)
  await $.prompt.submit({ text: 'hi', wait: false, origin: { kind: 'composer' } })
  expect(w.opened).toEqual([])
  expect(w.ran).toEqual([])
})

test('skips headless sessions', async ($, on) => {
  const w = world(on)
  await $.session.start({ ...START, surface: null, isInteractive: false })
  await $.prompt.submit({ text: 'hi', wait: false, origin: { kind: 'composer' } })
  expect(w.opened).toEqual([])
  expect(w.ran).toEqual([])
})

test('does not open when auto-open is off', async ($, on) => {
  const w = world(on, { out: STATE({ auto_open: false }) })
  await $.session.start(START)
  await $.prompt.submit({ text: 'hi', wait: false, origin: { kind: 'composer' } })
  expect(w.opened).toEqual([])
})

test('opens again on a prompt while the pane is not placed', async ($, on) => {
  const w = world(on)
  await $.session.start(START)
  await $.prompt.submit({ text: 'hi', wait: false, origin: { kind: 'composer' } })
  expect(w.opened).toEqual(['coachline', 'coachline'])
})

const ENTRY = {
  key: 'k1', stamp: '15:28', glyph: '!', state: 'local', words: 'can be improved', text: 'make the shoe site premium', after: '',
  lines: [['prompt', 'head', 'Your prompt', '15:28 · ! can be improved', null], ['prompt', 'prompt', 'make the shoe site premium', '', null]],
}

test('keeps the last good state when pane.py fails', async ($, on) => {
  let exit = 0
  mock.env(on, {})
  on('session.start', ($, e) => ({ cwd: e.cwd }))
  on('prompt.submit', ($, e) => ({ text: e.text }))
  on('session.id', () => ({ value: 's1' }))
  on('ui.panes', () => ({ value: [{ id: 'coachline', title: 'coachline', isShown: true, isFocused: false, isPlaced: true }] }))
  on('ui.open', () => ({ value: { isPlaced: true } }))
  on('process.run', ($, e) => ({
    value: {
      exitCode: e.argv.includes('--version') ? 0 : exit,
      stdout: e.argv.includes('--version') ? 'Python 3.13.0' : STATE({ entries: [ENTRY] }),
      stderr: exit ? 'Traceback\nboom' : '',
      isStdoutTruncated: false,
      isStderrTruncated: false,
    },
  }))
  await $.session.start(START)
  exit = 1
  await $.prompt.submit({ text: 'hi', wait: false, origin: { kind: 'composer' } })
  const ui = await $.ui.mount({ plugin: 'coachline', surface: 'terminal', component: 'Pane', requestId: 'coachline', props: {} as never })
  expect(await ui.find({ text: /make the shoe site premium/ })).toBeDefined()
  expect(await ui.find({ text: /boom · run \/coach doctor/ })).toBeDefined()
})
