import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register, RenderChildren } from 'claude-code'

import type { PaneEntry, PaneLine, PaneState } from '../types'

const PANE = 'coachline'
const NO_PYTHON = 'coachline needs Python 3.9+ · run /coach doctor'
const NO_CLIPBOARD = 'no clipboard here: select the text instead'

const state = atom({ plugin: 'coachline', key: 'state' } as const, null as PaneState | null)
const error = atom({ plugin: 'coachline', key: 'error' } as const, '')
const sel = atom({ plugin: 'coachline', key: 'sel' } as const, -1)
const full = atom({ plugin: 'coachline', key: 'full' } as const, false)
const showPatterns = atom({ plugin: 'coachline', key: 'showPatterns' } as const, false)
const closed = atom({ plugin: 'coachline', key: 'closed' } as const, false)
const msg = atom({ plugin: 'coachline', key: 'msg' } as const, '')

// watch.py's colours (see CODE in scripts/watch.py): text by line kind, and each section's box and title by section
const COLOR: Record<string, string> = {
  prompt: 'whiteBright', blue: 'blueBright', bluedim: 'blueBright', enh: 'cyanBright', task: 'blueBright', meta: 'gray',
  better: 'magentaBright', src: 'gray',
}
const SECTION_COLOR: Record<string, string> = {
  prompt: 'whiteBright', improve: 'blueBright', enh: 'cyanBright', web: 'magentaBright', info: 'gray', bad: 'redBright',
}

// discover.item_lines: "1. better: Name (kind) · you use this - why"
const FIND = /^(\d+\. )better: (.+?) \(([a-z]+)\)( · you use this)? - (.*)$/s

type Section = { section: string; head: PaneLine | null; rows: PaneLine[] }

// watch.py's boxed(): a section's title opens its box, and a blank line, a new title or another section closes it
function sections(lines: PaneLine[]): Section[] {
  const out: Section[] = []
  let cur: Section | null = null
  for (const l of lines) {
    const [section, kind] = l
    if (cur && (kind === 'blank' || section !== cur.section || kind === 'head')) cur = null
    if (kind === 'blank') continue
    if (!cur) {
      cur = { section, head: kind === 'head' ? l : null, rows: [] }
      out.push(cur)
      if (kind === 'head') continue
    }
    cur.rows.push(l)
  }
  return out
}

// Background work can outlive the module (a reload, the session ending): nothing is left to report to then.
const ignore = () => undefined

type Run = { ok: true; out: string } | { ok: false; err: string }

let active = false          // an interactive session on macOS / Linux; false under `claude -p`, the SDK and on Windows
let py: string | null = null
let pyChecked = false         // asked once: on a Mac without developer tools, each `python3` call can raise the install dialog
let inflight: Promise<PaneState | null> | null = null
let again = false
let width = 80
let poll: { cancel: () => void } | null = null

async function python($: EngineInterface): Promise<string | null> {
  if (pyChecked) return py
  pyChecked = true
  for (const name of ['python3', 'python']) {
    try {
      const r = await $.process.run([name, '--version'], { timeoutMs: 5000 })
      if (r.exitCode === 0) return (py = name)
    } catch {
      // not on PATH: try the next name
    }
  }
  return null
}

async function run($: EngineInterface, args: string[]): Promise<Run> {
  const p = await python($)
  if (!p) return { ok: false, err: NO_PYTHON }
  try {
    const r = await $.process.run([p, `${$.plugin.root}/scripts/pane.py`, ...args], { timeoutMs: 20000 })
    if (r.exitCode !== 0) {
      const last = r.stderr.trim().split('\n').pop() || `pane.py exited ${r.exitCode}`
      return { ok: false, err: `coachline: ${last} · run /coach doctor` }
    }
    return { ok: true, out: r.stdout }
  } catch (x) {
    return { ok: false, err: `coachline: ${String(x)} · run /coach doctor` }
  }
}

// One pane.py at a time: a refresh asked for while one runs is folded into a single rerun when it ends.
async function refresh($: EngineInterface): Promise<PaneState | null> {
  if (inflight) {
    again = true
    return inflight
  }
  inflight = (async () => {
    let s: PaneState | null = null
    do {
      again = false
      s = await refreshOnce($)
    } while (again)
    return s
  })()
  try {
    return await inflight
  } finally {
    inflight = null
  }
}

async function refreshOnce($: EngineInterface): Promise<PaneState | null> {
  // --width 0: unwrapped. The pane may sit beside the conversation, narrower than the viewport's columns, so its Text wraps each line
  const r = await run($, ['--json', '--session', await $.session.id(), '--width', '0'])
  let s: PaneState | null = null
  if (r.ok) {
    try {
      s = JSON.parse(r.out) as PaneState
    } catch {
      await update($, error, () => 'coachline: pane.py gave a bad answer · run /coach doctor')
      return null
    }
  } else {
    await update($, error, () => r.err)       // the last good state stays
    return null
  }
  await update($, error, () => '')
  await update($, state, () => s)
  const busy = s.entries.some(e => e.state === 'pending')
  if (busy && !poll) poll = $.clock.every(3000, () => void refresh($).catch(ignore))
  if (!busy && poll) {
    poll.cancel()
    poll = null
  }
  return s
}

