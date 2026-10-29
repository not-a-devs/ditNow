import { useEffect, useRef, useState, type FormEvent } from 'react';
import { ApiError, requestData } from '../../lib/api';
import { isOfferings, isQuestion, isSubmission, isWorkspace, type Assignment, type Offering, type Question, type Submission, type Workspace } from './models';
import styles from './styles.module.css';

type Mutation = (path: string, body: object, method?: 'POST' | 'PUT', key?: string) => Promise<unknown>;

function errorMessage(error: unknown): string {
  if (error instanceof ApiError && error.status === 503) return '승인된 공통 인증·수강·저장소 연결이 준비되지 않았습니다. 가상 로그인으로 대체하지 않습니다.';
  return error instanceof ApiError ? error.message : '강의실 응답을 확인하지 못했습니다. 다시 확인해 주세요.';
}
const localDate = (value: string) => new Intl.DateTimeFormat('ko-KR', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value));

function AssignmentCard({ assignment, submission, student, busy, mutate, onSaved }: {
  assignment: Assignment; submission?: Submission; student: boolean; busy: boolean; mutate: Mutation; onSaved: (submission: Submission) => void;
}) {
  const [text, setText] = useState(submission?.text ?? '');
  const [error, setError] = useState('');
  useEffect(() => setText(submission?.text ?? ''), [submission?.revision]);
  async function submit(event: FormEvent) {
    event.preventDefault(); setError('');
    try {
      const data = await mutate(`/assignments/${assignment.id}/submission`, { text, expected_revision: submission?.revision ?? 0 }, 'PUT');
      if (!isSubmission(data)) throw new Error('Invalid response');
      onSaved(data);
    } catch (error) { setError(errorMessage(error)); }
  }
  return <article className={styles.card}>
    <h3>{assignment.title}</h3><p>{assignment.instructions}</p><p>마감: <time dateTime={assignment.deadline_at}>{localDate(assignment.deadline_at)}</time> · {assignment.status === 'published' ? '게시됨' : assignment.status === 'draft' ? '초안' : '종료'}</p>
    {submission && <p role="status">{submission.state === 'resubmitted' ? '다시 제출한' : '제출한'} 시연 기록 · {localDate(submission.submitted_at)}</p>}
    {student && assignment.status === 'published' && <form onSubmit={submit}>
      <label htmlFor={`assignment-${assignment.id}`}>시연 텍스트 과제</label>
      <textarea id={`assignment-${assignment.id}`} maxLength={2000} required value={text} onChange={event => setText(event.target.value)} disabled={busy} />
      <p className={styles.note}>서버 시각으로 마감을 확인합니다. 파일 제출·성적 평가와 연결되지 않는 시연 텍스트입니다.</p>
      <button disabled={busy || !text.trim()}>{busy ? '저장 중…' : submission ? '다시 제출' : '시연 과제 제출'}</button>
    </form>}{error && <p role="alert">{error}</p>}
  </article>;
}

function QuestionCard({ question, teacher, busy, mutate, onSaved }: { question: Question; teacher: boolean; busy: boolean; mutate: Mutation; onSaved: (question: Question) => void }) {
  const [answer, setAnswer] = useState('');
  const [error, setError] = useState('');
  async function change(resolve: boolean, event?: FormEvent) {
    event?.preventDefault(); setError('');
    try {
      const data = await mutate(`/questions/${question.id}/${resolve ? 'resolve' : 'answer'}`, { expected_revision: question.revision, ...(resolve ? {} : { text: answer }) });
      if (!isQuestion(data)) throw new Error('Invalid response');
      onSaved(data);
    } catch (error) { setError(errorMessage(error)); }
  }
  return <article className={styles.card}>
    <span className={styles.badge}>교수에게만 · {question.state === 'open' ? '답변 대기' : question.state === 'answered' ? '답변됨' : '해결됨'}</span>
    <p>{question.text}</p>{question.answer && <div className={styles.answer}><strong>담당 교수 답변</strong><p>{question.answer}</p></div>}
    {teacher && question.state === 'open' && <form onSubmit={event => change(false, event)}><label htmlFor={`answer-${question.id}`}>교수 답변</label><textarea id={`answer-${question.id}`} maxLength={2000} required value={answer} onChange={event => setAnswer(event.target.value)} disabled={busy} /><button disabled={busy || !answer.trim()}>답변 등록</button></form>}
    {teacher && question.state === 'answered' && <button disabled={busy} onClick={() => change(true)}>해결 표시</button>}
    {error && <p role="alert">{error}</p>}
  </article>;
}

