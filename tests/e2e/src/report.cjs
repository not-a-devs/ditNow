'use strict';

const SCHEMA = 'ditnow.p0-browser-e2e.report/v1';
const NOTE =
  'Stage PASS is harness evidence for root review only; it is not VERIFIED status and not real-DB proof.';

/** Collects static stage results; serialisation always passes through the redactor. */
class Report {
  #redactor;
  #stages = [];
  #observations = {};
  #cleanup = null;
  #problems = [];
  #reason = null;
  #mode;
  #startedAt;
  #options = null;

  constructor({ redactor, mode = 'live', now = () => new Date() }) {
    this.#redactor = redactor;
    this.#mode = mode;
    this.now = now;
    this.#startedAt = now().toISOString();
  }

  setOptions(options) {
    this.#options = options;
  }

  setReason(reason, problems = []) {
    this.#reason = reason;
    this.#problems = problems;
  }

  addStage({ id, viewport = null, status, code = null, detail = null, durationMs = 0 }) {
    this.#stages.push({ id, viewport, status, code, detail, duration_ms: durationMs });
  }

  stageStatus(id, viewport = null) {
    const found = this.#stages.find((s) => s.id === id && s.viewport === viewport);
    return found ? found.status : null;
  }

  observe(viewport, key, value) {
    const bucket = (this.#observations[String(viewport)] ??= {});
    bucket[key] = value;
  }

  setCleanup(summary) {
    this.#cleanup = summary;
  }

  get status() {
    if (this.#reason) return this.#stages.some((s) => s.status === 'FAIL') ? 'FAIL' : 'NOT_RUN';
    if (this.#stages.length === 0) return 'NOT_RUN';
    if (this.#stages.some((s) => s.status === 'FAIL' || s.status === 'SKIPPED')) return 'FAIL';
    if (this.#cleanup && this.#cleanup.failed > 0) return 'FAIL';
    return 'PASS';
  }

  toJSON() {
    return this.#redactor.maskDeep({
      schema: SCHEMA,
      status: this.status,
      reason: this.#reason,
      problems: this.#problems,
      mode: this.#mode,
      verified_claim: false,
      note: NOTE,
      started_at: this.#startedAt,
      finished_at: this.now().toISOString(),
      options: this.#options,
      stages: this.#stages,
      observations: this.#observations,
      cleanup: this.#cleanup,
    });
  }
}

module.exports = { Report, SCHEMA };
