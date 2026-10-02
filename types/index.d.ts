export type PaneLine = [section: string, kind: string, text: string, right: string, action: string | null]

export type PaneEntry = {
  key: string
  stamp: string
  glyph: string
  state: string
  words: string
  text: string
  after: string
  lines: PaneLine[]
}

export type PaneState = {
  ai: boolean
  research: boolean
  auto_open: boolean
  session: string | null
  entries: PaneEntry[]
  patterns: string[]
  skill: string | null
  notice: string | null
}

declare module 'claude-code' {
  interface PluginState {
    coachline: {
      state: PaneState | null
      error: string
      sel: number
      full: boolean
      showPatterns: boolean
      closed: boolean
      msg: string
    }
  }
}
