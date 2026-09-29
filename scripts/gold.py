"""gold.py make  -> write <config>/coach/gold-labels.md (40 of your prompts, blank labels)
   gold.py eval  -> precision/recall per rule against the labels you filled in.
Label format per item: `yours: ok` or `yours: done-when, no-vague` (rule names from coach.RULES).
Nothing here leaves your machine; the labels file holds redacted prompts, so do not commit it."""
import os, random, re, sys
import coach

OUT = os.path.join(coach.STATE, "gold-labels.md")
NAMES = [n for n, _ in coach.RULES]

def items():
    out, prev = [], None
    for ts, _proj, t in coach.load(coach.HIST):
        gap = None if prev is None else ts - prev; prev = ts
        if coach.scorable(t): out.append((t, gap, [n for n, fn in coach.RULES if not fn(t, gap)]))
    return out

def make():
    its = items(); random.Random(7).shuffle(its)
    flagged = [x for x in its if x[2]][:15]; clean = [x for x in its if not x[2]][:25]
    sample = flagged + clean; random.Random(7).shuffle(sample)
    os.makedirs(coach.STATE, exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("# Gold labels. For each item write `yours: ok` or the rules that SHOULD flag it.\n"
                f"# Rules: {', '.join(NAMES)}\n\n")
        for i, (t, gap, _fails) in enumerate(sample, 1):
            g = "none" if gap is None else int(gap)
            f.write(f"### {i} gap={g}\n{coach.redact(t)[:300]}\nyours: \n\n")
    print(f"wrote {OUT} ({len(sample)} items, {len(flagged)} tool-flagged)")

def parse(text):
    res = []
    for blk in re.split(r"(?m)^### ", text)[1:]:
        head, _, rest = blk.partition("\n")
        m = re.match(r"(\d+) gap=(\S+)", head)
        lab = re.search(r"(?m)^yours:[ \t]*(.*)$", rest)
        if not m or not lab or not lab.group(1).strip(): continue
        gap = None if m.group(2) == "none" else float(m.group(2))
        yours = set() if lab.group(1).strip().lower() == "ok" else {x.strip() for x in lab.group(1).split(",")}
        res.append((rest[:lab.start()].strip(), gap, yours))
    return res

def evaluate():
    try:
        res = parse(open(OUT, encoding="utf-8").read())
    except OSError:
        sys.exit(f"no labels file at {OUT}; run `gold.py make` first")
    print(f"{len(res)} labelled items")
    for name, fn in coach.RULES:
        tp = fp = fn_ = 0
        for prompt, gap, yours in res:
            tool = not fn(prompt, gap); you = name in yours
            tp += tool and you; fp += tool and not you; fn_ += you and not tool
        p = tp / (tp + fp) if tp + fp else float("nan"); r = tp / (tp + fn_) if tp + fn_ else float("nan")
        print(f"  {name:15} precision {p:5.2f}  recall {r:5.2f}   (tp {tp}, fp {fp}, fn {fn_})")

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    {"make": make, "eval": evaluate}[sys.argv[1]]()
