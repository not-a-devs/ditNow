import { useEffect, useLayoutEffect, useRef, useState, type MouseEvent } from 'react';
import { Icon } from './components/Icon';
import { StatusPanel } from './components/StatusPanel';
import { ApiError, requestData } from './lib/api';
import { navigation, type SectionId } from './navigation';
import type { components } from './lib/generated/api';
import CampusAssistantPage from './features/ai';
import PublicCampusPage from './features/public-campus';
import PublicDiscoveryPage from './features/discovery';
import PlatformLogin from './features/auth';
import { MemoryAuthProvider, useMemoryAuth } from './features/auth/MemoryAuth';
import { AnonymousBoard } from './features/community/AnonymousBoard';
import { RecruitmentBoard } from './features/community/RecruitmentBoard';
import OpportunitiesPage from './features/opportunities';
import OpportunityAssistant from './features/opportunity-matching/OpportunityAssistant';

type Health = components['schemas']['HealthData'];
type HealthState = { kind: 'loading' | 'idle' } | { kind: 'success'; data: Health } | { kind: 'error'; error: ApiError };

function HealthStatus() {
  const [state, setState] = useState<HealthState>({ kind: 'idle' });
  const active = useRef<AbortController | null>(null);
  useEffect(() => () => active.current?.abort(), []);
  async function check() {
    active.current?.abort();
    const controller = new AbortController();
    active.current = controller;
    setState({ kind: 'loading' });
    try {
      const data = await requestData<Health>('/health', { signal: controller.signal });
      if (!data || data.status !== 'ok' || data.service !== 'ditnow-api') throw new ApiError('INVALID_RESPONSE', 200);
      if (!controller.signal.aborted) setState({ kind: 'success', data });
    } catch (error) {
      if (!controller.signal.aborted) setState({ kind: 'error', error: error instanceof ApiError ? error : new ApiError('NETWORK', 0) });
    }
  }
  return <section className="connection-card" aria-label="공개 서버 연결 확인">
    <div className="eyebrow">SERVICE STATUS</div><h3>서버 연결 확인</h3>
    {state.kind === 'success' ? <p role="status">공개 서버가 응답했습니다. 인증·DB 연결 상태는 확인하지 않습니다.</p>
      : state.kind === 'error' ? <p role="alert">{state.error.message}</p>
      : <p role="status">{state.kind === 'loading' ? '공개 서버 응답을 확인하고 있어요…' : '현재 화면은 공개 탐색입니다. 연결 확인으로 서버 상태를 확인할 수 있어요.'}</p>}
    <button className="outline-button" onClick={check} disabled={state.kind === 'loading'}>{state.kind === 'error' ? '다시 확인' : '연결 확인'} <span aria-hidden="true">↗</span></button>
  </section>;
}

