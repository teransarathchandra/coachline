import { expect, mock, test } from 'claude-code/testing'
import type { On } from 'claude-code'

// the test runner has timers; the hooks environment's typings do not declare them
declare const setTimeout: (fn: (value?: unknown) => void, ms: number) => unknown

const STATE = (over = {}) =>
  JSON.stringify({ ai: true, research: true, auto_open: true, session: 's1', entries: [], patterns: [], skill: null, notice: null, ...over })

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
// session.start leaves its pane.py run in the background (the first prompt never waits for it): let it finish
const settle = () => new Promise(r => setTimeout(r, 50))

test('opens the pane at session start on macOS', async ($, on) => {
  const w = world(on)
  await $.session.start(START)
  await settle()
  expect(w.opened).toEqual(['coachline'])
  expect(w.ran.some(a => a.includes('--json') && a.includes('s1'))).toBe(true)
})

test('does nothing on Windows', async ($, on) => {
  const w = world(on, { os: 'Windows_NT' })
  await $.session.start(START)
  await settle()
  await $.prompt.submit({ text: 'hi', wait: false, origin: { kind: 'composer' } })
  await settle()
  expect(w.opened).toEqual([])
  expect(w.ran).toEqual([])
})

test('skips headless sessions', async ($, on) => {
  const w = world(on)
  await $.session.start({ ...START, surface: null, isInteractive: false })
  await settle()
  await $.prompt.submit({ text: 'hi', wait: false, origin: { kind: 'composer' } })
  await settle()
  expect(w.opened).toEqual([])
  expect(w.ran).toEqual([])
})

test('does not open when auto-open is off', async ($, on) => {
  const w = world(on, { out: STATE({ auto_open: false }) })
  await $.session.start(START)
  await settle()
  await $.prompt.submit({ text: 'hi', wait: false, origin: { kind: 'composer' } })
  await settle()
  expect(w.opened).toEqual([])
})

test('opens again on a prompt while the pane is not placed', async ($, on) => {
  const w = world(on)
  await $.session.start(START)
  await settle()
  await $.prompt.submit({ text: 'hi', wait: false, origin: { kind: 'composer' } })
  await settle()
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
  await settle()
  exit = 1
  await $.prompt.submit({ text: 'hi', wait: false, origin: { kind: 'composer' } })
  await settle()
  const ui = await $.ui.mount({ plugin: 'coachline', surface: 'terminal', component: 'Pane', requestId: 'coachline', props: {} as never })
  expect(await ui.find({ text: /make the shoe site premium/ })).toBeDefined()
  expect(await ui.find({ text: /boom · run \/coach doctor/ })).toBeDefined()
})

const SUBMIT = { text: 'hi', wait: false, origin: { kind: 'composer' } } as const
const RESULT = (stdout: string, exitCode = 0) => ({
  value: { exitCode, stdout, stderr: exitCode ? 'boom' : '', isStdoutTruncated: false, isStderrTruncated: false },
})

function base(on: On) {
  mock.env(on, {})
  on('session.start', ($, e) => ({ cwd: e.cwd }))
  on('prompt.submit', ($, e) => ({ text: e.text }))
  on('turn.complete', () => ({ text: '' }))
  on('session.id', () => ({ value: 's1' }))
  on('ui.panes', () => ({ value: [] }))
}

test('runs one pane.py at a time and catches up once afterwards', async ($, on) => {
  base(on)
  on('ui.open', () => ({ value: { isPlaced: true } }))
  let running = 0
  let most = 0
  let runs = 0
  on('process.run', async ($, e) => {
    if (e.argv.includes('--version')) return RESULT('Python 3.13.0')
    runs += 1
    running += 1
    most = Math.max(most, running)
    await Promise.resolve()
    await Promise.resolve()
    running -= 1
    return RESULT(STATE())
  })
  await $.session.start(START)
  await settle()
  await Promise.all([$.prompt.submit(SUBMIT), $.prompt.submit(SUBMIT), $.prompt.submit(SUBMIT)])
  await settle()
  expect(most).toBe(1)
  expect(runs).toBeLessThanOrEqual(3)
})

test('opens the pane even without Python, so its error can be read', async ($, on) => {
  base(on)
  const opened: string[] = []
  on('ui.open', ($, e) => { opened.push(e.id); return { value: { isPlaced: true } } })
  on('process.run', () => { throw new Error('not found') })
  await $.session.start(START)
  await settle()
  expect(opened).toEqual(['coachline'])
})

test('asks for Python once, not on every prompt', async ($, on) => {
  base(on)
  on('ui.open', () => ({ value: { isPlaced: true } }))
  let asked = 0
  on('process.run', ($, e) => {
    if (e.argv.includes('--version')) asked += 1
    throw new Error('not found')
  })
  await $.session.start(START)
  await settle()
  await $.prompt.submit(SUBMIT)
  await settle()
  await $.prompt.submit(SUBMIT)
  expect(asked).toBe(2)          // python3, then python; never again this session
})

