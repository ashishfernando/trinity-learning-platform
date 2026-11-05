#!/usr/bin/env python3
"""Text-only practice conversation with a persona.

Usage: python chat.py [--persona persona.json] [--pushback realistic] [--out transcript.txt] [--mock]
Type your lines as the learner. Type /quit to stop. The transcript is saved in the
format score.py reads:   python ../scoring/score.py transcript.txt
Needs ANTHROPIC_API_KEY unless --mock. Model: env PERSONA_MODEL (default claude-sonnet-5-5).
"""
import argparse, json, os, sys, time
from pathlib import Path

HERE = Path(__file__).parent
END = "<END_SESSION>"

def build_prompt(p, pushback):
    return (HERE / "persona_prompt.txt").read_text().format(pushback=pushback, **p)

def mock_reply(history, p):
    last = history[-1]["content"].lower()
    n = sum(1 for h in history if h["role"] == "user")
    if any(w in last for w in ("friday", "90 days", "by ")) and any(w in last for w in ("navigator", "transport", "review", "plan")):
        return "Okay. Friday works, and I will hold you to the review. " + END
    if any(w in last for w in ("sorry", "should have", "nothing is final", "not final")):
        return "I appreciate that. Patients here already travel an hour for specialty care. Another gap means some will go without."
    if any(w in last for w in ("matters", "hear", "tell me", "what would")):
        return "Guaranteed transport, a nurse navigator, and a clear date you will revisit this."
    if n >= 8:
        return "I do not think we are getting anywhere. Let us talk another time. " + END
    return "That is not really an answer. Was this decided without us?"

def model_reply(system, history):
    import anthropic
    client = anthropic.Anthropic()
    msg = client.messages.create(model=os.environ.get("PERSONA_MODEL", "claude-sonnet-5-5"),
                                 max_tokens=300, system=system, messages=history)
    return "".join(b.text for b in msg.content if b.type == "text").strip()

def stamp(t0):
    s = int(time.time() - t0)
    return f"[{s // 60:02d}:{s % 60:02d}]"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--persona", default=str(HERE / "persona.json"))
    ap.add_argument("--pushback", default="realistic", choices=["supportive", "realistic", "tough"])
    ap.add_argument("--out", default="transcript.txt")
    ap.add_argument("--mock", action="store_true")
    a = ap.parse_args()
    if not a.mock and not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("Set ANTHROPIC_API_KEY, or use --mock.")
    p = json.loads(Path(a.persona).read_text())
    system = build_prompt(p, a.pushback)
    t0 = time.time()
    lines, history = [], []
    opening = p["opening_line"]
    lines.append(f"{stamp(t0)} Character: {opening}")
    history.append({"role": "assistant", "content": opening})
    print(f"\n{p['name']}: {opening}\n")
    while True:
        try:
            you = input("You: ").strip()
        except EOFError:
            break
        if not you:
            continue
        if you == "/quit":
            break
        lines.append(f"{stamp(t0)} Learner: {you}")
        # the API needs the first message to be from the user, so prepend a stage cue
        msgs = [{"role": "user", "content": "(The conversation begins. You speak first.)"}] + history + [{"role": "user", "content": you}]
        history.append({"role": "user", "content": you})
        reply = mock_reply(history, p) if a.mock else model_reply(system, msgs)
        ended = END in reply
        reply = reply.replace(END, "").strip()
        history.append({"role": "assistant", "content": reply})
        lines.append(f"{stamp(t0)} Character: {reply}")
        print(f"\n{p['name']}: {reply}\n")
        if ended:
            print("[Session ended]")
            break
    Path(a.out).write_text("\n".join(lines) + "\n")
    print(f"Transcript saved to {a.out}")

if __name__ == "__main__":
    main()
