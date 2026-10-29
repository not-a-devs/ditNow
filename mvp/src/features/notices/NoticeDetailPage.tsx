import { useParams } from 'react-router-dom';
import { useAuth } from '../../app/auth';
import { getNotice } from '../../shared/data/api';
import { formatDateTime } from '../../shared/format';
import { useApi } from '../../shared/hooks';
import { Badge, Card, EmptyState, ErrorState, LoadingBlock, PageHeader } from '../../shared/ui';
import { ShieldIcon } from '../../shared/ui/icons';

export function NoticeDetailPage() {
  const { id = '' } = useParams();
  const { user } = useAuth();
  const { data: n, error, loading, reload } = useApi(() => getNotice(id), [id]);
  const back = user?.role === 'student' ? '/app' : '/staff/notices';

  if (loading && !n) return <LoadingBlock rows={3} />;
  if (error) return <ErrorState error={error} onRetry={reload} />;
  if (!n) return null;
  if (n.deletedAt) return <EmptyState title="삭제된 공지입니다" description="작성자가 삭제하여 더 이상 볼 수 없습니다." />;

  return (
    <div className="mx-auto max-w-3xl">
      <PageHeader back={back} title={n.title} />
      <Card>
        <div className="flex flex-wrap items-center gap-1.5">
          <Badge tone="brand"><ShieldIcon className="h-3 w-3" /> 공식</Badge>
          <Badge tone="navy">{n.category}</Badge>
          <Badge tone="gray">{n.audience}</Badge>
          {n.important && <Badge tone="brand">중요</Badge>}
          {n.status === 'archived' && <Badge tone="gray">게시 종료</Badge>}
        </div>
        <dl className="mt-4 grid grid-cols-[auto,1fr] gap-x-4 gap-y-1 text-sm">
          <dt className="text-navy-400">작성</dt>
          <dd className="text-navy-800">{n.authorName} {n.authorRole}</dd>
          <dt className="text-navy-400">게시</dt>
          <dd className="text-navy-800">{formatDateTime(n.createdAt)}</dd>
          {n.revision > 1 && (
            <>
              <dt className="text-navy-400">최종 수정</dt>
              <dd className="text-navy-800">{formatDateTime(n.updatedAt)} (제{n.revision}판)</dd>
            </>
          )}
        </dl>
        <hr className="my-4 border-navy-100" />
        <p className="whitespace-pre-wrap break-words text-[15px] leading-7 text-navy-900">{n.body}</p>
        <hr className="my-4 border-navy-100" />
        <p className="text-xs text-navy-500">
          {n.deliveredChannels.length > 0 ? `자동 전달된 채널: ${n.deliveredChannels.join(', ')}` : '학교 전체 공지는 학과 채팅에 복제하지 않고 홈 공지 목록으로 안내합니다.'}
        </p>
        <p className="mt-1 text-[11px] text-navy-400">※ 시연용 가상 공지입니다. 실제 학교 공지와 무관합니다.</p>
      </Card>
    </div>
  );
}
