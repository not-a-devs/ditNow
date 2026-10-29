import { useState, type FormEvent } from 'react';
import { Navigate, useLocation, useNavigate } from 'react-router-dom';
import { homePathFor, useAuth } from '../../app/auth';
import { DemoBanner, Logo } from '../../app/AppLayout';
import { ApiError, DEMO_PASSWORD, listDemoAccounts } from '../../shared/data/api';
import { Button, Field, Input } from '../../shared/ui';

export function LoginPage() {
  const { user, login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const accounts = listDemoAccounts();

  if (user) return <Navigate to={homePathFor(user.role)} replace />;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (pending) return;
    setPending(true);
    setError(null);
    try {
      const u = await login(email, password);
      const from = (location.state as { from?: string } | null)?.from;
      navigate(from && u.role === 'student' && from.startsWith('/app') ? from : homePathFor(u.role), { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : '로그인 중 오류가 발생했습니다.');
    } finally {
      setPending(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#f6f7fa]">
      <DemoBanner />
      <div className="mx-auto grid max-w-5xl gap-8 px-4 py-10 lg:grid-cols-2 lg:items-center lg:py-20">
        <section className="relative overflow-hidden rounded-3xl bg-gradient-to-br from-brand-600 via-brand-700 to-navy-900 p-7 text-white sm:p-10">
          <div className="absolute -right-16 -top-16 h-56 w-56 rounded-full bg-white/10" aria-hidden />
          <div className="absolute -bottom-20 right-10 h-40 w-40 rounded-full bg-sky-500/30" aria-hidden />
          <Logo light />
          <h1 className="relative mt-8 text-2xl font-extrabold leading-snug sm:text-3xl">
            학교의 모든 정보를
            <br />
            내 손안에서, 지금 바로.
          </h1>
          <ul className="relative mt-6 space-y-2 text-sm text-white/85">
            <li>· 조교 공지가 학년 채팅에 자동으로 도착</li>
            <li>· 익명 자유게시판과 실명 팀원 모집</li>
            <li>· 장학금·공모전 준비 체크리스트</li>
          </ul>
        </section>

        <section>
          <form onSubmit={submit} className="rounded-3xl bg-white p-6 shadow-sm ring-1 ring-navy-100 sm:p-8" noValidate>
            <h2 className="text-xl font-bold text-navy-900">로그인</h2>
            <p className="mt-1 text-sm text-navy-500">시연용 계정으로 로그인하세요.</p>
            <div className="mt-6 space-y-4">
              <Field label="이메일" htmlFor="email">
                <Input id="email" type="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="student1@demo.dit" required />
              </Field>
              <Field label="비밀번호" htmlFor="password">
                <Input id="password" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required />
              </Field>
              {error && (
                <p role="alert" className="rounded-xl bg-brand-50 px-3 py-2 text-sm text-brand-700">
                  {error}
                </p>
              )}
              <Button type="submit" className="w-full" loading={pending}>
                로그인
              </Button>
            </div>
          </form>

          <div className="mt-5 rounded-3xl bg-white p-5 ring-1 ring-navy-100">
            <p className="text-sm font-semibold text-navy-800">시연 계정 (비밀번호 {DEMO_PASSWORD})</p>
            <p className="mt-1 text-xs text-navy-500">탭마다 다른 계정으로 로그인해 학생 ↔ 조교 흐름을 함께 확인할 수 있습니다.</p>
            <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2">
              {accounts.map((a) => (
                <button
                  key={a.email}
                  type="button"
                  onClick={() => {
                    setEmail(a.email);
                    setPassword(DEMO_PASSWORD);
                  }}
                  className="min-h-[44px] rounded-xl bg-navy-50 px-3 py-2 text-left hover:bg-navy-100"
                >
                  <span className="block text-sm font-semibold text-navy-900">{a.label}</span>
                  <span className="block text-[11px] text-navy-500">{a.detail} · {a.email}</span>
                </button>
              ))}
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}
