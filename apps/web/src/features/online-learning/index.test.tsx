import { cleanup,fireEvent,render,screen,waitFor } from '@testing-library/react';
import { afterEach,beforeEach,describe,expect,it,vi } from 'vitest';
import { ApiError,resolveApiUrl } from '../../lib/api';
import * as api from './api';
import OnlineLearningPage from './index';

vi.mock('./api',async()=>{const real=await vi.importActual<typeof import('./api')>('./api');return {...real,loadOfferings:vi.fn(),loadWorkspace:vi.fn(),loadExam:vi.fn(),writeProgress:vi.fn(),writeAttempt:vi.fn()};});
const ID='11111111-1111-4111-8111-111111111111',TERM='22222222-2222-4222-8222-222222222222',UNIT='33333333-3333-4333-8333-333333333333',STEP='44444444-4444-4444-8444-444444444444',EXAM='55555555-5555-4555-8555-555555555555',QUESTION='66666666-6666-4666-8666-666666666666',A='77777777-7777-4777-8777-777777777777',B='88888888-8888-4888-8888-888888888888',ATTEMPT='99999999-9999-4999-8999-999999999999';
const offering:api.Offering={id:ID,term_id:TERM,title:'가상 수업',section:'가상 A',source_kind:'DEMO'};
const summary:api.ExamSummary={id:EXAM,title:'가상 시험 A',revision:1,opens_at:'2026-10-30T00:00:00Z',closes_at:'2026-10-31T00:00:00Z',open_for_demo:true,source_kind:'DEMO'};
const exam:api.Exam={...summary,questions:[{id:QUESTION,prompt:'가상 선택 질문',options:[{id:A,text:'선택 A'},{id:B,text:'선택 B'}]}]};
const started:api.Attempt={id:ATTEMPT,exam_id:EXAM,exam_revision:1,state:'in_progress',revision:1,started_at:'2026-10-30T01:00:00Z',submitted_at:null,source_kind:'DEMO',evaluation:'NOT_GRADED',official_grade:'BLOCKED'};
const progress:api.Progress={unit_id:UNIT,completed_steps:[],revision:0,state:'IN_PROGRESS',evidence:'SELF_REPORTED_DEMO',official_attendance:'BLOCKED',source_kind:'DEMO'};
const workspace:api.Workspace={offering,policy:{offering_id:ID,term_id:TERM,revision:1,completion_steps:1,max_attempts:1,require_all_answers:true,source_kind:'DEMO'},units:[{id:UNIT,offering_id:ID,title:'가상 학습 A',steps:[{id:STEP,text:'가상 학습 내용'}],revision:1,status:'published',opens_at:summary.opens_at,closes_at:summary.closes_at,source_kind:'DEMO'}],progress:[progress],exams:[summary],attempts:[],source_kind:'DEMO'};
beforeEach(()=>{vi.clearAllMocks();vi.mocked(api.loadOfferings).mockResolvedValue([offering]);vi.mocked(api.loadWorkspace).mockResolvedValue(structuredClone(workspace));vi.mocked(api.loadExam).mockResolvedValue(structuredClone(exam));vi.mocked(api.writeAttempt).mockResolvedValue(structuredClone(started));});
afterEach(()=>{cleanup();vi.unstubAllGlobals();});
async function loaded(){render(<OnlineLearningPage/>);await screen.findByText('가상 학습 내용');}
async function open(){await loaded();fireEvent.click(screen.getByRole('button',{name:'가상 응시 시작'}));await screen.findByText('가상 선택 질문');}

