CREATE TABLE IF NOT EXISTS role(id INTEGER PRIMARY KEY, title TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS person(id INTEGER PRIMARY KEY, name TEXT NOT NULL, email TEXT, role_id INTEGER REFERENCES role(id), setting TEXT);
CREATE TABLE IF NOT EXISTS persona(id INTEGER PRIMARY KEY, name TEXT, role TEXT, setting TEXT, learner_title TEXT, situation TEXT,
  goal TEXT, worries TEXT, opening_stance TEXT, opening_line TEXT, replica_id TEXT, replica_consent_id TEXT);
CREATE TABLE IF NOT EXISTS scenario(id INTEGER PRIMARY KEY, role_id INTEGER REFERENCES role(id), title TEXT, persona_id INTEGER REFERENCES persona(id), pass_mark INTEGER DEFAULT 70, rubric_json TEXT);
CREATE TABLE IF NOT EXISTS session(id INTEGER PRIMARY KEY, person_id INTEGER REFERENCES person(id), scenario_id INTEGER REFERENCES scenario(id),
  pushback TEXT, started_at REAL, ended_at REAL, avatar_conversation_id TEXT);
CREATE TABLE IF NOT EXISTS transcript_turn(id INTEGER PRIMARY KEY, session_id INTEGER REFERENCES session(id), t_ms INTEGER, speaker TEXT, text TEXT);
CREATE TABLE IF NOT EXISTS score(id INTEGER PRIMARY KEY, session_id INTEGER UNIQUE REFERENCES session(id), overall INTEGER, result_json TEXT,
  model TEXT, prompt_version TEXT, rubric_id TEXT, needs_review INTEGER DEFAULT 0, created_at REAL);
CREATE TABLE IF NOT EXISTS audit_event(id INTEGER PRIMARY KEY, actor TEXT, action TEXT, object TEXT, at REAL);
