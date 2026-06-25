import { Link } from "react-router-dom";
import { offsetToLabel } from "../../lib/timeOffsets";
import type { ShiftTimelineResponse, TimelineAssignment, TimelineSegment } from "../../lib/types";

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
  canManage: boolean;
  onClose: () => void;
};

export function ShiftDetailPanel({ plan, selection, canManage, onClose }: Props) {
  if (!selection) return null;
  const workMinutes = selection.segments
    .filter((segment) => !segment.work_type_is_break)
    .reduce((total, segment) => total + segment.duration_minutes, 0);
  const breakMinutes = selection.segments
    .filter((segment) => segment.work_type_is_break)
    .reduce((total, segment) => total + segment.duration_minutes, 0);
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
          <dl className="detail-list">
            <dt>勤務パターン</dt>
            <dd>{selection.assignment.pattern_name || selection.assignment.pattern_short_name}</dd>
            <dt>勤務時間</dt>
            <dd>{workMinutes}分</dd>
            <dt>休憩時間</dt>
            <dd>{breakMinutes}分</dd>
            <dt>source_type</dt>
            <dd>{selection.assignment.source_type}</dd>
            <dt>customized</dt>
            <dd>{selection.assignment.is_customized ? "あり" : "なし"}</dd>
            <dt>warning</dt>
            <dd>{selection.assignment.warning_count ? `${selection.assignment.warning_count}件` : "なし"}</dd>
            <dt>備考</dt>
            <dd>{selection.assignment.notes || "-"}</dd>
          </dl>
          <h4>Segment</h4>
          <div className="detail-segments">
            {selection.segments.map((segment) => (
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