function Home({ navigate }: { navigate: (id: SectionId) => void }) {
  return <>
    <section className="hero">
      <div className="hero-copy"><span className="eyebrow">YOUR CAMPUS, CONNECTED</span><h1>이번 학기도,<br />나답게.</h1><p>배움과 사람, 새로운 기회.<br />당신의 대학 생활을 한곳에서 이어가요.</p><button className="primary-button" onClick={() => navigate('opportunities')}>새로운 기회 살펴보기 <span aria-hidden="true">↗</span></button></div>
      <div className="hero-art" aria-hidden="true"><div className="orb orb-one" /><div className="orb orb-two" /><div className="art-card"><span>DIT</span><b>NOW<span className="art-dot">✳</span></b><small>Make your next move.</small></div><div className="art-caption">배움의 오늘, 가능성의 내일.</div></div>
    </section>
    <section className="section-block" aria-labelledby="quick-title"><div className="section-heading"><div><span className="eyebrow">QUICK ACCESS</span><h2 id="quick-title">나의 캠퍼스로 바로</h2></div><span className="muted">하루를 더 가볍게</span></div>
      <div className="quick-grid">{(['classrooms', 'academic', 'department', 'support'] as const).map(id => { const item = navigation.find(item => item.id === id)!; return <button className="quick-card" key={id} onClick={() => navigate(id)}><span className={`icon-tile tile-${id}`}><Icon name={id} size={26} /></span><strong>{item.label}</strong><span>{item.description}</span><span className="quick-arrow" aria-hidden="true">↗</span></button>; })}</div>
    </section>
    <div className="dashboard-grid"><section className="surface section-block" aria-labelledby="action-title"><div className="section-heading"><div><span className="eyebrow">MY ACTIONS</span><h2 id="action-title">내가 챙길 일</h2></div><span className="badge">개인화 준비 중</span></div><StatusPanel title="나만의 하루를 준비하고 있어요" tone="empty">개인 일정과 알림은 인증·권한 연결 후 제공됩니다. 현재 개인 학적이나 알림을 조회하지 않습니다.</StatusPanel><div className="inline-links"><button onClick={() => navigate('classrooms')}>내 강의실 <span aria-hidden="true">→</span></button><button onClick={() => navigate('opportunities')}>기회 준비 관리 <span aria-hidden="true">→</span></button></div></section>
      <section className="community-card"><span className="eyebrow">BETTER TOGETHER</span><h2>혼자보다<br />함께하는 다음.</h2><p>편하게 나누는 생각부터<br />같이 도전할 팀원까지.</p><div className="community-actions"><button onClick={() => navigate('community')}>익명 커뮤니티 <span aria-hidden="true">↗</span></button><button onClick={() => navigate('recruitments')}>실명 팀원 모집 <span aria-hidden="true">↗</span></button></div></section></div>
    <HealthStatus />
  </>;
}

function PendingSection({ id }: { id: Exclude<SectionId, 'home'> }) {
  const item = navigation.find(item => item.id === id)!;
  return <section className="surface pending-page"><span className="icon-tile"><Icon name={id} size={32} /></span><span className="eyebrow">CONNECTED CAMPUS</span><h1>{item.label}</h1><p className="page-description">{item.description}</p><StatusPanel title="이 기능은 아직 연결되지 않았어요">현재는 통합 탐색 화면입니다. 실제 데이터 조회·작성 기능은 서버와 권한 검증이 연결된 후 제공됩니다.</StatusPanel><p className="pending-note">{id === 'community' ? '익명 글에는 작성자의 실명이나 내부 계정 식별자를 노출하지 않습니다.' : id === 'recruitments' ? '팀원 모집은 익명 게시판과 구분되는 실명 기반 활동입니다.' : id === 'opportunities' ? '외부 기관 제출과 앱의 개인 준비 상태는 구분됩니다.' : '실제 학교의 학적·출결·상담 정보가 연결된 화면이 아닙니다.'}</p></section>;
}

function LoginPanel() {
  const auth = useMemoryAuth();
  if (auth.phase === 'authenticated') return <section className="surface section-block"><h1>현재 가상 계정</h1><p>{auth.user?.display_name} · DEMO</p><p>권한은 서버가 매 요청 다시 확인합니다. 새로고침하면 메모리 로그인이 해제됩니다.</p><button className="outline-button" onClick={auth.signOut}>로그아웃</button></section>;
  if (auth.phase === 'checking') return <StatusPanel title="공통 신원과 현재 권한을 확인 중입니다">로그인 토큰만으로 보호 화면을 열지 않습니다.</StatusPanel>;
  return <>{auth.message && <p role="status">{auth.message}</p>}<PlatformLogin enabled session={{ state: 'signed_out' }} onSignedIn={auth.accept} onSignedOut={() => undefined} /></>;
}