describe('학생 공개 계약',()=>{
 it('서버와 같은 Unicode 문자 수로 제목·학습 단계·문항·선택지의 경계를 허용한다',()=>{
  expect(api.isOffering({...offering,title:'🙂'.repeat(160),section:'🙂'.repeat(40)})).toBe(true);
  expect(api.isWorkspace({...workspace,units:[{...workspace.units[0],title:'🙂'.repeat(160),steps:[{id:STEP,text:'🙂'.repeat(2000)}]}]})).toBe(true);
  expect(api.isExam({...exam,title:'🙂'.repeat(160),questions:[{...exam.questions[0],prompt:'🙂'.repeat(1000),options:[{id:A,text:'🙂'.repeat(400)},{id:B,text:'선택 B'}]}]})).toBe(true);
 });
 it('Unicode와 ASCII 모두 문자 수 상한을 넘거나 공백뿐인 응답은 거부한다',()=>{
  for(const character of ['🙂','가','a']){
   expect(api.isOffering({...offering,title:character.repeat(161)})).toBe(false);
   expect(api.isOffering({...offering,section:character.repeat(41)})).toBe(false);
   expect(api.isWorkspace({...workspace,units:[{...workspace.units[0],steps:[{id:STEP,text:character.repeat(2001)}]}]})).toBe(false);
   expect(api.isExam({...exam,questions:[{...exam.questions[0],prompt:character.repeat(1001)}]})).toBe(false);
   expect(api.isExam({...exam,questions:[{...exam.questions[0],options:[{id:A,text:character.repeat(401)},{id:B,text:'선택 B'}]}]})).toBe(false);
  }
  expect(api.isOffering({...offering,title:'   '})).toBe(false);
 });
 it('출처·기간·부모·정답·평가 유출 응답을 거부한다',()=>{
  expect(api.isWorkspace(workspace)).toBe(true);expect(api.isExam(exam)).toBe(true);expect(api.isAttempt(started)).toBe(true);
  expect(api.isWorkspace({...workspace,offering:{...offering,source_kind:'OFFICIAL_PUBLIC'}})).toBe(false);
  expect(api.isWorkspace({...workspace,policy:{...workspace.policy,term_id:A}})).toBe(false);
  expect(api.isWorkspace({...workspace,units:[{...workspace.units[0],closes_at:'yesterday'}]})).toBe(false);
  expect(api.isExam({...exam,questions:[{...exam.questions[0],correct_option_id:A}]})).toBe(false);
  expect(api.isAttempt({...started,owner_id:ID})).toBe(false);
  expect(api.isAttempt({...started,score:100})).toBe(false);
  expect(api.isAttempt({...started,answers:[]})).toBe(false);
  expect(api.isProgress({...progress,official_attendance:'present'})).toBe(false);
 });
 it('공통 전송 경로를 한 번만 prefix 한다',async()=>{
  const actual=await vi.importActual<typeof import('./api')>('./api');
  const fetch=vi.fn().mockResolvedValue(new Response(JSON.stringify({data:[offering]}),{status:200,headers:{'Content-Type':'application/json'}}));vi.stubGlobal('fetch',fetch);
  await actual.loadOfferings();expect(fetch.mock.calls[0][0]).toBe(resolveApiUrl('/online-learning?limit=20'));expect(fetch.mock.calls[0][1].cache).toBe('no-store');
 });
 it('런타임 잘못된 상세 응답을 표시 전에 거부한다',async()=>{
  const actual=await vi.importActual<typeof import('./api')>('./api');vi.stubGlobal('fetch',vi.fn().mockResolvedValue(new Response(JSON.stringify({data:{...exam,private_rubric:'private'}}),{status:200})));
  await expect(actual.loadExam(ID,EXAM)).rejects.toMatchObject({code:'INVALID_RESPONSE'});
 });
 it('같은 요청의 미확정 재시도 키를 보존하고 입력 변경은 회전한다',()=>{let n=0;const intent=api.intentTracker(()=>`key-${++n}`);expect(intent.key('submit',{a:1})).toBe(intent.key('submit',{a:1}));expect(intent.key('submit',{a:2})).toBe('key-2');intent.done('submit');expect(intent.key('submit',{a:2})).toBe('key-3');});
});