export default function ClassroomsPage() {
  const [offerings, setOfferings] = useState<Offering[] | null>(null);
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [pending, setPending] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [question, setQuestion] = useState('');
  const key = useRef({ text: '', value: crypto.randomUUID() });
  const current = useRef<AbortController | null>(null);
  const writes = useRef(new Set<AbortController>());

  async function load(offeringId?: string) {
    current.current?.abort();
    const controller = new AbortController(); current.current = controller;
    setPending(true); setError(''); setWorkspace(null); setQuestion('');
    key.current = { text: '', value: crypto.randomUUID() };
    try {
      const data = await requestData<unknown>(offeringId ? `/classrooms/${offeringId}` : '/classrooms', { signal: controller.signal });
      if (controller.signal.aborted) return;
      if (offeringId) { if (!isWorkspace(data)) throw new Error('Invalid response'); setWorkspace(data); }
      else { if (!isOfferings(data)) throw new Error('Invalid response'); setOfferings(data); }
    } catch (error) { if (!controller.signal.aborted) setError(errorMessage(error)); }
    finally { if (!controller.signal.aborted) setPending(false); }
  }
  useEffect(() => { void load(); return () => { current.current?.abort(); for (const controller of writes.current) controller.abort(); }; }, []);

  const mutate: Mutation = async (path, body, method = 'POST', idempotencyKey) => {
    if (!workspace) throw new ApiError('UNAVAILABLE', 503);
    const controller = new AbortController(); writes.current.add(controller); setBusy(true);
    try {
      return await requestData<unknown>(`/classrooms/${workspace.offering.id}${path}`, {
        method, body: JSON.stringify(body), headers: { 'Content-Type': 'application/json', ...(idempotencyKey ? { 'Idempotency-Key': idempotencyKey } : {}) }, signal: controller.signal,
      });
    } catch (error) {
      if (!controller.signal.aborted && error instanceof ApiError && [401, 403].includes(error.status)) {
        setError(errorMessage(error)); setWorkspace(null);
      }
      throw error;
    } finally { writes.current.delete(controller); if (!controller.signal.aborted) setBusy(false); }
  };

  async function sendQuestion(event: FormEvent) {
    event.preventDefault(); setError('');
    if (key.current.text !== question) key.current = { text: question, value: crypto.randomUUID() };
    try {
      const data = await mutate('/questions', { text: question }, 'POST', key.current.value);
      if (!isQuestion(data)) throw new Error('Invalid response');
      setWorkspace(previous => previous ? { ...previous, questions: [...previous.questions.filter(q => q.id !== data.id), data] } : previous);
      setQuestion(''); key.current = { text: '', value: crypto.randomUUID() };
    } catch (error) { setError(errorMessage(error)); }
  }

  return <section className={styles.page} aria-labelledby="classrooms-title">
    <header><span className={styles.eyebrow}>MY CLASSROOMS</span><h1 id="classrooms-title">내 강의실</h1><p>분반별 수업 자료, 과제와 교수 질문을 한곳에서 확인해요.</p></header>
    <p className={styles.notice}>가상 학기·수강 승인 기반 시연입니다. 실제 학교 학적·성적·온라인 출석·시험·화면 공유는 연결하지 않습니다.</p>
    {pending && <p role="status">강의실을 확인하고 있어요…</p>}
    {error && <div role="alert"><p>{error}</p><button onClick={() => load()}>목록 다시 확인</button></div>}
    {!pending && !workspace && offerings?.length === 0 && <p role="status">현재 승인된 강의실이 없습니다. 등록되지 않은 분반을 임의로 추가하지 않습니다.</p>}
    {!workspace && <div className={styles.grid}>{offerings?.map(offering => <button key={offering.id} className={styles.offering} disabled={pending} onClick={() => load(offering.id)}><span>{offering.term} · {offering.section}</span><strong>{offering.title}</strong><span>{offering.instructor_name} · 시연 분반</span></button>)}</div>}
    {workspace && <>
      <button className={styles.back} disabled={busy} onClick={() => { setWorkspace(null); setError(''); }}>← 내 강의실 목록</button>
      <section className={styles.course}><span>{workspace.offering.term} · {workspace.offering.section} · {workspace.role === 'teacher' ? '담당 교수' : '수강생'} 시연 범위</span><h2>{workspace.offering.title}</h2></section>
      <section><h2>수업 자료</h2>{workspace.materials.length === 0 && <p>게시된 자료가 없습니다.</p>}{workspace.materials.map(material => <article className={styles.card} key={material.id}><h3>{material.title}</h3><p>{material.description}</p>{material.public_reference_url && <a href={material.public_reference_url} target="_blank" rel="noopener noreferrer">공개 참고 원문 열기 ↗</a>}<p className={styles.note}>파일 업로드·보호된 첨부 다운로드는 아직 제공하지 않습니다.</p></article>)}</section>
      <section><h2>과제</h2>{workspace.assignments.length === 0 && <p>게시된 과제가 없습니다.</p>}{workspace.assignments.map(assignment => <AssignmentCard key={assignment.id} assignment={assignment} submission={workspace.submissions.find(s => s.assignment_id === assignment.id)} student={workspace.role === 'student'} busy={busy} mutate={mutate} onSaved={submission => setWorkspace(previous => previous ? { ...previous, submissions: [...previous.submissions.filter(s => s.assignment_id !== submission.assignment_id), submission] } : previous)} />)}</section>
      <section><h2>교수 질문함</h2><p className={styles.note}>이 단계에서는 본인과 담당 교수에게만 보입니다. 공개 질문·수업 실시간 채팅은 별도 단계입니다.</p>
        {workspace.role === 'student' && <form className={styles.card} onSubmit={sendQuestion}><label htmlFor="classroom-question">교수에게 질문</label><textarea id="classroom-question" maxLength={2000} required value={question} disabled={busy} onChange={event => setQuestion(event.target.value)} /><button disabled={busy || !question.trim()}>{busy ? '저장 중…' : '질문 보내기'}</button></form>}
        {workspace.questions.length === 0 && <p>조회할 질문이 없습니다.</p>}
        {workspace.questions.map(q => <QuestionCard key={q.id} question={q} teacher={workspace.role === 'teacher'} busy={busy} mutate={mutate} onSaved={question => setWorkspace(previous => previous ? { ...previous, questions: previous.questions.map(q => q.id === question.id ? question : q) } : previous)} />)}
      </section>
    </>}
  </section>;
}
