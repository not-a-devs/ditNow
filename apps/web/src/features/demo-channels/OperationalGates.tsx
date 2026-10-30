/** Read-only explanation (FR-ADM-001~003, FR-NOT-004). No calls, no impersonation, no privileged simulation. */
export default function OperationalGates() {
  return <section className="mx-auto grid max-w-3xl gap-4 p-4" aria-labelledby="ops-gates-title">
    <header><h1 id="ops-gates-title" className="text-2xl font-semibold">운영자·공지 열람 통계 준비 상태</h1>
      <p>이 화면은 안내 전용입니다. 관리자 기능과 공지 열람 통계는 아직 제공하지 않습니다.</p></header>
    <ul className="grid gap-2 rounded border p-3">
      <li>역할 부여·회수(FR-ADM-001): 공통 신원 원장, 승인 절차, 감사 기록이 갖춰지기 전까지 화면과 API를 열지 않습니다.</li>
      <li>콘텐츠 감사(FR-ADM-002): 감사 권한 정책과 열람 범위가 확정되지 않아 미제공입니다.</li>
      <li>신규 업무 역할(FR-ADM-003): 역할 정의는 운영 승인 대상이며 사용자가 스스로 부여할 수 없습니다.</li>
      <li>공지 열람 통계(FR-NOT-004): 개인 열람 기록의 수집·보존 정책이 승인되기 전에는 수집하지 않습니다.</li>
    </ul>
    <p className="rounded bg-amber-50 p-3">다른 사용자로 보기, 관리자 체험, 권한 시뮬레이션 기능은 없습니다. 가상 채널 신청에서도 공식 승인이나 배지는 부여되지 않습니다.</p>
  </section>;
}