describe('온라인 학습 화면',()=>{
 it('503 뒤 재확인으로 수강 범위를 불러온다',async()=>{vi.mocked(api.loadOfferings).mockRejectedValueOnce(new ApiError('UNAVAILABLE',503));render(<OnlineLearningPage/>);expect(await screen.findByRole('alert')).toHaveTextContent('연결을 준비');fireEvent.click(screen.getByRole('button',{name:'수강 목록 다시 확인'}));expect(await screen.findByText('가상 학습 내용')).toBeInTheDocument();});
 it('로그인 오류와 빈 강의를 구분한다',async()=>{vi.mocked(api.loadOfferings).mockRejectedValueOnce(new ApiError('UNAUTHORIZED',401));render(<OnlineLearningPage/>);expect(await screen.findByRole('alert')).toHaveTextContent('로그인');vi.mocked(api.loadOfferings).mockResolvedValueOnce([]);fireEvent.click(screen.getByRole('button',{name:'수강 목록 다시 확인'}));expect(await screen.findByText('허용된 온라인 강의가 없습니다.')).toBeInTheDocument();});
 it('본인 확인 진도 실패 후 동일 의도 키로 재시도한다',async()=>{vi.mocked(api.writeProgress).mockRejectedValueOnce(new ApiError('NETWORK',0)).mockResolvedValueOnce({...progress,revision:1,completed_steps:[STEP],state:'DEMO_COMPLETED'});await loaded();fireEvent.click(screen.getByRole('button',{name:'가상 학습 단계 확인'}));await screen.findByRole('alert');fireEvent.click(screen.getByRole('button',{name:'가상 학습 단계 확인'}));expect(await screen.findByText('가상 확인 완료 · 공식 출석 판정 차단')).toBeInTheDocument();const calls=vi.mocked(api.writeProgress).mock.calls;expect(calls[0][3]).toBe(calls[1][3]);expect(calls[1][2]).toEqual(calls[0][2]);});
 it('선택한 가상 답안만 제출하고 채점 없이 제출을 확인한다',async()=>{await open();fireEvent.click(screen.getByLabelText('선택 B'));vi.mocked(api.writeAttempt).mockResolvedValueOnce({...started,state:'submitted',revision:2,submitted_at:'2026-10-30T01:01:00Z'});fireEvent.click(screen.getByRole('button',{name:'가상 답안 제출'}));expect(await screen.findByText('가상 제출을 확인했습니다. 채점·점수·공식 성적은 제공하지 않습니다.')).toBeInTheDocument();expect(vi.mocked(api.writeAttempt).mock.calls[1][2]).toMatchObject({answers:[{question_id:QUESTION,option_id:B}],expected_revision:1});expect(screen.queryByText('가상 선택 질문')).not.toBeInTheDocument();});
 it('제출 실패 시 선택·키를 유지하고 같은 요청으로 다시 확인한다',async()=>{await open();fireEvent.click(screen.getByLabelText('선택 A'));vi.mocked(api.writeAttempt).mockRejectedValueOnce(new ApiError('NETWORK',0)).mockResolvedValueOnce({...started,state:'submitted',revision:2,submitted_at:'2026-10-30T01:01:00Z'});fireEvent.click(screen.getByRole('button',{name:'가상 답안 제출'}));await screen.findByRole('alert');expect(screen.getByLabelText('선택 A')).toBeChecked();fireEvent.click(screen.getByRole('button',{name:'가상 답안 제출'}));await screen.findByText('가상 제출을 확인했습니다. 채점·점수·공식 성적은 제공하지 않습니다.');const calls=vi.mocked(api.writeAttempt).mock.calls;expect(calls[1][3]).toBe(calls[2][3]);expect(calls[1][2]).toEqual(calls[2][2]);});
 it('불확실한 제출 뒤 선택을 변경하면 키가 회전한다',async()=>{await open();vi.mocked(api.writeAttempt).mockRejectedValue(new ApiError('CONFLICT',409));fireEvent.click(screen.getByLabelText('선택 A'));fireEvent.click(screen.getByRole('button',{name:'가상 답안 제출'}));await screen.findByRole('alert');fireEvent.click(screen.getByLabelText('선택 B'));fireEvent.click(screen.getByRole('button',{name:'가상 답안 제출'}));await waitFor(()=>expect(api.writeAttempt).toHaveBeenCalledTimes(3));const calls=vi.mocked(api.writeAttempt).mock.calls;expect(calls[1][3]).not.toBe(calls[2][3]);});
 it('수강 권한이 폐기되면 민감 상태를 화면에서 지운다',async()=>{await open();vi.mocked(api.writeAttempt).mockRejectedValueOnce(new ApiError('FORBIDDEN',403));fireEvent.click(screen.getByLabelText('선택 A'));fireEvent.click(screen.getByRole('button',{name:'가상 답안 제출'}));await screen.findByRole('alert');expect(screen.queryByText('가상 선택 질문')).not.toBeInTheDocument();expect(screen.queryByText('가상 학습 내용')).not.toBeInTheDocument();});
 it('시작 재시도도 같은 의도를 유지한다',async()=>{vi.mocked(api.writeAttempt).mockRejectedValueOnce(new ApiError('NETWORK',0)).mockResolvedValueOnce(started);await loaded();fireEvent.click(screen.getByRole('button',{name:'가상 응시 시작'}));await screen.findByRole('alert');fireEvent.click(screen.getByRole('button',{name:'가상 응시 시작'}));await screen.findByText('가상 선택 질문');const calls=vi.mocked(api.writeAttempt).mock.calls;expect(calls[0][3]).toBe(calls[1][3]);});
});
