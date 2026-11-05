# Trinity Health learning platform: working code

- scoring/   score.py scores a transcript against rubric.json (schema.json validates the output). Sample transcript included.
- persona/   chat.py is a text-only practice chat with Dr. Priya Raman (persona.json, persona_prompt.txt).

Setup:  pip install anthropic jsonschema   then   export ANTHROPIC_API_KEY=...
Try:    cd persona && python chat.py --mock          (no key needed)
        python chat.py --pushback tough              (real model)
        python ../scoring/score.py transcript.txt    (score what you just said)
Spec:   see claude/trinity-learning-platform-spec.md in the General BS project.
The clickable prototype lives in the published design artifact.
