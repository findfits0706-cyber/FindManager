import { Link } from "react-router-dom";
import { offsetToLabel } from "../../lib/timeOffsets";
import type { MonthlyShiftAssignment, ShiftTimelineResponse, TimelineAssignment, TimelineSegment } from "../../lib/types";

export type TimelineSelection = {
  staffId: string;
  staffName: string;
  date: string;
  assignment: TimelineAssignment | null;
  segments: TimelineSegment[];
};

type Props = {
  plan: ShiftTimelineResponse["plan"];
  selection: TimelineSelection | null;
  assignmentDetail: MonthlyShiftAssignment | null;
  isLoading: boolean;
  isError: boolean;
  canManage: boolean;
  onClose: () => void;
};

function attendanceStatusLabel(status?: string) {
  const labels: Record<string, string> = {
    open: "未打刻",
    clocked_in: "出勤済み",
    on_break: "休憩中",
    clocked_out: "退勤済み",
    pending_correction: "修正申請中",
    confirmed: "確定済み",
    void: "無効",
  };
  return status ? labels[status] ?? status : "なし";
}

export function ShiftDetailPanel({ plan, selection, assignmentDetail, isLoading, isError, canManage, onClose }: Props) {
  if (!selection) return null;
  const detailSegments = (assignmentDetail?.segments ?? []).filter((segment) => segment.is_active);
  const visibleSegments = assignmentDetail
    ? detailSegments.map((segment) => ({
        id: segment.id,
        start_offset_minutes: segment.start_offset_minutes,
        end_offset_minutes: segment.end_offset_minutes,
        duration_minutes: segment.duration_minutes ?? segment.end_offset_minutes - segment.start_offset_minutes,
        work_type_name: segment.work_type_name_snapshot,
        work_type_short_name: segment.work_type_short_name_snapshot,
        work_type_color_key: segment.work_type_color_key_snapshot,
        work_type_is_break: segment.work_type_is_break_snapshot,
        work_area_name: segment.work_area_name_snapshot,
        notes: segment.notes,
      }))
    : selection.segments;
  const workMinutes = assignmentDetail?.work_minutes ?? visibleSegments.filter((segment) => !segment.work_type_is_break).reduce((total, segment) => total + segment.duration_minutes, 0);
  const breakMinutes = assignmentDetail?.break_minutes ?? visibleSegments.filter((segment) => segment.work_type_is_break).reduce((total, segment) => total + segment.duration_minutes, 0);
  const assignment = selection.assignment;
  const patternName = assignmentDetail?.pattern_name_snapshot || assignment?.pattern_name || assignment?.pattern_short_name || "";
  const sourceType = assignmentDetail?.source_type ?? assignment?.source_type;
  const isCustomized = assignmentDetail?.is_customized ?? assignment?.is_customized;
  const notes = assignmentDetail?.notes ?? assignment?.notes;
  const attendance = assignment?.attendance;
  const startOffset = assignmentDetail?.start_offset_minutes ?? Math.min(...visibleSegments.map((segment) => segment.start_offset_minutes));
  const endOffset = assignmentDetail?.end_offset_minutes ?? Math.max(...visibleSegments.map((segment) => segment.end_offset_minutes));
  return (
    <aside className="timeline-detail" aria-label="勤務詳細">
      <div className="section-header">
        <div>
          <h3>{selection.staffName}</h3>
          <p className="subtle-text">{selection.date}</p>
        </div>
        <button type="button" onClick={onClose} aria-label="閉じる">
          x
        </button>
      </div>
      {selection.assignment ? (
        <>
          {isLoading ? <p className="subtle-text">勤務詳細を読み込み中...</p> : null}
          {isError ? <p className="error">Assignment詳細APIの取得に失敗しました。</p> : null}
          <dl className="detail-list">
            <dt>勤務パターン</dt>
            <dd>{patternName}</dd>
            <dt>Assignment</dt>
            <dd>
              {Number.isFinite(startOffset) && Number.isFinite(endOffset) ? `${offsetToLabel(startOffset)}-${offsetToLabel(endOffset)}` : "-"}
            </dd>
            <dt>勤務時間</dt>
            <dd>{workMinutes}分</dd>
            <dt>休憩時間</dt>
            <dd>{breakMinutes}分</dd>
            <dt>source_type</dt>
            <dd>{sourceType}</dd>
            <dt>customized</dt>
            <dd>{isCustomized ? "あり" : "なし"}</dd>
            <dt>warning</dt>
            <dd>{selection.assignment.warning_count ? `${selection.assignment.warning_count}件` : "なし"}</dd>
            <dt>勤怠</dt>
            <dd>{attendanceStatusLabel(attendance?.status)}</dd>
            <dt>実績</dt>
            <dd>{attendance?.actual_start_offset_minutes == null || attendance.actual_end_offset_minutes == null ? "-" : `${offsetToLabel(attendance.actual_start_offset_minutes)}-${offsetToLabel(attendance.actual_end_offset_minutes)}`}</dd>
            <dt>勤怠warning</dt>
            <dd>{attendance?.warning_count ? attendance.warnings.map((item) => item.code).join(" / ") : "なし"}</dd>
            <dt>備考</dt>
            <dd>{notes || "-"}</dd>
          </dl>
          <h4>Segment</h4>
          <div className="detail-segments">
            {visibleSegments.map((segment) => (
              <div key={segment.id} className="detail-segment">
                <strong>
                  {offsetToLabel(segment.start_offset_minutes)}-{offsetToLabel(segment.end_offset_minutes)}
                </strong>
                <span>{segment.work_type_name}</span>
                <span>{segment.work_area_name || "全体"}</span>
                {segment.notes ? <span>{segment.notes}</span> : null}
              </div>
            ))}
          </div>
          {canManage ? (
            <Link
              className="button-link"
              to={`/shifts/monthly?location=${plan.location}&year=${plan.year}&month=${plan.month}&date=${selection.date}&staff=${selection.staffId}`}
            >
              月間シフトで編集
            </Link>
          ) : null}
        </>
      ) : (
        <p className="subtle-text">この日の勤務はありません。</p>
      )}
    </aside>
  );
}