// Opens when the last answer says auto-open is on, or when there is no answer at all (no Python, pane.py failing): the pane then
// shows why, and the person can close it.
async function openIfWanted($: EngineInterface, s: PaneState | null): Promise<void> {
  if (s ? s.auto_open : (await read($, state)) === null) await open($)
}

async function startUp($: EngineInterface): Promise<void> {
  await openIfWanted($, await refresh($))
}

async function open($: EngineInterface): Promise<void> {
  if (await read($, closed)) return
  const panes = await $.ui.panes()
  if (panes.some((p: { id: string; isPlaced: boolean }) => p.id === PANE && p.isPlaced)) return
  await $.ui.open({ id: PANE, title: 'coachline' })
}

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    const r = await next(e)
    active = e.isInteractive && (await $.env.get('OS')) !== 'Windows_NT'
    if (!active) return r
    void startUp($).catch(ignore)              // the first prompt never waits for pane.py
    return r
  })

  on('prompt.submit', async ($, e, next) => {
    const r = await next(e)
    if (!active) return r
    await update($, sel, () => -1)             // follow the newest prompt
    let s = await read($, state)
    if (!s && inflight) s = await inflight     // the session start's first answer, if it is still coming
    await openIfWanted($, s)                   // from a prompt the person entered: placed at any width
    void refresh($).catch(ignore)
    return r
  })

  on('turn.complete', async ($, e, next) => {
    const r = await next(e)
    if (active) await refresh($)
    return r
  })

  on('ui.close', async ($, e, next) => {
    if (e.id === PANE && e.origin.kind === 'person') await update($, closed, () => true)
    return next(e)
  })

  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const { Box, Button, Text } = $.ui.resolve(e)
    width = e.viewport?.columns ?? width
    const s = await read($, state)
    const err = await read($, error)
    const note = await read($, msg)
    if (!s) return <Text dimColor>{err || 'coachline: loading…'}</Text>

    const header = (
      <Box key="header">
        <Text bold>coachline · this thread · {s.entries.length} prompt{s.entries.length === 1 ? '' : 's'}</Text>
        <Text>{'  '}</Text>
        <Text color={s.ai ? 'green' : 'gray'}>{s.ai ? '● Claude on' : '○ Claude off'}</Text>
      </Box>
    )
    const footer = [
      err ? <Text key="err" color="red">{err}</Text> : null,
      note ? <Text key="msg" dimColor>{note}</Text> : null,
      s.notice && !s.entries.length ? <Text key="notice" dimColor>{s.notice}</Text> : null,
    ]
    if (!s.entries.length) {
      return (
        <Box flexDirection="column">
          {header}
          <Text dimColor>Send a prompt: coachline coaches it here.</Text>
          {footer}
        </Box>
      )
    }

    const at = await read($, sel)
    const i = at < 0 || at >= s.entries.length ? s.entries.length - 1 : at
    const cur: PaneEntry | undefined = s.entries[i]
    if (!cur) return <Text dimColor>coachline: loading…</Text>
    const isFull = await read($, full)
    const pats = await read($, showPatterns)

    const copy = async () => {
      const r = await $.ui.copy({ text: cur.after, surface: e.surface })
      await update($, msg, () => (r.isCopied ? `copied the enhanced prompt (${cur.after.length} characters)` : NO_CLIPBOARD))
    }
    const analyse = async () => {
      const r = await run($, s.session ? ['--enhance', cur.key, '--session', s.session] : ['--enhance', cur.key])
      await update($, msg, () => (r.ok ? r.out.trim() : r.err))
      await refresh($)
    }
    const mark = async (status: 'dismissed' | 'adopted', id: string) => {
      const r = await run($, ['--mark', status, id])
      await update($, msg, () => (r.ok ? r.out.trim() : r.err))
      await refresh($)
    }
    const research = async () => {
      const r = await run($, s.session ? ['--research', cur.key, '--session', s.session] : ['--research', cur.key])
      await update($, msg, () => (r.ok ? r.out.trim() : r.err))
    }
    const install = async () => {
      if (!s.skill) return
      const r = await run($, ['--install', s.skill])
      await update($, msg, () => (r.ok ? r.out.trim() : r.err))
    }

    const line = (l: PaneLine, n: number) => {
      const [, kind, text, , action] = l
      if (kind === 'itemacts' && action?.startsWith('item:')) {
        const id = action.slice('item:'.length)
        return (
          <Box key={`l${n}`} paddingLeft={3}>
            <Button key={`hide:${id}`} label="Hide" onPress={() => mark('dismissed', id)} />
            <Text>{'  '}</Text>
            <Button key={`use:${id}`} label="I use this" onPress={() => mark('adopted', id)} />
          </Box>
        )
      }
      if (action === 'enter') return <Button key="whole" label="Show the whole prompt" onPress={() => update($, full, () => true)} />
      const find = kind === 'better' ? FIND.exec(text) : null
      if (find) {
        const [, num, name, type, used, why] = find
        return (
          // a web find: its name and kind, then why, the source and the buttons beneath, each item apart from the one before
          <Box key={`l${n}`} marginTop={n % 1000 ? 1 : 0}>
            <Text color={COLOR.better}>{num}</Text>
            <Box flexDirection="column">
              <Box>
                <Text bold color={COLOR.better}>{name}</Text>
                <Text dimColor>{`  ${type}${used ?? ''}`}</Text>
              </Box>
              <Text>{why}</Text>
            </Box>
          </Box>
        )
      }
      if (kind === 'src') {
        return (
          <Box key={`l${n}`} paddingLeft={3}>
            <Text dimColor>{text.trim()}</Text>
          </Box>
        )
      }
      const dot = /^[•-] /.exec(text)?.[0]
      if (dot) {
        return (
          // a bullet's wrapped lines start under its text, as watch.py's bullet() wraps them
          <Box key={`l${n}`}>
            <Text color={COLOR[kind]} dimColor={kind === 'bluedim'}>{dot}</Text>
            <Text color={COLOR[kind]} dimColor={kind === 'bluedim'}>{text.slice(dot.length)}</Text>
          </Box>
        )
      }
      return <Text key={`l${n}`} color={COLOR[kind]} dimColor={kind === 'bluedim' || kind === 'meta' || kind === 'src'} bold={kind === 'prompt'}>{text}</Text>
    }

    // as on watch.py's panel: each section a rounded box in its colour. The title opens it (an element set on the border is not
    // drawn), its label or Copy button right after, never against the pane's right edge, where the pane's own close mark is
    const box = (sec: Section, n: number, body: RenderChildren[]) => {
      const color = SECTION_COLOR[sec.section] ?? 'gray'
      const [, , title, right, action] = sec.head ?? []
      if (!sec.section) return <Box key={`s${n}`} flexDirection="column">{body}</Box>
      return (
        <Box key={`s${n}`} flexDirection="column" borderStyle="round" borderColor={color} paddingX={1}>
          {title && (
            <Box>
              <Text bold color={color}>{title}</Text>
              <Text>{'  '}</Text>
              {action === 'copy' ? <Button key="copy" label="Copy" onPress={copy} /> : right ? <Text dimColor>{right}</Text> : null}
            </Box>
          )}
          {body}
        </Box>
      )
    }

    const card = isFull
      ? [box({ section: 'prompt', head: ['prompt', 'head', 'Your prompt', '', null], rows: [] }, 0, [
          <Text key="fulltext" color="whiteBright">{cur.text}</Text>,
          <Button key="less" label="Show less" onPress={() => update($, full, () => false)} />,
        ])]
      : sections(cur.lines).map((sec, n) => box(sec, n, sec.rows.map((l, k) => line(l, n * 1000 + k))))
    // watch.py's card names keys ("press e"); here one Analyse button stands for them, whatever the prompt's state
    const canAnalyse = !cur.after && cur.state !== 'off'

    return (
      <Box flexDirection="column">
        {header}
        <Box flexDirection="column" marginY={1} gap={1}>{card}</Box>
        {canAnalyse && <Button key="analyse" label={cur.state === 'pending' ? 'Analyse again' : 'Analyse'} onPress={analyse} />}
        {s.research && !!cur.after && cur.state !== 'off' && <Button key="research" label="Look again on the web" onPress={research} />}
        {s.patterns.length > 0 && (
          <Box flexDirection="column">
            <Button key="patterns" label={pats ? 'Hide patterns' : `${s.patterns.length} pattern${s.patterns.length === 1 ? '' : 's'} from your past chats`}
              onPress={() => update($, showPatterns, v => !v)} />
            {pats && s.patterns.map((p, n) => <Text key={`p${n}`} color="blueBright">{p}</Text>)}
            {s.skill && <Button key="skill" label={`Install the drafted skill /${s.skill}`} onPress={install} />}
          </Box>
        )}
        <Text dimColor>Prompts in this thread</Text>
        {s.entries.map((x, n) => (
          <Button key={`e${n}`} label={`${n === i ? '›' : ' '} ${x.glyph} ${x.stamp}  ${x.text.replace(/\s+/g, ' ').slice(0, Math.max(10, width - 16))}`}
            onPress={() => update($, sel, () => n)} />
        ))}
        {footer}
      </Box>
    )
  })
}
