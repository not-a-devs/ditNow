import hashlib
import json
from collections.abc import Callable
from datetime import UTC,datetime
from uuid import UUID,uuid4

from app.core.errors import ApiError
from app.features.online_learning.models import (
    AttemptRecord,AttemptView,ExamSummary,ExamView,LearningActor,ProgressInput,ProgressRecord,
    ProgressView,QuestionView,StartInput,SubmitInput,Workspace,
)
from app.features.online_learning.ports import LearningStore
from app.schemas.common import ApiModel,ErrorCode


def digest(body:ApiModel):
    return hashlib.sha256(json.dumps(body.model_dump(mode="json"),sort_keys=True,
                                    separators=(",",":")).encode()).hexdigest()


class OnlineLearningService:
    def __init__(self,store:LearningStore,clock:Callable[[],datetime]=lambda:datetime.now(UTC)):
        self.store,self.clock=store,clock

    def _now(self):
        now=self.clock()
        if now.tzinfo is None or now.utcoffset() is None:
            raise ApiError(ErrorCode.UNAVAILABLE)
        return now.astimezone(UTC)

    @staticmethod
    def _access(tx,offering_id):
        if (not tx.grant.active or not tx.grant.current_student or tx.offering.id!=offering_id
            or tx.grant.offering_id!=offering_id or tx.grant.term_id!=tx.offering.term_id):
            raise ApiError(ErrorCode.FORBIDDEN)
        if tx.policy is None:
            raise ApiError(ErrorCode.UNAVAILABLE)
        if tx.policy.offering_id!=offering_id or tx.policy.term_id!=tx.offering.term_id:
            raise ApiError(ErrorCode.UNAVAILABLE)

    @staticmethod
    def _attempt(tx,actor,exam_id,id):
        row=tx.attempt(id)
        if (row is None or row.owner_id!=actor.user_id or row.offering_id!=tx.offering.id
            or row.exam_id!=exam_id):
            raise ApiError(ErrorCode.NOT_FOUND)
        return row

    @staticmethod
    def _attempt_view(row):
        return AttemptView(**row.model_dump(exclude={"owner_id","offering_id","policy_revision","answers"}))

    def _exam(self,tx,id,open_required=False):
        exam=tx.exam(id)
        if exam is None or exam.offering_id!=tx.offering.id or exam.status=="draft":
            raise ApiError(ErrorCode.NOT_FOUND)
        if open_required and (exam.status!="published" or not exam.opens_at<=self._now()<exam.closes_at):
            raise ApiError(ErrorCode.CONFLICT)
        return exam

    def _summary(self,exam):
        return ExamSummary(id=exam.id,title=exam.title,revision=exam.revision,opens_at=exam.opens_at,
            closes_at=exam.closes_at,open_for_demo=exam.status=="published" and exam.opens_at<=self._now()<exam.closes_at)

    @staticmethod
    def _progress_view(tx,unit,actor):
        row=tx.progress(unit.id)
        if row is None:
            return ProgressView(unit_id=unit.id,completed_steps=[],revision=0,state="IN_PROGRESS")
        if row.owner_id!=actor.user_id or row.offering_id!=tx.offering.id or row.unit_id!=unit.id:
            raise ApiError(ErrorCode.NOT_FOUND)
        stale=row.unit_revision!=unit.revision or row.policy_revision!=tx.policy.revision
        completed=[] if stale else sorted(row.completed_steps,key=str)
        if not set(completed).issubset({s.id for s in unit.steps}):
            raise ApiError(ErrorCode.UNAVAILABLE)
        state="STALE_DEMO" if stale else "DEMO_COMPLETED" if len(completed)>=tx.policy.completion_steps else "IN_PROGRESS"
        return ProgressView(unit_id=unit.id,completed_steps=completed,revision=row.revision,state=state)

    def offerings(self,actor:LearningActor,limit:int):
        result=[]
        for id in self.store.my_offering_ids(actor.user_id,limit)[:limit]:
            with self.store.transaction(actor.user_id,id) as tx:
                self._access(tx,id)
                result.append(tx.offering)
        return result

    def workspace(self,actor:LearningActor,id:UUID):
        with self.store.transaction(actor.user_id,id) as tx:
            self._access(tx,id)
            now=self._now()
            units=[u for u in tx.units() if u.offering_id==id and u.status=="published"
                   and u.opens_at<=now<u.closes_at]
            exams=[e for e in tx.exams() if e.offering_id==id and e.status!="draft"]
            visible={e.id for e in exams}
            return Workspace(offering=tx.offering,policy=tx.policy,units=units,
                progress=[self._progress_view(tx,u,actor) for u in units],
                exams=[self._summary(e) for e in exams],
                attempts=[self._attempt_view(a) for a in tx.attempts()
                    if a.owner_id==actor.user_id and a.offering_id==id and a.exam_id in visible])

    def mark_step(self,actor,id,unit_id,body:ProgressInput,key):
        with self.store.transaction(actor.user_id,id) as tx:
            self._access(tx,id)
            unit=tx.unit(unit_id)
            if unit is None or unit.offering_id!=id or unit.status=="draft":
                raise ApiError(ErrorCode.NOT_FOUND)
            op,hashed=f"progress:{unit_id}",digest(body)
            old=tx.replay(op,key,hashed)
            if old:
                if old!=unit_id:
                    raise ApiError(ErrorCode.INTERNAL)
                return self._progress_view(tx,unit,actor)
            current=self._progress_view(tx,unit,actor)
            if (unit.status!="published" or not unit.opens_at<=self._now()<unit.closes_at
                or body.expected_unit_revision!=unit.revision
                or body.expected_policy_revision!=tx.policy.revision
                or current.revision!=body.expected_revision or current.state=="STALE_DEMO"):
                raise ApiError(ErrorCode.CONFLICT)
            if tx.policy.completion_steps>len(unit.steps):
                raise ApiError(ErrorCode.UNAVAILABLE)
            if body.step_id not in {s.id for s in unit.steps}:
                raise ApiError(ErrorCode.VALIDATION)
            done=set(current.completed_steps)|{body.step_id}
            record=ProgressRecord(owner_id=actor.user_id,offering_id=id,unit_id=unit_id,
                unit_revision=unit.revision,policy_revision=tx.policy.revision,completed_steps=done,
                revision=current.revision+1,updated_at=self._now())
            tx.save_progress(record,current.revision,op,key,hashed)
            return self._progress_view(tx,unit,actor)

    def exam(self,actor,id,exam_id):
        with self.store.transaction(actor.user_id,id) as tx:
            self._access(tx,id)
            exam=self._exam(tx,exam_id,True)
            return ExamView(**self._summary(exam).model_dump(),questions=[QuestionView(
                id=q.id,prompt=q.prompt,options=q.options) for q in exam.questions])

    def attempt(self,actor,id,exam_id,attempt_id):
        with self.store.transaction(actor.user_id,id) as tx:
            self._access(tx,id)
            self._exam(tx,exam_id)
            return self._attempt_view(self._attempt(tx,actor,exam_id,attempt_id))

    def start(self,actor,id,exam_id,body:StartInput,key):
        with self.store.transaction(actor.user_id,id) as tx:
            self._access(tx,id)
            self._exam(tx,exam_id)
            op,hashed=f"start:{exam_id}",digest(body)
            old=tx.replay(op,key,hashed)
            if old:
                return self._attempt_view(self._attempt(tx,actor,exam_id,old))
            exam=self._exam(tx,exam_id,True)
            if body.expected_exam_revision!=exam.revision or body.expected_policy_revision!=tx.policy.revision:
                raise ApiError(ErrorCode.CONFLICT)
            attempts=[a for a in tx.attempts() if a.owner_id==actor.user_id
                      and a.offering_id==id and a.exam_id==exam_id]
            if len(attempts)>=tx.policy.max_attempts or any(a.state=="in_progress" for a in attempts):
                raise ApiError(ErrorCode.CONFLICT)
            row=AttemptRecord(id=uuid4(),owner_id=actor.user_id,offering_id=id,exam_id=exam_id,
                exam_revision=exam.revision,policy_revision=tx.policy.revision,state="in_progress",
                revision=1,started_at=self._now())
            stored=tx.start(row,op,key,hashed)
            return self._attempt_view(self._attempt(tx,actor,exam_id,stored.id))

    def submit(self,actor,id,exam_id,attempt_id,body:SubmitInput,key):
        with self.store.transaction(actor.user_id,id) as tx:
            self._access(tx,id)
            row=self._attempt(tx,actor,exam_id,attempt_id)
            op,hashed=f"submit:{exam_id}:{attempt_id}",digest(body)
            old=tx.replay(op,key,hashed)
            if old:
                if old!=attempt_id:
                    raise ApiError(ErrorCode.INTERNAL)
                return self._attempt_view(self._attempt(tx,actor,exam_id,old))
            exam=self._exam(tx,exam_id,True)
            if (row.state!="in_progress" or row.revision!=body.expected_revision
                or row.exam_revision!=exam.revision or row.policy_revision!=tx.policy.revision
                or body.expected_exam_revision!=exam.revision or body.expected_policy_revision!=tx.policy.revision):
                raise ApiError(ErrorCode.CONFLICT)
            options={q.id:{o.id for o in q.options} for q in exam.questions}
            if any(a.question_id not in options or a.option_id not in options[a.question_id] for a in body.answers):
                raise ApiError(ErrorCode.VALIDATION)
            if tx.policy.require_all_answers and {a.question_id for a in body.answers}!=set(options):
                raise ApiError(ErrorCode.VALIDATION)
            changed=row.model_copy(update={"answers":body.answers,"state":"submitted",
                "revision":row.revision+1,"submitted_at":self._now()})
            stored=tx.submit(changed,body.expected_revision,op,key,hashed)
            return self._attempt_view(self._attempt(tx,actor,exam_id,stored.id))