test('session start does not wait for pane.py', async ($, on) => {
  base(on)
  on('ui.open', () => ({ value: { isPlaced: true } }))
  let release: () => void = () => {}
  const held = new Promise<void>(r => { release = r })
  on('process.run', async ($, e) => {
    if (e.argv.includes('--version')) return RESULT('Python 3.13.0')
    await held
    return RESULT(STATE())
  })
  let started = false
  const start = $.session.start(START).then(() => { started = true })
  await Promise.race([start, new Promise(r => setTimeout(r, 200))])
  expect(started).toBe(true)
  release()
  await settle()
})

const NO_ANSWER = {
  ...ENTRY, glyph: '×', state: 'error', words: 'no answer yet, press e to retry',
  lines: [['prompt', 'head', 'Your prompt', '15:28 · × no answer yet', null], ['prompt', 'prompt', 'make the shoe site premium', '', null]],
}

test('Analyse is there whenever there is no enhanced prompt, and it names the session', async ($, on) => {
  base(on)
  on('ui.open', () => ({ value: { isPlaced: true } }))
  const ran: string[][] = []
  on('process.run', ($, e) => {
    ran.push([...e.argv])
    if (e.argv.includes('--version')) return RESULT('Python 3.13.0')
    return RESULT(e.argv.includes('--enhance') ? 'asking Claude' : STATE({ entries: [NO_ANSWER] }))
  })
  await $.session.start(START)
  await settle()
  await $.prompt.submit(SUBMIT)
  await settle()
  const ui = await $.ui.mount({ plugin: 'coachline', surface: 'terminal', component: 'Pane', requestId: 'coachline', props: {} as never })
  await ui.press({ key: 'analyse' })
  const enhance = ran.find(a => a.includes('--enhance'))
  expect(enhance).toBeDefined()
  expect(enhance?.slice(-4)).toEqual(['--enhance', 'k1', '--session', 's1'])
})

const WITH_WEB = {
  ...ENTRY, glyph: '✓', state: 'done', words: 'analysed', after: 'Do it.\n\nReferences (checked links from web research):\n- Use GreatKit: https://x.example.com/g',
  lines: [['prompt', 'head', 'Your prompt', '15:28 · ✓ analysed', null], ['web', 'better', '1. better: GreatKit (tool) - w', '', null],
          ['web', 'itemacts', '', '', 'item:x.example.com/g']],
}

test('Hide, I use this and Look again call pane.py with the item and the prompt', async ($, on) => {
  base(on)
  on('ui.open', () => ({ value: { isPlaced: true } }))
  const ran: string[][] = []
  on('process.run', ($, e) => {
    ran.push([...e.argv])
    if (e.argv.includes('--version')) return RESULT('Python 3.13.0')
    return RESULT(e.argv.includes('--mark') || e.argv.includes('--research') ? 'ok' : STATE({ entries: [WITH_WEB] }))
  })
  await $.session.start(START)
  await settle()
  await $.prompt.submit(SUBMIT)
  await settle()
  const ui = await $.ui.mount({ plugin: 'coachline', surface: 'terminal', component: 'Pane', requestId: 'coachline', props: {} as never })
  await ui.press({ key: 'hide:x.example.com/g' })
  await ui.press({ key: 'use:x.example.com/g' })
  await ui.press({ key: 'research' })
  const tail = (flag: string) => ran.find(a => a.includes(flag))?.slice(-3)
  expect(tail('dismissed')).toEqual(['--mark', 'dismissed', 'x.example.com/g'])
  expect(tail('adopted')).toEqual(['--mark', 'adopted', 'x.example.com/g'])
  expect(ran.find(a => a.includes('--research'))?.slice(-4)).toEqual(['--research', 'k1', '--session', 's1'])
})

test('Look again is not offered while web research is off', async ($, on) => {
  base(on)
  on('ui.open', () => ({ value: { isPlaced: true } }))
  const ran: string[][] = []
  on('process.run', ($, e) => {
    ran.push([...e.argv])
    if (e.argv.includes('--version')) return RESULT('Python 3.13.0')
    return RESULT(STATE({ entries: [WITH_WEB], research: false }))
  })
  await $.session.start(START)
  await settle()
  await $.prompt.submit(SUBMIT)
  await settle()
  const ui = await $.ui.mount({ plugin: 'coachline', surface: 'terminal', component: 'Pane', requestId: 'coachline', props: {} as never })
  let pressed = true
  try {
    await ui.press({ key: 'research' })
  } catch {
    pressed = false
  }
  expect(pressed).toBe(false)
  expect(ran.some(a => a.includes('--research'))).toBe(false)
})