function AssistantPage({ navigate }: { navigate: (id: SectionId) => void }) {
  const auth = useMemoryAuth();
  return <>
    <section className="surface section-block" aria-label="기회·준비 도우미">
      <h1 style={{ wordBreak: 'keep-all', textWrap: 'balance' }}>캠퍼스 <span style={{ whiteSpace: 'nowrap' }}>기회·준비</span> 도우미</h1>
      {auth.phase === 'authenticated'
        ? <OpportunityAssistant key={auth.generation} sessionGeneration={auth.generation} onSaved={() => navigate('opportunities')} />
        : <StatusPanel title="로그인이 필요한 화면입니다"><span>맞춤 기회는 공통 로그인 후 이용할 수 있습니다.</span><button className="outline-button" onClick={() => navigate('login')}>로그인 화면으로</button></StatusPanel>}
    </section>
    <CampusAssistantPage />
  </>;
}

function ProtectedFeature({ id, navigate }: { id: 'community' | 'recruitments' | 'opportunities'; navigate: (id: SectionId) => void }) {
  const auth = useMemoryAuth();
  const title = navigation.find(item => item.id === id)!.label;
  return <section key={auth.generation} className="surface section-block"><h1>{title}</h1>
    {auth.phase !== 'authenticated' ? <StatusPanel title="로그인이 필요한 화면입니다">{auth.message || '가상 계정 로그인 후 서버의 현재 신원·권한을 확인해야 이용할 수 있습니다.'}<button className="outline-button" onClick={() => navigate('login')}>로그인 화면으로</button></StatusPanel>
      : id !== 'opportunities' && !auth.user?.community_access ? <StatusPanel title="현재 커뮤니티 권한이 없습니다">역할이나 소속을 이 화면에서 부여할 수 없습니다. 서버의 승인 상태를 확인해 주세요.</StatusPanel>
      : id === 'community' ? <AnonymousBoard /> : id === 'recruitments' ? <RecruitmentBoard /> : <OpportunitiesPage />}
  </section>;
}

export default function App() { return <MemoryAuthProvider><CampusApp /></MemoryAuthProvider>; }

function CampusApp() {
  const auth = useMemoryAuth();
  const [path, setPath] = useState(window.location.pathname.replace(/\/$/, '') || '/app');
  const [menuOpen, setMenuOpen] = useState(false);
  const main = useRef<HTMLElement>(null);
  const menuNavigation = useRef<HTMLElement>(null);
  const menuTrigger = useRef<HTMLButtonElement | null>(null);
  const current = navigation.find(item => item.path === path);
  function toggleMenu(event: MouseEvent<HTMLButtonElement>) {
    if (!menuOpen) menuTrigger.current = event.currentTarget;
    setMenuOpen(!menuOpen);
  }
  useLayoutEffect(() => {
    if (menuOpen) menuNavigation.current?.querySelector<HTMLAnchorElement>('a[href]')?.focus();
  }, [menuOpen]);
  useEffect(() => {
    if (!menuOpen) return;
    const escape = (event: KeyboardEvent) => {
      if (event.key !== 'Escape' || event.defaultPrevented) return;
      event.preventDefault(); setMenuOpen(false); menuTrigger.current?.focus();
    };
    document.addEventListener('keydown', escape);
    return () => document.removeEventListener('keydown', escape);
  }, [menuOpen]);
  useEffect(() => { const pop = () => { setPath(window.location.pathname.replace(/\/$/, '') || '/app'); setMenuOpen(false); }; window.addEventListener('popstate', pop); return () => window.removeEventListener('popstate', pop); }, []);
  function navigate(id: SectionId) { const item = navigation.find(item => item.id === id)!; window.history.pushState(null, '', item.path); setPath(item.path); setMenuOpen(false); main.current?.focus(); window.scrollTo?.({ top: 0 }); }
  return <div className="app-layout"><a className="skip-link" href="#main-content">본문으로 건너뛰기</a><aside className={`sidebar ${menuOpen ? 'sidebar-open' : ''}`} id="campus-navigation"><a className="brand" href="/app" onClick={event => { event.preventDefault(); navigate('home'); }} aria-label="DIT NOW 홈"><span className="brand-symbol" aria-hidden="true">✳</span><span>DIT <b>NOW</b><small>나의 캠퍼스, 지금</small></span></a><nav ref={menuNavigation} aria-label="캠퍼스 전체 메뉴">{navigation.map((item, index) => <div key={item.id}>{(index === 0 || navigation[index - 1].category !== item.category) && <p className="nav-group">{item.category}</p>}<a href={item.path} className={`nav-link ${current?.id === item.id ? 'active' : ''}`} aria-current={current?.id === item.id ? 'page' : undefined} onClick={event => { if (!event.metaKey && !event.ctrlKey && !event.shiftKey && !event.altKey) { event.preventDefault(); navigate(item.id); } }}><Icon name={item.id} /><span>{item.label}</span>{item.id === 'ai' && <span className="nav-new">AI</span>}</a></div>)}</nav><div className="sidebar-foot"><span className="live-dot" /> 새로운 캠퍼스를 연결하는 중<small>독립 플랫폼 · 공개 탐색</small></div></aside>
    <div className="workspace"><header className="topbar"><button className="menu-button" aria-label={menuOpen ? '전체 메뉴 닫기' : '전체 메뉴 열기'} aria-expanded={menuOpen} aria-controls="campus-navigation" onClick={toggleMenu}>{menuOpen ? '닫기' : '메뉴'}</button><div className="breadcrumb">나의 캠퍼스 <span aria-hidden="true">/</span> <strong>{current?.label ?? '페이지 안내'}</strong></div><div className="visitor"><span className="visitor-avatar" aria-hidden="true">D</span><span>{auth.user?.display_name ?? '공개 탐색'}<small>{auth.phase === 'authenticated' ? '가상 계정(DEMO)' : '로그인되지 않음'}</small></span>{auth.phase === 'authenticated' ? <button className="text-button" onClick={auth.signOut}>로그아웃</button> : <button className="text-button" onClick={() => navigate('login')}>로그인</button>}</div></header><main id="main-content" ref={main} tabIndex={-1}><div className="page-intro"><span>DIT NOW <span className="intro-dot">●</span> CAMPUS PLATFORM</span><span className="preview-badge">개발 중 · 실제 학교 연동 없음</span></div>{current?.id === 'login' ? <LoginPanel /> : current?.id === 'home' ? <Home navigate={navigate} /> : current?.id === 'ai' ? <AssistantPage navigate={navigate} /> : current?.id === 'information' ? <PublicCampusPage /> : current?.id === 'discovery' ? <PublicDiscoveryPage /> : current && ['community', 'recruitments', 'opportunities'].includes(current.id) ? <ProtectedFeature key={`${current.id}:${auth.generation}`} id={current.id as 'community' | 'recruitments' | 'opportunities'} navigate={navigate} /> : current ? <PendingSection key={current.id} id={current.id} /> : <StatusPanel title="페이지를 찾을 수 없어요" tone="error"><button className="text-button" onClick={() => navigate('home')}>캠퍼스 홈으로 이동</button></StatusPanel>}<footer>DIT NOW <span>배움과 사람, 기회를 연결합니다.</span><small>{auth.phase === 'authenticated' ? '가상 계정 · 시연용 데이터' : '공개 탐색 · 로그인 전'}</small></footer></main></div>
    <nav className="mobile-bar" aria-label="빠른 메뉴">{(['home', 'classrooms', 'department', 'community'] as const).map(id => <button key={id} aria-current={current?.id === id ? 'page' : undefined} onClick={() => navigate(id)}><Icon name={id} size={20} /><span>{navigation.find(item => item.id === id)!.label.replace('캠퍼스 ', '')}</span></button>)}<button aria-expanded={menuOpen} aria-controls="campus-navigation" onClick={toggleMenu}><span className="more-icon" aria-hidden="true">•••</span><span>전체 메뉴</span></button></nav>
  </div>;
}
