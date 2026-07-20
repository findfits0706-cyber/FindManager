from rest_framework import serializers

from apps.accounts.models import User
from apps.operations.models import Location

from .models import (
    AttendanceClosingPeriod,
    AttendanceClosingRecordSnapshot,
    AttendanceClosingStaffSummary,
    AttendanceCorrectionRequest,
    AttendanceEvent,
    AttendanceRecord,
    LaborCostBudgetAllowanceSnapshot,
    LaborCostBudgetDailySummary,
    LaborCostBudgetPeriod,
    LaborCostBudgetPlanRecordSnapshot,
    LaborCostBudgetStaffSummary,
    LaborCostEstimateAllowanceSnapshot,
    LaborCostEstimatePeriod,
    LaborCostEstimateRecordSnapshot,
    LaborCostEstimateStaffSummary,
    MonthlyShiftAssignment,
    MonthlyShiftPlan,
    MonthlyShiftPublication,
    MonthlyShiftPublicationAssignment,
    MonthlyShiftPublicationSegment,
    MonthlyShiftSegment,
    ShiftChangeRequest,
    ShiftPattern,
    ShiftPatternSegment,
    ShiftRequestItem,
    ShiftRequestPeriod,
    ShiftRequestSubmission,
    StaffAllowanceAssignment,
    StaffCompensationProfile,
    WeeklyShiftTemplate,
    WeeklyShiftTemplateEntry,
)
from .services import (
    attendance_record_summary,
    can_cancel_shift_change_request,
    can_edit_shift_change_request,
    can_edit_shift_request_submission,
    can_manage_shifts,
    can_submit_shift_change_request,
    can_submit_shift_request_submission,
    closed_period_from_lookup,
    count_shift_request_target_staff,
    is_attendance_period_closed,
    save_monthly_assignment,
    save_monthly_plan,
    save_shift_pattern,
    save_weekly_template,
    shift_change_requests_for_display,
)

FORBIDDEN_CHILD_FIELDS = {"is_active", "created_at", "updated_at"}
IMMUTABLE_LOCATION_MESSAGE = "拠点は作成後変更できません。別拠点用に複製してください。"
IMMUTABLE_PLAN_MESSAGE = "拠点・年月は作成後変更できません。新しい月間表を作成してください。"


class ShiftPatternSegmentSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(required=False)
    work_type_name = serializers.CharField(source="work_type.name", read_only=True)
    work_type_color_key = serializers.CharField(source="work_type.color_key", read_only=True)
    work_area_name = serializers.CharField(source="work_area.name", read_only=True)
    duration_minutes = serializers.IntegerField(read_only=True)

    class Meta:
        model = ShiftPatternSegment
        fields = [
            "id",
            "work_type",
            "work_type_name",
            "work_type_color_key",
            "work_area",
            "work_area_name",
            "start_offset_minutes",
            "end_offset_minutes",
            "duration_minutes",
            "display_order",
            "notes",
            "is_active",
        ]
        read_only_fields = ["is_active"]

    def validate(self, attrs):
        forbidden = FORBIDDEN_CHILD_FIELDS.intersection(getattr(self, "initial_data", {}))
        if forbidden:
            raise serializers.ValidationError({field: "This field is read-only." for field in forbidden})
        return attrs


class ShiftPatternSerializer(serializers.ModelSerializer):
    location_name = serializers.CharField(source="location.name", read_only=True)
    segments = ShiftPatternSegmentSerializer(many=True, required=False)
    start_offset_minutes = serializers.SerializerMethodField()
    end_offset_minutes = serializers.SerializerMethodField()
    total_minutes = serializers.SerializerMethodField()
    work_minutes = serializers.SerializerMethodField()
    break_minutes = serializers.SerializerMethodField()
    segment_count = serializers.SerializerMethodField()

    class Meta:
        model = ShiftPattern
        fields = [
            "id",
            "location",
            "location_name",
            "code",
            "name",
            "short_name",
            "description",
            "display_order",
            "is_active",
            "start_offset_minutes",
            "end_offset_minutes",
            "total_minutes",
            "work_minutes",
            "break_minutes",
            "segment_count",
            "segments",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "is_active",
            "created_at",
            "updated_at",
            "start_offset_minutes",
            "end_offset_minutes",
            "total_minutes",
            "work_minutes",
            "break_minutes",
            "segment_count",
        ]

    def _active_segments(self, obj):
        return [segment for segment in obj.segments.all() if segment.is_active]

    def get_start_offset_minutes(self, obj):
        segments = self._active_segments(obj)
        return min((segment.start_offset_minutes for segment in segments), default=None)

    def get_end_offset_minutes(self, obj):
        segments = self._active_segments(obj)
        return max((segment.end_offset_minutes for segment in segments), default=None)

    def get_total_minutes(self, obj):
        start = self.get_start_offset_minutes(obj)
        end = self.get_end_offset_minutes(obj)
        return None if start is None or end is None else end - start

    def get_work_minutes(self, obj):
        return sum(segment.duration_minutes for segment in self._active_segments(obj) if not segment.work_type.is_break)

    def get_break_minutes(self, obj):
        return sum(segment.duration_minutes for segment in self._active_segments(obj) if segment.work_type.is_break)

    def get_segment_count(self, obj):
        return len(self._active_segments(obj))

    def validate(self, attrs):
        forbidden = {"is_active", "created_at", "updated_at"}.intersection(self.initial_data)
        if forbidden:
            raise serializers.ValidationError({field: "This field is read-only." for field in forbidden})
        if self.instance is not None and "location" in attrs and attrs["location"].id != self.instance.location_id:
            raise serializers.ValidationError({"location": IMMUTABLE_LOCATION_MESSAGE})
        return attrs

    def create(self, validated_data):
        segments_data = validated_data.pop("segments", None)
        return save_shift_pattern(instance=None, validated_data=validated_data, segments_data=segments_data)

    def update(self, instance, validated_data):
        segments_data = validated_data.pop("segments", None)
        return save_shift_pattern(instance=instance, validated_data=validated_data, segments_data=segments_data)


class ShiftPatternDuplicateSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=50)
    name = serializers.CharField(max_length=150)
    short_name = serializers.CharField(max_length=100)


class ShiftPatternListSerializer(ShiftPatternSerializer):
    class Meta(ShiftPatternSerializer.Meta):
        fields = [field for field in ShiftPatternSerializer.Meta.fields if field != "segments"]


class WeeklyShiftTemplateEntrySerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(required=False)
    weekday_label = serializers.CharField(source="get_weekday_display", read_only=True)
    staff_display_name = serializers.CharField(source="staff.display_name", read_only=True)
    shift_pattern_name = serializers.CharField(source="shift_pattern.name", read_only=True)
    shift_pattern_short_name = serializers.CharField(source="shift_pattern.short_name", read_only=True)

    class Meta:
        model = WeeklyShiftTemplateEntry
        fields = [
            "id",
            "weekday",
            "weekday_label",
            "staff",
            "staff_display_name",
            "shift_pattern",
            "shift_pattern_name",
            "shift_pattern_short_name",
            "notes",
            "display_order",
            "is_active",
        ]
        read_only_fields = ["is_active"]

    def validate(self, attrs):
        forbidden = FORBIDDEN_CHILD_FIELDS.intersection(getattr(self, "initial_data", {}))
        if forbidden:
            raise serializers.ValidationError({field: "This field is read-only." for field in forbidden})
        return attrs


class WeeklyShiftTemplateSerializer(serializers.ModelSerializer):
    location_name = serializers.CharField(source="location.name", read_only=True)
    entries = WeeklyShiftTemplateEntrySerializer(many=True, required=False)
    staff_count = serializers.SerializerMethodField()
    entry_count = serializers.SerializerMethodField()

    class Meta:
        model = WeeklyShiftTemplate
        fields = [
            "id",
            "location",
            "location_name",
            "code",
            "name",
            "description",
            "display_order",
            "is_active",
            "staff_count",
            "entry_count",
            "entries",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["is_active", "created_at", "updated_at", "staff_count", "entry_count"]

    def _active_entries(self, obj):
        return [entry for entry in obj.entries.all() if entry.is_active]

    def get_staff_count(self, obj):
        return len({entry.staff_id for entry in self._active_entries(obj)})

    def get_entry_count(self, obj):
        return len(self._active_entries(obj))

    def validate(self, attrs):
        forbidden = {"is_active", "created_at", "updated_at"}.intersection(self.initial_data)
        if forbidden:
            raise serializers.ValidationError({field: "This field is read-only." for field in forbidden})
        if self.instance is not None and "location" in attrs and attrs["location"].id != self.instance.location_id:
            raise serializers.ValidationError({"location": IMMUTABLE_LOCATION_MESSAGE})
        return attrs

    def create(self, validated_data):
        entries_data = validated_data.pop("entries", None)
        return save_weekly_template(instance=None, validated_data=validated_data, entries_data=entries_data)

    def update(self, instance, validated_data):
        entries_data = validated_data.pop("entries", None)
        return save_weekly_template(instance=instance, validated_data=validated_data, entries_data=entries_data)


class WeeklyShiftTemplateDuplicateSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=50)
    name = serializers.CharField(max_length=150)


class WeeklyShiftTemplateListSerializer(WeeklyShiftTemplateSerializer):
    class Meta(WeeklyShiftTemplateSerializer.Meta):
        fields = [field for field in WeeklyShiftTemplateSerializer.Meta.fields if field != "entries"]


class MonthlyShiftSegmentSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(required=False)
    duration_minutes = serializers.IntegerField(read_only=True)

    class Meta:
        model = MonthlyShiftSegment
        fields = [
            "id",
            "source_pattern_segment",
            "work_type",
            "work_area",
            "work_type_name_snapshot",
            "work_type_short_name_snapshot",
            "work_type_color_key_snapshot",
            "work_type_is_break_snapshot",
            "work_area_name_snapshot",
            "start_offset_minutes",
            "end_offset_minutes",
            "duration_minutes",
            "display_order",
            "notes",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "source_pattern_segment",
            "work_type_name_snapshot",
            "work_type_short_name_snapshot",
            "work_type_color_key_snapshot",
            "work_type_is_break_snapshot",
            "work_area_name_snapshot",
            "duration_minutes",
            "is_active",
            "created_at",
            "updated_at",
        ]

    def validate(self, attrs):
        forbidden = FORBIDDEN_CHILD_FIELDS.intersection(getattr(self, "initial_data", {}))
        if forbidden:
            raise serializers.ValidationError({field: "This field is read-only." for field in forbidden})
        return attrs


class MonthlyShiftPlanSerializer(serializers.ModelSerializer):
    location_name = serializers.CharField(source="location.name", read_only=True)
    source_weekly_template_name = serializers.CharField(source="source_weekly_template.name", read_only=True)
    confirmed_by_display_name = serializers.CharField(source="confirmed_by.display_name", read_only=True)
    assignment_count = serializers.SerializerMethodField()
    staff_count = serializers.SerializerMethodField()
    is_editable = serializers.SerializerMethodField()
    current_publication = serializers.SerializerMethodField()
    publication_count = serializers.SerializerMethodField()

    class Meta:
        model = MonthlyShiftPlan
        fields = [
            "id",
            "location",
            "location_name",
            "year",
            "month",
            "name",
            "notes",
            "assignment_count",
            "staff_count",
            "source_weekly_template",
            "source_weekly_template_name",
            "last_generated_at",
            "last_generated_by",
            "workflow_status",
            "confirmed_at",
            "confirmed_by",
            "confirmed_by_display_name",
            "confirmed_content_hash",
            "is_editable",
            "current_publication",
            "publication_count",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "assignment_count",
            "staff_count",
            "source_weekly_template",
            "source_weekly_template_name",
            "last_generated_at",
            "last_generated_by",
            "workflow_status",
            "confirmed_at",
            "confirmed_by",
            "confirmed_by_display_name",
            "confirmed_content_hash",
            "is_editable",
            "current_publication",
            "publication_count",
            "is_active",
            "created_at",
            "updated_at",
        ]
        validators = []

    def get_assignment_count(self, obj):
        if hasattr(obj, "active_assignment_count"):
            return obj.active_assignment_count
        return obj.assignments.filter(is_active=True).count()

    def get_staff_count(self, obj):
        if hasattr(obj, "active_staff_count"):
            return obj.active_staff_count
        return obj.assignments.filter(is_active=True).values("staff_id").distinct().count()

    def get_is_editable(self, obj):
        return obj.is_active and obj.workflow_status == MonthlyShiftPlan.WorkflowStatus.DRAFT

    def get_current_publication(self, obj):
        if hasattr(obj, "active_publications"):
            publication = obj.active_publications[0] if obj.active_publications else None
        else:
            publication = obj.publications.filter(is_active=True).order_by("-version").first()
        if publication is None:
            return None
        return {
            "id": str(publication.id),
            "version": publication.version,
            "published_at": publication.published_at,
            "published_by": str(publication.published_by_id),
            "published_by_display_name": publication.published_by.display_name,
        }

    def get_publication_count(self, obj):
        if hasattr(obj, "publication_total"):
            return obj.publication_total
        return obj.publications.count()

    def validate(self, attrs):
        forbidden = {
            "is_active",
            "created_at",
            "updated_at",
            "last_generated_at",
            "last_generated_by",
            "workflow_status",
            "confirmed_at",
            "confirmed_by",
            "confirmed_content_hash",
        }.intersection(self.initial_data)
        if forbidden:
            raise serializers.ValidationError({field: "This field is read-only." for field in forbidden})
        if self.instance is not None:
            errors = {}
            if "location" in attrs and attrs["location"].id != self.instance.location_id:
                errors["location"] = IMMUTABLE_PLAN_MESSAGE
            if "year" in attrs and attrs["year"] != self.instance.year:
                errors["year"] = IMMUTABLE_PLAN_MESSAGE
            if "month" in attrs and attrs["month"] != self.instance.month:
                errors["month"] = IMMUTABLE_PLAN_MESSAGE
            if errors:
                raise serializers.ValidationError(errors)
        return attrs

    def create(self, validated_data):
        return save_monthly_plan(instance=None, validated_data=validated_data, actor=self.context["request"].user)

    def update(self, instance, validated_data):
        return save_monthly_plan(instance=instance, validated_data=validated_data, actor=self.context["request"].user)


class MonthlyShiftPlanListSerializer(MonthlyShiftPlanSerializer):
    class Meta(MonthlyShiftPlanSerializer.Meta):
        fields = [
            "id",
            "location",
            "location_name",
            "year",
            "month",
            "name",
            "assignment_count",
            "staff_count",
            "last_generated_at",
            "source_weekly_template",
            "source_weekly_template_name",
            "workflow_status",
            "is_editable",
            "current_publication",
            "publication_count",
            "is_active",
            "created_at",
            "updated_at",
        ]


class MonthlyShiftAssignmentSerializer(serializers.ModelSerializer):
    staff_display_name = serializers.CharField(source="staff.display_name", read_only=True)
    segments = MonthlyShiftSegmentSerializer(many=True, required=False)
    shift_pattern = serializers.PrimaryKeyRelatedField(
        queryset=ShiftPattern.objects.filter(is_active=True),
        write_only=True,
        required=False,
    )
    warnings = serializers.SerializerMethodField()
    start_offset_minutes = serializers.SerializerMethodField()
    end_offset_minutes = serializers.SerializerMethodField()
    work_minutes = serializers.SerializerMethodField()
    break_minutes = serializers.SerializerMethodField()
    segment_count = serializers.SerializerMethodField()

    class Meta:
        model = MonthlyShiftAssignment
        fields = [
            "id",
            "monthly_shift_plan",
            "work_date",
            "staff",
            "staff_display_name",
            "source_type",
            "source_weekly_template_entry",
            "source_shift_pattern",
            "shift_pattern",
            "pattern_code_snapshot",
            "pattern_name_snapshot",
            "pattern_short_name_snapshot",
            "notes",
            "is_customized",
            "display_order",
            "is_active",
            "start_offset_minutes",
            "end_offset_minutes",
            "work_minutes",
            "break_minutes",
            "segment_count",
            "warnings",
            "segments",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "source_type",
            "source_weekly_template_entry",
            "source_shift_pattern",
            "pattern_code_snapshot",
            "pattern_name_snapshot",
            "pattern_short_name_snapshot",
            "is_customized",
            "is_active",
            "start_offset_minutes",
            "end_offset_minutes",
            "work_minutes",
            "break_minutes",
            "segment_count",
            "warnings",
            "created_at",
            "updated_at",
        ]
        validators = []

    def _active_segments(self, obj):
        return [segment for segment in obj.segments.all() if segment.is_active]

    def get_warnings(self, obj):
        return getattr(obj, "validation_warnings", [])

    def get_start_offset_minutes(self, obj):
        return min((segment.start_offset_minutes for segment in self._active_segments(obj)), default=None)

    def get_end_offset_minutes(self, obj):
        return max((segment.end_offset_minutes for segment in self._active_segments(obj)), default=None)

    def get_work_minutes(self, obj):
        return sum(
            segment.duration_minutes
            for segment in self._active_segments(obj)
            if not segment.work_type_is_break_snapshot
        )

    def get_break_minutes(self, obj):
        return sum(
            segment.duration_minutes for segment in self._active_segments(obj) if segment.work_type_is_break_snapshot
        )

    def get_segment_count(self, obj):
        return len(self._active_segments(obj))

    def validate(self, attrs):
        forbidden = {"is_active", "created_at", "updated_at"}.intersection(self.initial_data)
        if forbidden:
            raise serializers.ValidationError({field: "This field is read-only." for field in forbidden})
        if self.instance is not None:
            errors = {}
            message = "月間表・日付・スタッフは作成後変更できません。勤務を解除して新しく作成してください。"
            if "monthly_shift_plan" in attrs and attrs["monthly_shift_plan"].id != self.instance.monthly_shift_plan_id:
                errors["monthly_shift_plan"] = message
            if "work_date" in attrs and attrs["work_date"] != self.instance.work_date:
                errors["work_date"] = message
            if "staff" in attrs and attrs["staff"].id != self.instance.staff_id:
                errors["staff"] = message
            if errors:
                raise serializers.ValidationError(errors)
        return attrs

    def create(self, validated_data):
        segments_data = validated_data.pop("segments", None)
        shift_pattern = validated_data.pop("shift_pattern", None)
        return save_monthly_assignment(
            instance=None,
            validated_data=validated_data,
            segments_data=segments_data,
            shift_pattern=shift_pattern,
            actor=self.context["request"].user,
        )

    def update(self, instance, validated_data):
        segments_data = validated_data.pop("segments", None)
        shift_pattern = validated_data.pop("shift_pattern", None)
        return save_monthly_assignment(
            instance=instance,
            validated_data=validated_data,
            segments_data=segments_data,
            shift_pattern=shift_pattern,
            actor=self.context["request"].user,
        )


class MonthlyShiftAssignmentListSerializer(MonthlyShiftAssignmentSerializer):
    class Meta(MonthlyShiftAssignmentSerializer.Meta):
        fields = [field for field in MonthlyShiftAssignmentSerializer.Meta.fields if field != "segments"]


class TemplateGenerationSerializer(serializers.Serializer):
    weekly_shift_template = serializers.PrimaryKeyRelatedField(queryset=WeeklyShiftTemplate.objects.all())
    existing_mode = serializers.ChoiceField(
        choices=["skip_existing", "replace_template_generated"], default="skip_existing"
    )
    invalid_mode = serializers.ChoiceField(choices=["strict", "skip_invalid"], default="strict")


class PublicationAcknowledgeSerializer(serializers.Serializer):
    acknowledge_warnings = serializers.BooleanField(default=False)


class PublicationReopenSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=1000, required=False, allow_blank=True, trim_whitespace=True)


class PublicationWithdrawSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=1000, trim_whitespace=True)


class MonthlyShiftPublicationSegmentSerializer(serializers.ModelSerializer):
    duration_minutes = serializers.SerializerMethodField()

    class Meta:
        model = MonthlyShiftPublicationSegment
        fields = [
            "id",
            "source_segment",
            "work_type",
            "work_area",
            "work_type_name_snapshot",
            "work_type_short_name_snapshot",
            "work_type_color_key_snapshot",
            "work_type_is_break_snapshot",
            "work_area_name_snapshot",
            "start_offset_minutes",
            "end_offset_minutes",
            "duration_minutes",
            "display_order",
            "notes",
            "created_at",
        ]

    def get_duration_minutes(self, obj):
        return obj.end_offset_minutes - obj.start_offset_minutes


class MonthlyShiftPublicationAssignmentSerializer(serializers.ModelSerializer):
    segments = serializers.SerializerMethodField()
    start_offset_minutes = serializers.SerializerMethodField()
    end_offset_minutes = serializers.SerializerMethodField()
    work_minutes = serializers.SerializerMethodField()
    break_minutes = serializers.SerializerMethodField()

    class Meta:
        model = MonthlyShiftPublicationAssignment
        fields = [
            "id",
            "source_assignment",
            "work_date",
            "staff",
            "staff_display_name_snapshot",
            "employee_code_snapshot",
            "source_type",
            "is_customized",
            "pattern_code_snapshot",
            "pattern_name_snapshot",
            "pattern_short_name_snapshot",
            "notes",
            "display_order",
            "warning_count_snapshot",
            "start_offset_minutes",
            "end_offset_minutes",
            "work_minutes",
            "break_minutes",
            "segments",
            "created_at",
        ]

    def _segments(self, obj):
        cached = getattr(obj, "_publication_segments_cache", None)
        if cached is not None:
            return cached
        if hasattr(obj, "prefetched_segments"):
            cached = list(obj.prefetched_segments)
        else:
            cached = list(obj.segments.all())
        obj._publication_segments_cache = cached
        return cached

    def get_segments(self, obj):
        return MonthlyShiftPublicationSegmentSerializer(self._segments(obj), many=True).data

    def get_start_offset_minutes(self, obj):
        return min((segment.start_offset_minutes for segment in self._segments(obj)), default=None)

    def get_end_offset_minutes(self, obj):
        return max((segment.end_offset_minutes for segment in self._segments(obj)), default=None)

    def get_work_minutes(self, obj):
        return sum(
            segment.end_offset_minutes - segment.start_offset_minutes
            for segment in self._segments(obj)
            if not segment.work_type_is_break_snapshot
        )

    def get_break_minutes(self, obj):
        return sum(
            segment.end_offset_minutes - segment.start_offset_minutes
            for segment in self._segments(obj)
            if segment.work_type_is_break_snapshot
        )


class MonthlyShiftPublicationSerializer(serializers.ModelSerializer):
    published_by_display_name = serializers.CharField(source="published_by.display_name", read_only=True)
    withdrawn_by_display_name = serializers.CharField(source="withdrawn_by.display_name", read_only=True)
    assignment_count = serializers.SerializerMethodField()
    staff_count = serializers.SerializerMethodField()
    segment_count = serializers.SerializerMethodField()
    assignments = MonthlyShiftPublicationAssignmentSerializer(many=True, read_only=True)

    class Meta:
        model = MonthlyShiftPublication
        fields = [
            "id",
            "monthly_shift_plan",
            "version",
            "content_hash",
            "location",
            "location_name_snapshot",
            "location_short_name_snapshot",
            "year",
            "month",
            "plan_name_snapshot",
            "plan_notes_snapshot",
            "published_by",
            "published_by_display_name",
            "published_at",
            "withdrawn_by",
            "withdrawn_by_display_name",
            "withdrawn_at",
            "withdrawal_reason",
            "is_active",
            "assignment_count",
            "staff_count",
            "segment_count",
            "assignments",
            "created_at",
        ]

    def get_assignment_count(self, obj):
        if hasattr(obj, "assignment_total"):
            return obj.assignment_total
        return obj.assignments.count()

    def get_staff_count(self, obj):
        if hasattr(obj, "staff_total"):
            return obj.staff_total
        return obj.assignments.values("staff_id").distinct().count()

    def get_segment_count(self, obj):
        if hasattr(obj, "segment_total"):
            return obj.segment_total
        return MonthlyShiftPublicationSegment.objects.filter(publication_assignment__publication=obj).count()


class MonthlyShiftPublicationListSerializer(MonthlyShiftPublicationSerializer):
    class Meta(MonthlyShiftPublicationSerializer.Meta):
        fields = [field for field in MonthlyShiftPublicationSerializer.Meta.fields if field != "assignments"]


class MyPublishedShiftSerializer(MonthlyShiftPublicationAssignmentSerializer):
    publication = serializers.SerializerMethodField()
    shift_change_requests = serializers.SerializerMethodField()
    attendance = serializers.SerializerMethodField()
    is_month_closed = serializers.SerializerMethodField()
    closing_period = serializers.SerializerMethodField()

    class Meta(MonthlyShiftPublicationAssignmentSerializer.Meta):
        fields = MonthlyShiftPublicationAssignmentSerializer.Meta.fields + [
            "publication",
            "shift_change_requests",
            "attendance",
            "is_month_closed",
            "closing_period",
        ]

    def get_publication(self, obj):
        publication = obj.publication
        return {
            "id": str(publication.id),
            "version": publication.version,
            "monthly_shift_plan": str(publication.monthly_shift_plan_id),
            "location": str(publication.location_id),
            "location_name": publication.location_name_snapshot,
            "year": publication.year,
            "month": publication.month,
            "published_at": publication.published_at,
        }

    def get_shift_change_requests(self, obj):
        lookup = self.context.get("shift_change_request_lookup", {})
        return shift_change_requests_for_display(lookup.get(str(obj.id), []))

    def get_attendance(self, obj):
        lookup = self.context.get("attendance_lookup", {})
        return attendance_record_summary(
            lookup.get(str(obj.id)),
            closed_period_lookup=self.context.get("closed_period_lookup"),
        )

    def _closed_period(self, obj):
        return closed_period_from_lookup(
            self.context.get("closed_period_lookup"),
            location_id=obj.publication.location_id,
            work_date=obj.work_date,
        )

    def get_is_month_closed(self, obj):
        return self._closed_period(obj) is not None

    def get_closing_period(self, obj):
        period = self._closed_period(obj)
        if period is None:
            return None
        return {"id": str(period.id), "name": period.name, "status": period.status}


class ShiftChangeRequestSerializer(serializers.ModelSerializer):
    location_name = serializers.CharField(source="location.name", read_only=True)
    publication_version = serializers.IntegerField(source="publication.version", read_only=True)
    requester_display_name = serializers.CharField(source="requester.display_name", read_only=True)
    target_staff_display_name = serializers.CharField(source="target_staff.display_name", read_only=True)
    requested_staff_display_name = serializers.CharField(source="requested_staff.display_name", read_only=True)
    requested_shift_pattern_name = serializers.CharField(source="requested_shift_pattern.name", read_only=True)
    can_edit = serializers.SerializerMethodField()
    can_submit = serializers.SerializerMethodField()
    can_cancel = serializers.SerializerMethodField()
    can_approve = serializers.SerializerMethodField()
    can_apply = serializers.SerializerMethodField()

    class Meta:
        model = ShiftChangeRequest
        fields = [
            "id",
            "location",
            "location_name",
            "monthly_shift_plan",
            "publication",
            "publication_version",
            "publication_assignment",
            "requester",
            "requester_display_name",
            "target_staff",
            "target_staff_display_name",
            "requested_staff",
            "requested_staff_display_name",
            "request_type",
            "status",
            "priority",
            "work_date",
            "original_start_offset_minutes",
            "original_end_offset_minutes",
            "original_pattern_name_snapshot",
            "original_pattern_short_name_snapshot",
            "requested_work_date",
            "requested_shift_pattern",
            "requested_shift_pattern_name",
            "requested_start_offset_minutes",
            "requested_end_offset_minutes",
            "requested_notes",
            "reason",
            "manager_note",
            "submitted_at",
            "submitted_by",
            "approved_at",
            "approved_by",
            "rejected_at",
            "rejected_by",
            "cancelled_at",
            "cancelled_by",
            "applied_at",
            "applied_by",
            "can_edit",
            "can_submit",
            "can_cancel",
            "can_approve",
            "can_apply",
            "created_at",
            "updated_at",
            "is_active",
        ]
        read_only_fields = fields

    def _actor(self):
        request = self.context.get("request")
        return getattr(request, "user", None)

    def _actor_can_manage(self):
        if not hasattr(self, "_cached_actor_can_manage"):
            actor = self._actor()
            self._cached_actor_can_manage = bool(actor and can_manage_shifts(actor))
        return self._cached_actor_can_manage

    def get_can_edit(self, obj):
        return can_edit_shift_change_request(obj, actor=self._actor())

    def get_can_submit(self, obj):
        return can_submit_shift_change_request(obj, actor=self._actor())

    def get_can_cancel(self, obj):
        actor = self._actor()
        return can_cancel_shift_change_request(obj, actor=actor, manager=self._actor_can_manage())

    def get_can_approve(self, obj):
        return self._actor_can_manage() and obj.status == ShiftChangeRequest.Status.SUBMITTED

    def get_can_apply(self, obj):
        return (
            self._actor_can_manage()
            and obj.status == ShiftChangeRequest.Status.APPROVED
            and obj.request_type != ShiftChangeRequest.RequestType.NOTE
        )


class ShiftChangeRequestSaveSerializer(serializers.Serializer):
    publication_assignment = serializers.PrimaryKeyRelatedField(
        queryset=MonthlyShiftPublicationAssignment.objects.select_related(
            "publication",
            "publication__monthly_shift_plan",
            "publication__location",
            "staff",
        ),
        required=False,
    )
    request_type = serializers.ChoiceField(choices=ShiftChangeRequest.RequestType.choices, required=False)
    priority = serializers.ChoiceField(choices=ShiftChangeRequest.Priority.choices, required=False)
    requested_staff = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.filter(is_active=True),
        required=False,
        allow_null=True,
    )
    requested_work_date = serializers.DateField(required=False, allow_null=True)
    requested_shift_pattern = serializers.PrimaryKeyRelatedField(
        queryset=ShiftPattern.objects.filter(is_active=True),
        required=False,
        allow_null=True,
    )
    requested_start_offset_minutes = serializers.IntegerField(required=False, allow_null=True)
    requested_end_offset_minutes = serializers.IntegerField(required=False, allow_null=True)
    requested_notes = serializers.CharField(required=False, allow_blank=True, trim_whitespace=False)
    reason = serializers.CharField(required=False, allow_blank=True, trim_whitespace=False)
    manager_note = serializers.CharField(required=False, allow_blank=True, trim_whitespace=False)
    submit = serializers.BooleanField(required=False, default=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["requested_staff"].queryset = self.context.get(
            "staff_queryset",
            User.objects.filter(is_active=True),
        )


class ShiftChangeRequestActionSerializer(serializers.Serializer):
    requested_staff = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.filter(is_active=True),
        required=False,
        allow_null=True,
    )
    requested_work_date = serializers.DateField(required=False, allow_null=True)
    requested_shift_pattern = serializers.PrimaryKeyRelatedField(
        queryset=ShiftPattern.objects.filter(is_active=True),
        required=False,
        allow_null=True,
    )
    requested_start_offset_minutes = serializers.IntegerField(required=False, allow_null=True)
    requested_end_offset_minutes = serializers.IntegerField(required=False, allow_null=True)
    manager_note = serializers.CharField(required=False, allow_blank=True, trim_whitespace=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["requested_staff"].queryset = self.context.get(
            "staff_queryset",
            User.objects.filter(is_active=True),
        )


class ShiftChangeRequestManagerNoteSerializer(serializers.Serializer):
    manager_note = serializers.CharField(required=False, allow_blank=True, trim_whitespace=True)


class AttendanceClosingPeriodSerializer(serializers.ModelSerializer):
    location_name = serializers.CharField(source="location.name", read_only=True)
    location_code = serializers.CharField(source="location.code", read_only=True)
    closed_by_display_name = serializers.CharField(source="closed_by.display_name", read_only=True)
    reopened_by_display_name = serializers.CharField(source="reopened_by.display_name", read_only=True)
    created_by_display_name = serializers.CharField(source="created_by.display_name", read_only=True)
    updated_by_display_name = serializers.CharField(source="updated_by.display_name", read_only=True)
    snapshot_count = serializers.SerializerMethodField()
    staff_summary_count = serializers.SerializerMethodField()
    labor_cost_estimate_period = serializers.SerializerMethodField()
    labor_cost_estimate_status = serializers.SerializerMethodField()
    labor_cost_estimate_name = serializers.SerializerMethodField()
    name = serializers.CharField(required=False, allow_blank=True, trim_whitespace=True)

    class Meta:
        model = AttendanceClosingPeriod
        fields = [
            "id",
            "location",
            "location_name",
            "location_code",
            "year",
            "month",
            "name",
            "description",
            "status",
            "content_hash",
            "validation_fingerprint",
            "closed_at",
            "closed_by",
            "closed_by_display_name",
            "reopened_at",
            "reopened_by",
            "reopened_by_display_name",
            "created_by",
            "created_by_display_name",
            "updated_by",
            "updated_by_display_name",
            "snapshot_count",
            "staff_summary_count",
            "labor_cost_estimate_period",
            "labor_cost_estimate_status",
            "labor_cost_estimate_name",
            "created_at",
            "updated_at",
            "is_active",
        ]
        read_only_fields = [
            "id",
            "status",
            "content_hash",
            "validation_fingerprint",
            "closed_at",
            "closed_by",
            "reopened_at",
            "reopened_by",
            "created_by",
            "updated_by",
            "snapshot_count",
            "staff_summary_count",
            "labor_cost_estimate_period",
            "labor_cost_estimate_status",
            "labor_cost_estimate_name",
            "created_at",
            "updated_at",
            "is_active",
        ]

    def get_snapshot_count(self, obj):
        if hasattr(obj, "snapshot_total"):
            return obj.snapshot_total
        return obj.record_snapshots.count()

    def get_staff_summary_count(self, obj):
        if hasattr(obj, "staff_summary_total"):
            return obj.staff_summary_total
        return obj.staff_summaries.count()

    def _labor_cost_period(self, obj):
        if hasattr(obj, "prefetched_labor_cost_periods"):
            return next(iter(obj.prefetched_labor_cost_periods), None)
        return obj.labor_cost_estimate_periods.filter(is_active=True).order_by("created_at").first()

    def get_labor_cost_estimate_period(self, obj):
        period = self._labor_cost_period(obj)
        return str(period.id) if period else None

    def get_labor_cost_estimate_status(self, obj):
        period = self._labor_cost_period(obj)
        return period.status if period else ""

    def get_labor_cost_estimate_name(self, obj):
        period = self._labor_cost_period(obj)
        return period.name if period else ""

    def validate(self, attrs):
        if self.instance is not None:
            if self.instance.status == AttendanceClosingPeriod.Status.ARCHIVED:
                raise serializers.ValidationError({"status": "アーカイブ済みの月次締めは編集できません。"})
            immutable_errors = {}
            for field in ["location", "year", "month"]:
                if field in attrs and attrs[field] != getattr(self.instance, field):
                    immutable_errors[field] = "作成後は変更できません。"
            if immutable_errors:
                raise serializers.ValidationError(immutable_errors)
        return attrs

    def create(self, validated_data):
        actor = self.context["request"].user
        location = validated_data["location"]
        year = validated_data["year"]
        month = validated_data["month"]
        if not validated_data.get("name"):
            validated_data["name"] = f"{location.short_name} {year}-{month:02d} 月次勤怠締め"
        period = AttendanceClosingPeriod(created_by=actor, updated_by=actor, **validated_data)
        period.full_clean()
        period.save()
        return period

    def update(self, instance, validated_data):
        for field in ["name", "description"]:
            if field in validated_data:
                setattr(instance, field, validated_data[field])
        instance.updated_by = self.context["request"].user
        instance.full_clean()
        instance.save()
        return instance


class AttendanceClosingRecordSnapshotSerializer(serializers.ModelSerializer):
    class Meta:
        model = AttendanceClosingRecordSnapshot
        fields = [
            "id",
            "closing_period",
            "attendance_record",
            "location",
            "location_code_snapshot",
            "location_name_snapshot",
            "staff",
            "staff_display_name_snapshot",
            "employee_code_snapshot",
            "work_date",
            "monthly_shift_plan",
            "monthly_shift_assignment",
            "publication",
            "publication_assignment",
            "status_snapshot",
            "source_snapshot",
            "scheduled_start_offset_minutes",
            "scheduled_end_offset_minutes",
            "scheduled_pattern_name_snapshot",
            "scheduled_pattern_short_name_snapshot",
            "actual_clock_in_at",
            "actual_clock_out_at",
            "actual_start_offset_minutes",
            "actual_end_offset_minutes",
            "break_minutes",
            "worked_minutes",
            "difference_start_minutes",
            "difference_end_minutes",
            "difference_worked_minutes",
            "warning_count",
            "warnings",
            "manager_note_snapshot",
            "staff_note_snapshot",
            "confirmed_at",
            "confirmed_by",
            "confirmed_by_display_name_snapshot",
            "created_at",
        ]
        read_only_fields = fields


class AttendanceClosingStaffSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = AttendanceClosingStaffSummary
        fields = [
            "id",
            "closing_period",
            "staff",
            "staff_display_name_snapshot",
            "employee_code_snapshot",
            "scheduled_days",
            "attendance_record_days",
            "worked_days",
            "unscheduled_work_days",
            "scheduled_minutes",
            "worked_minutes",
            "break_minutes",
            "late_count",
            "early_leave_count",
            "missing_clock_in_count",
            "missing_clock_out_count",
            "open_break_count",
            "warning_count",
            "confirmed_count",
            "unconfirmed_count",
            "pending_correction_count",
            "created_at",
        ]
        read_only_fields = fields


class AttendanceClosingCloseSerializer(serializers.Serializer):
    acknowledge_warnings = serializers.BooleanField(default=False)
    validation_fingerprint = serializers.CharField(max_length=64)
    manager_note = serializers.CharField(required=False, allow_blank=True, trim_whitespace=False)


class AttendanceClosingManagerNoteSerializer(serializers.Serializer):
    manager_note = serializers.CharField(required=False, allow_blank=True, trim_whitespace=False)


class StaffCompensationProfileSerializer(serializers.ModelSerializer):
    location_name = serializers.CharField(source="location.name", read_only=True)
    location_code = serializers.CharField(source="location.code", read_only=True)
    staff_display_name = serializers.CharField(source="staff.display_name", read_only=True)
    employee_code = serializers.CharField(source="staff.employee_code", read_only=True)
    created_by_display_name = serializers.CharField(source="created_by.display_name", read_only=True)
    updated_by_display_name = serializers.CharField(source="updated_by.display_name", read_only=True)

    class Meta:
        model = StaffCompensationProfile
        fields = [
            "id",
            "location",
            "location_name",
            "location_code",
            "staff",
            "staff_display_name",
            "employee_code",
            "employment_type",
            "base_hourly_rate",
            "fixed_monthly_amount",
            "valid_from",
            "valid_to",
            "notes",
            "created_by",
            "created_by_display_name",
            "updated_by",
            "updated_by_display_name",
            "created_at",
            "updated_at",
            "is_active",
        ]
        read_only_fields = [
            "id",
            "created_by",
            "updated_by",
            "created_at",
            "updated_at",
        ]

    def create(self, validated_data):
        actor = self.context["request"].user
        profile = StaffCompensationProfile(created_by=actor, updated_by=actor, **validated_data)
        profile.full_clean()
        profile.save()
        return profile

    def update(self, instance, validated_data):
        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.updated_by = self.context["request"].user
        instance.full_clean()
        instance.save()
        return instance


class StaffAllowanceAssignmentSerializer(serializers.ModelSerializer):
    location_name = serializers.CharField(source="location.name", read_only=True)
    location_code = serializers.CharField(source="location.code", read_only=True)
    staff_display_name = serializers.CharField(source="staff.display_name", read_only=True)
    employee_code = serializers.CharField(source="staff.employee_code", read_only=True)
    created_by_display_name = serializers.CharField(source="created_by.display_name", read_only=True)
    updated_by_display_name = serializers.CharField(source="updated_by.display_name", read_only=True)

    class Meta:
        model = StaffAllowanceAssignment
        fields = [
            "id",
            "location",
            "location_name",
            "location_code",
            "staff",
            "staff_display_name",
            "employee_code",
            "code",
            "name",
            "allowance_type",
            "amount",
            "valid_from",
            "valid_to",
            "notes",
            "created_by",
            "created_by_display_name",
            "updated_by",
            "updated_by_display_name",
            "created_at",
            "updated_at",
            "is_active",
        ]
        read_only_fields = [
            "id",
            "created_by",
            "updated_by",
            "created_at",
            "updated_at",
        ]

    def create(self, validated_data):
        actor = self.context["request"].user
        assignment = StaffAllowanceAssignment(created_by=actor, updated_by=actor, **validated_data)
        assignment.full_clean()
        assignment.save()
        return assignment

    def update(self, instance, validated_data):
        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.updated_by = self.context["request"].user
        instance.full_clean()
        instance.save()
        return instance


class LaborCostEstimatePeriodSerializer(serializers.ModelSerializer):
    location_name = serializers.CharField(source="location.name", read_only=True)
    location_code = serializers.CharField(source="location.code", read_only=True)
    attendance_closing_period_name = serializers.CharField(source="attendance_closing_period.name", read_only=True)
    attendance_closing_period_status = serializers.CharField(source="attendance_closing_period.status", read_only=True)
    finalized_by_display_name = serializers.CharField(source="finalized_by.display_name", read_only=True)
    reopened_by_display_name = serializers.CharField(source="reopened_by.display_name", read_only=True)
    created_by_display_name = serializers.CharField(source="created_by.display_name", read_only=True)
    updated_by_display_name = serializers.CharField(source="updated_by.display_name", read_only=True)
    record_snapshot_count = serializers.SerializerMethodField()
    staff_summary_count = serializers.SerializerMethodField()
    allowance_snapshot_count = serializers.SerializerMethodField()
    name = serializers.CharField(required=False, allow_blank=True, trim_whitespace=True)

    class Meta:
        model = LaborCostEstimatePeriod
        fields = [
            "id",
            "location",
            "location_name",
            "location_code",
            "year",
            "month",
            "attendance_closing_period",
            "attendance_closing_period_name",
            "attendance_closing_period_status",
            "name",
            "description",
            "status",
            "content_hash",
            "validation_fingerprint",
            "finalized_at",
            "finalized_by",
            "finalized_by_display_name",
            "reopened_at",
            "reopened_by",
            "reopened_by_display_name",
            "created_by",
            "created_by_display_name",
            "updated_by",
            "updated_by_display_name",
            "record_snapshot_count",
            "staff_summary_count",
            "allowance_snapshot_count",
            "created_at",
            "updated_at",
            "is_active",
        ]
        read_only_fields = [
            "id",
            "status",
            "content_hash",
            "validation_fingerprint",
            "finalized_at",
            "finalized_by",
            "reopened_at",
            "reopened_by",
            "created_by",
            "updated_by",
            "record_snapshot_count",
            "staff_summary_count",
            "allowance_snapshot_count",
            "created_at",
            "updated_at",
            "is_active",
        ]

    def get_record_snapshot_count(self, obj):
        if hasattr(obj, "record_snapshot_total"):
            return obj.record_snapshot_total
        return obj.record_snapshots.count()

    def get_staff_summary_count(self, obj):
        if hasattr(obj, "staff_summary_total"):
            return obj.staff_summary_total
        return obj.staff_summaries.count()

    def get_allowance_snapshot_count(self, obj):
        if hasattr(obj, "allowance_snapshot_total"):
            return obj.allowance_snapshot_total
        return obj.allowance_snapshots.count()

    def validate(self, attrs):
        if self.instance is not None:
            if self.instance.status == LaborCostEstimatePeriod.Status.ARCHIVED:
                raise serializers.ValidationError({"status": "アーカイブ済みの概算人件費periodは編集できません。"})
            immutable_errors = {}
            for field in ["location", "year", "month"]:
                if field in attrs and attrs[field] != getattr(self.instance, field):
                    immutable_errors[field] = "作成後は変更できません。"
            if immutable_errors:
                raise serializers.ValidationError(immutable_errors)
        return attrs

    def create(self, validated_data):
        actor = self.context["request"].user
        location = validated_data["location"]
        year = validated_data["year"]
        month = validated_data["month"]
        if not validated_data.get("name"):
            validated_data["name"] = f"{location.short_name} {year}-{month:02d} 概算人件費"
        period = LaborCostEstimatePeriod(created_by=actor, updated_by=actor, **validated_data)
        period.full_clean()
        period.save()
        return period

    def update(self, instance, validated_data):
        for field in ["attendance_closing_period", "name", "description"]:
            if field in validated_data:
                setattr(instance, field, validated_data[field])
        instance.updated_by = self.context["request"].user
        instance.full_clean()
        instance.save()
        return instance


class LaborCostEstimateRecordSnapshotSerializer(serializers.ModelSerializer):
    class Meta:
        model = LaborCostEstimateRecordSnapshot
        fields = [
            "id",
            "estimate_period",
            "attendance_closing_snapshot",
            "attendance_record",
            "location",
            "location_code_snapshot",
            "location_name_snapshot",
            "staff",
            "staff_display_name_snapshot",
            "employee_code_snapshot",
            "work_date",
            "employment_type_snapshot",
            "base_hourly_rate_snapshot",
            "fixed_monthly_amount_snapshot",
            "worked_minutes",
            "worked_hours_decimal",
            "base_pay",
            "allowance_total",
            "estimated_total",
            "warning_count",
            "warnings",
            "error_count",
            "errors",
            "created_at",
        ]
        read_only_fields = fields


class LaborCostEstimateStaffSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = LaborCostEstimateStaffSummary
        fields = [
            "id",
            "estimate_period",
            "staff",
            "staff_display_name_snapshot",
            "employee_code_snapshot",
            "employment_type_snapshot",
            "base_hourly_rate_snapshot",
            "fixed_monthly_amount_snapshot",
            "worked_days",
            "worked_minutes",
            "worked_hours_decimal",
            "base_pay_total",
            "allowance_total",
            "estimated_total",
            "warning_count",
            "error_count",
            "created_at",
        ]
        read_only_fields = fields


class LaborCostEstimateAllowanceSnapshotSerializer(serializers.ModelSerializer):
    class Meta:
        model = LaborCostEstimateAllowanceSnapshot
        fields = [
            "id",
            "estimate_period",
            "staff",
            "staff_display_name_snapshot",
            "employee_code_snapshot",
            "allowance_assignment",
            "code_snapshot",
            "name_snapshot",
            "allowance_type_snapshot",
            "amount_snapshot",
            "quantity",
            "estimated_amount",
            "warning_count",
            "warnings",
            "created_at",
        ]
        read_only_fields = fields


class LaborCostEstimateFinalizeSerializer(serializers.Serializer):
    acknowledge_warnings = serializers.BooleanField(default=False)
    validation_fingerprint = serializers.CharField(max_length=64)
    manager_note = serializers.CharField(required=False, allow_blank=True, trim_whitespace=False)


class LaborCostEstimateManagerNoteSerializer(serializers.Serializer):
    manager_note = serializers.CharField(required=False, allow_blank=True, trim_whitespace=False)


class LaborCostBudgetPeriodSerializer(serializers.ModelSerializer):
    location_name = serializers.CharField(source="location.name", read_only=True)
    location_code = serializers.CharField(source="location.code", read_only=True)
    source_monthly_shift_plan_name = serializers.CharField(source="source_monthly_shift_plan.name", read_only=True)
    source_publication_version = serializers.IntegerField(source="source_publication.version", read_only=True)
    approved_by_display_name = serializers.CharField(source="approved_by.display_name", read_only=True)
    reopened_by_display_name = serializers.CharField(source="reopened_by.display_name", read_only=True)
    created_by_display_name = serializers.CharField(source="created_by.display_name", read_only=True)
    updated_by_display_name = serializers.CharField(source="updated_by.display_name", read_only=True)
    plan_record_snapshot_count = serializers.SerializerMethodField()
    staff_summary_count = serializers.SerializerMethodField()
    daily_summary_count = serializers.SerializerMethodField()
    allowance_snapshot_count = serializers.SerializerMethodField()
    name = serializers.CharField(required=False, allow_blank=True, trim_whitespace=True)

    class Meta:
        model = LaborCostBudgetPeriod
        validators = []
        fields = [
            "id",
            "location",
            "location_name",
            "location_code",
            "year",
            "month",
            "name",
            "description",
            "budget_amount",
            "warning_threshold_percent",
            "critical_threshold_percent",
            "source_monthly_shift_plan",
            "source_monthly_shift_plan_name",
            "source_publication",
            "source_publication_version",
            "status",
            "content_hash",
            "validation_fingerprint",
            "approved_at",
            "approved_by",
            "approved_by_display_name",
            "reopened_at",
            "reopened_by",
            "reopened_by_display_name",
            "created_by",
            "created_by_display_name",
            "updated_by",
            "updated_by_display_name",
            "plan_record_snapshot_count",
            "staff_summary_count",
            "daily_summary_count",
            "allowance_snapshot_count",
            "created_at",
            "updated_at",
            "is_active",
        ]
        read_only_fields = [
            "id",
            "source_monthly_shift_plan",
            "source_publication",
            "status",
            "content_hash",
            "validation_fingerprint",
            "approved_at",
            "approved_by",
            "reopened_at",
            "reopened_by",
            "created_by",
            "updated_by",
            "plan_record_snapshot_count",
            "staff_summary_count",
            "daily_summary_count",
            "allowance_snapshot_count",
            "created_at",
            "updated_at",
            "is_active",
        ]

    def _count(self, obj, annotation, relation):
        if hasattr(obj, annotation):
            return getattr(obj, annotation)
        return getattr(obj, relation).count()

    def get_plan_record_snapshot_count(self, obj):
        return self._count(obj, "plan_record_snapshot_total", "plan_record_snapshots")

    def get_staff_summary_count(self, obj):
        return self._count(obj, "budget_staff_summary_total", "staff_summaries")

    def get_daily_summary_count(self, obj):
        return self._count(obj, "daily_summary_total", "daily_summaries")

    def get_allowance_snapshot_count(self, obj):
        return self._count(obj, "budget_allowance_snapshot_total", "allowance_snapshots")

    def validate(self, attrs):
        if self.instance is not None:
            if self.instance.status == LaborCostBudgetPeriod.Status.ARCHIVED:
                raise serializers.ValidationError({"status": "アーカイブ済みの予算periodは編集できません。"})
            if self.instance.status == LaborCostBudgetPeriod.Status.APPROVED:
                raise serializers.ValidationError(
                    {"status": "承認済みの予算periodは再オープンしてから編集してください。"}
                )
            immutable_errors = {}
            for field in ["location", "year", "month"]:
                if field in attrs and attrs[field] != getattr(self.instance, field):
                    immutable_errors[field] = "作成後は変更できません。"
            if immutable_errors:
                raise serializers.ValidationError(immutable_errors)
        return attrs

    def create(self, validated_data):
        actor = self.context["request"].user
        if not validated_data.get("name"):
            location = validated_data["location"]
            validated_data["name"] = (
                f"{location.short_name} {validated_data['year']}-{validated_data['month']:02d} 人件費予算"
            )
        period = LaborCostBudgetPeriod(created_by=actor, updated_by=actor, **validated_data)
        period.full_clean()
        period.save()
        return period

    def update(self, instance, validated_data):
        for field in [
            "name",
            "description",
            "budget_amount",
            "warning_threshold_percent",
            "critical_threshold_percent",
        ]:
            if field in validated_data:
                setattr(instance, field, validated_data[field])
        instance.updated_by = self.context["request"].user
        instance.full_clean()
        instance.save()
        return instance


class LaborCostBudgetPlanRecordSnapshotSerializer(serializers.ModelSerializer):
    class Meta:
        model = LaborCostBudgetPlanRecordSnapshot
        fields = "__all__"


class LaborCostBudgetStaffSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = LaborCostBudgetStaffSummary
        fields = "__all__"


class LaborCostBudgetDailySummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = LaborCostBudgetDailySummary
        fields = "__all__"


class LaborCostBudgetAllowanceSnapshotSerializer(serializers.ModelSerializer):
    class Meta:
        model = LaborCostBudgetAllowanceSnapshot
        fields = "__all__"


class LaborCostBudgetApproveSerializer(serializers.Serializer):
    acknowledge_warnings = serializers.BooleanField(default=False)
    validation_fingerprint = serializers.CharField(max_length=64)
    manager_note = serializers.CharField(required=False, allow_blank=True, trim_whitespace=False)


class LaborCostBudgetManagerNoteSerializer(serializers.Serializer):
    manager_note = serializers.CharField(required=False, allow_blank=True, trim_whitespace=False)


class AttendanceEventSerializer(serializers.ModelSerializer):
    actor_display_name = serializers.CharField(source="actor.display_name", read_only=True)

    class Meta:
        model = AttendanceEvent
        fields = [
            "id",
            "attendance_record",
            "event_type",
            "occurred_at",
            "offset_minutes",
            "source",
            "actor",
            "actor_display_name",
            "note",
            "metadata",
            "created_at",
        ]
        read_only_fields = fields


class AttendanceCorrectionRequestSerializer(serializers.ModelSerializer):
    location = serializers.UUIDField(source="attendance_record.location_id", read_only=True)
    location_name = serializers.CharField(source="attendance_record.location.name", read_only=True)
    work_date = serializers.DateField(source="attendance_record.work_date", read_only=True)
    staff = serializers.UUIDField(source="attendance_record.staff_id", read_only=True)
    staff_display_name = serializers.CharField(source="attendance_record.staff.display_name", read_only=True)
    requester_display_name = serializers.CharField(source="requester.display_name", read_only=True)
    approved_by_display_name = serializers.CharField(source="approved_by.display_name", read_only=True)
    rejected_by_display_name = serializers.CharField(source="rejected_by.display_name", read_only=True)
    cancelled_by_display_name = serializers.CharField(source="cancelled_by.display_name", read_only=True)
    applied_by_display_name = serializers.CharField(source="applied_by.display_name", read_only=True)
    can_edit = serializers.SerializerMethodField()
    can_submit = serializers.SerializerMethodField()
    can_cancel = serializers.SerializerMethodField()
    can_approve = serializers.SerializerMethodField()
    can_apply = serializers.SerializerMethodField()

    class Meta:
        model = AttendanceCorrectionRequest
        fields = [
            "id",
            "attendance_record",
            "location",
            "location_name",
            "work_date",
            "staff",
            "staff_display_name",
            "requester",
            "requester_display_name",
            "status",
            "requested_clock_in_at",
            "requested_clock_out_at",
            "requested_break_minutes",
            "requested_staff_note",
            "reason",
            "manager_note",
            "submitted_at",
            "approved_at",
            "approved_by",
            "approved_by_display_name",
            "rejected_at",
            "rejected_by",
            "rejected_by_display_name",
            "cancelled_at",
            "cancelled_by",
            "cancelled_by_display_name",
            "applied_at",
            "applied_by",
            "applied_by_display_name",
            "can_edit",
            "can_submit",
            "can_cancel",
            "can_approve",
            "can_apply",
            "created_at",
            "updated_at",
            "is_active",
        ]
        read_only_fields = fields

    def _actor(self):
        request = self.context.get("request")
        return getattr(request, "user", None)

    def _actor_can_manage(self):
        if not hasattr(self, "_cached_actor_can_manage"):
            actor = self._actor()
            self._cached_actor_can_manage = bool(actor and can_manage_shifts(actor))
        return self._cached_actor_can_manage

    def get_can_edit(self, obj):
        actor = self._actor()
        return bool(actor and obj.requester_id == actor.id and obj.status == AttendanceCorrectionRequest.Status.DRAFT)

    def get_can_submit(self, obj):
        return self.get_can_edit(obj)

    def get_can_cancel(self, obj):
        actor = self._actor()
        return bool(
            actor
            and obj.requester_id == actor.id
            and obj.status
            in {
                AttendanceCorrectionRequest.Status.DRAFT,
                AttendanceCorrectionRequest.Status.SUBMITTED,
                AttendanceCorrectionRequest.Status.APPROVED,
            }
        )

    def get_can_approve(self, obj):
        return self._actor_can_manage() and obj.status == AttendanceCorrectionRequest.Status.SUBMITTED

    def get_can_apply(self, obj):
        return self._actor_can_manage() and obj.status == AttendanceCorrectionRequest.Status.APPROVED


class AttendanceRecordSerializer(serializers.ModelSerializer):
    location_name = serializers.CharField(source="location.name", read_only=True)
    staff_display_name = serializers.CharField(source="staff.display_name", read_only=True)
    employee_code = serializers.CharField(source="staff.employee_code", read_only=True)
    confirmed_by_display_name = serializers.CharField(source="confirmed_by.display_name", read_only=True)
    events = AttendanceEventSerializer(many=True, read_only=True)
    correction_requests = AttendanceCorrectionRequestSerializer(many=True, read_only=True)
    can_clock_in = serializers.SerializerMethodField()
    can_break_start = serializers.SerializerMethodField()
    can_break_end = serializers.SerializerMethodField()
    can_clock_out = serializers.SerializerMethodField()
    can_request_correction = serializers.SerializerMethodField()
    can_manage = serializers.SerializerMethodField()
    is_month_closed = serializers.SerializerMethodField()
    closing_period = serializers.SerializerMethodField()
    closing_period_name = serializers.SerializerMethodField()

    class Meta:
        model = AttendanceRecord
        fields = [
            "id",
            "location",
            "location_name",
            "staff",
            "staff_display_name",
            "employee_code",
            "work_date",
            "monthly_shift_plan",
            "monthly_shift_assignment",
            "publication",
            "publication_assignment",
            "status",
            "source",
            "scheduled_start_offset_minutes",
            "scheduled_end_offset_minutes",
            "scheduled_pattern_name_snapshot",
            "scheduled_pattern_short_name_snapshot",
            "actual_clock_in_at",
            "actual_clock_out_at",
            "actual_start_offset_minutes",
            "actual_end_offset_minutes",
            "break_minutes",
            "worked_minutes",
            "difference_start_minutes",
            "difference_end_minutes",
            "difference_worked_minutes",
            "warning_count",
            "warnings",
            "manager_note",
            "staff_note",
            "confirmed_at",
            "confirmed_by",
            "confirmed_by_display_name",
            "events",
            "correction_requests",
            "can_clock_in",
            "can_break_start",
            "can_break_end",
            "can_clock_out",
            "can_request_correction",
            "can_manage",
            "is_month_closed",
            "closing_period",
            "closing_period_name",
            "created_at",
            "updated_at",
            "is_active",
        ]
        read_only_fields = fields

    def _actor(self):
        request = self.context.get("request")
        return getattr(request, "user", None)

    def _actor_can_manage(self):
        if not hasattr(self, "_cached_actor_can_manage"):
            actor = self._actor()
            self._cached_actor_can_manage = bool(actor and can_manage_shifts(actor))
        return self._cached_actor_can_manage

    def _closed_period(self, obj):
        lookup = self.context.get("closed_period_lookup")
        if lookup is not None:
            return closed_period_from_lookup(
                lookup,
                location_id=obj.location_id,
                work_date=obj.work_date,
            )
        return is_attendance_period_closed(obj.location, obj.work_date)

    def _self_operable(self, obj):
        actor = self._actor()
        return bool(
            actor
            and obj.staff_id == actor.id
            and obj.is_active
            and self._closed_period(obj) is None
            and obj.status
            not in {
                AttendanceRecord.Status.CONFIRMED,
                AttendanceRecord.Status.VOID,
            }
        )

    def get_can_clock_in(self, obj):
        return self._self_operable(obj) and obj.actual_clock_in_at is None

    def get_can_break_start(self, obj):
        return self._self_operable(obj) and obj.status == AttendanceRecord.Status.CLOCKED_IN

    def get_can_break_end(self, obj):
        return self._self_operable(obj) and obj.status == AttendanceRecord.Status.ON_BREAK

    def get_can_clock_out(self, obj):
        return self._self_operable(obj) and obj.status == AttendanceRecord.Status.CLOCKED_IN

    def get_can_request_correction(self, obj):
        return self._self_operable(obj)

    def get_can_manage(self, obj):
        return self._actor_can_manage() and self._closed_period(obj) is None

    def get_is_month_closed(self, obj):
        return self._closed_period(obj) is not None

    def get_closing_period(self, obj):
        period = self._closed_period(obj)
        return str(period.id) if period else None

    def get_closing_period_name(self, obj):
        period = self._closed_period(obj)
        return period.name if period else ""


class AttendanceClockInSerializer(serializers.Serializer):
    location = serializers.PrimaryKeyRelatedField(queryset=Location.objects.filter(is_active=True))
    work_date = serializers.DateField()
    occurred_at = serializers.DateTimeField(required=False, allow_null=True)
    note = serializers.CharField(required=False, allow_blank=True, trim_whitespace=False)


class AttendanceClockEventSerializer(serializers.Serializer):
    occurred_at = serializers.DateTimeField(required=False, allow_null=True)
    note = serializers.CharField(required=False, allow_blank=True, trim_whitespace=False)


class AttendanceManualAdjustSerializer(serializers.Serializer):
    actual_clock_in_at = serializers.DateTimeField()
    actual_clock_out_at = serializers.DateTimeField()
    break_minutes = serializers.IntegerField(min_value=0, default=0)
    manager_note = serializers.CharField(required=False, allow_blank=True, trim_whitespace=False)


class AttendanceManagerNoteSerializer(serializers.Serializer):
    manager_note = serializers.CharField(required=False, allow_blank=True, trim_whitespace=False)


class AttendanceCorrectionSaveSerializer(serializers.Serializer):
    attendance_record = serializers.PrimaryKeyRelatedField(
        queryset=AttendanceRecord.objects.select_related("location", "staff").filter(is_active=True),
        required=False,
    )
    requested_clock_in_at = serializers.DateTimeField(required=False, allow_null=True)
    requested_clock_out_at = serializers.DateTimeField(required=False, allow_null=True)
    requested_break_minutes = serializers.IntegerField(required=False, allow_null=True, min_value=0)
    requested_staff_note = serializers.CharField(required=False, allow_blank=True, trim_whitespace=False)
    reason = serializers.CharField(required=False, allow_blank=True, trim_whitespace=False)
    submit = serializers.BooleanField(required=False, default=False)


class ShiftRequestItemSerializer(serializers.ModelSerializer):
    work_type_name = serializers.CharField(source="work_type.name", read_only=True)
    work_area_name = serializers.CharField(source="work_area.name", read_only=True)

    class Meta:
        model = ShiftRequestItem
        fields = [
            "id",
            "request_type",
            "work_date",
            "start_offset_minutes",
            "end_offset_minutes",
            "work_type",
            "work_type_name",
            "work_area",
            "work_area_name",
            "priority",
            "reason",
            "notes",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "is_active", "created_at", "updated_at"]


class ShiftRequestPeriodSerializer(serializers.ModelSerializer):
    location_name = serializers.CharField(source="location.name", read_only=True)
    draft_count = serializers.IntegerField(read_only=True, default=0)
    submitted_count = serializers.IntegerField(read_only=True, default=0)
    returned_count = serializers.IntegerField(read_only=True, default=0)
    locked_count = serializers.IntegerField(read_only=True, default=0)
    submission_count = serializers.IntegerField(read_only=True, default=0)
    item_count = serializers.IntegerField(read_only=True, default=0)
    target_staff_count = serializers.SerializerMethodField()
    not_created_count = serializers.SerializerMethodField()
    my_submission = serializers.SerializerMethodField()

    class Meta:
        model = ShiftRequestPeriod
        fields = [
            "id",
            "location",
            "location_name",
            "year",
            "month",
            "name",
            "description",
            "opens_at",
            "closes_at",
            "status",
            "draft_count",
            "submitted_count",
            "returned_count",
            "locked_count",
            "submission_count",
            "item_count",
            "target_staff_count",
            "not_created_count",
            "my_submission",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "status", "created_at", "updated_at"]

    def get_target_staff_count(self, obj):
        if hasattr(obj, "target_staff_count"):
            return obj.target_staff_count
        target_counts = self.context.get("target_staff_counts", {})
        if str(obj.id) in target_counts:
            return target_counts[str(obj.id)]
        return count_shift_request_target_staff(obj)

    def get_not_created_count(self, obj):
        return max(self.get_target_staff_count(obj) - getattr(obj, "submission_count", 0), 0)

    def get_my_submission(self, obj):
        submission_map = self.context.get("my_submission_map")
        submission = submission_map.get(str(obj.id)) if submission_map is not None else None
        if submission is None:
            return None
        return {
            "id": str(submission.id),
            "status": submission.status,
            "submitted_at": submission.submitted_at,
            "item_count": getattr(submission, "item_count", 0),
            "can_edit": can_edit_shift_request_submission(submission),
            "can_submit": can_submit_shift_request_submission(submission),
        }


class ShiftRequestSubmissionSerializer(serializers.ModelSerializer):
    period = serializers.SerializerMethodField()
    staff_display_name = serializers.CharField(source="staff.display_name", read_only=True)
    item_count = serializers.IntegerField(read_only=True, default=0)
    day_off_count = serializers.IntegerField(read_only=True, default=0)
    unavailable_count = serializers.IntegerField(read_only=True, default=0)
    prefer_count = serializers.IntegerField(read_only=True, default=0)
    has_note = serializers.BooleanField(read_only=True, default=False)
    can_edit = serializers.SerializerMethodField()
    can_submit = serializers.SerializerMethodField()
    items = serializers.SerializerMethodField()

    class Meta:
        model = ShiftRequestSubmission
        fields = [
            "id",
            "request_period",
            "period",
            "staff",
            "staff_display_name",
            "status",
            "can_edit",
            "can_submit",
            "submitted_at",
            "submitted_by",
            "returned_at",
            "returned_by",
            "return_reason",
            "notes",
            "item_count",
            "day_off_count",
            "unavailable_count",
            "prefer_count",
            "has_note",
            "items",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "request_period",
            "staff",
            "status",
            "submitted_at",
            "submitted_by",
            "returned_at",
            "returned_by",
            "return_reason",
            "created_at",
            "updated_at",
        ]

    def get_period(self, obj):
        period = obj.request_period
        return {
            "id": str(period.id),
            "location": str(period.location_id),
            "location_name": period.location.name,
            "year": period.year,
            "month": period.month,
            "name": period.name,
            "status": period.status,
            "opens_at": period.opens_at,
            "closes_at": period.closes_at,
        }

    def get_can_edit(self, obj):
        return can_edit_shift_request_submission(obj)

    def get_can_submit(self, obj):
        return can_submit_shift_request_submission(obj)

    def get_items(self, obj):
        items = [item for item in obj.items.all() if item.is_active]
        return ShiftRequestItemSerializer(items, many=True).data


class ShiftRequestSubmissionSaveSerializer(serializers.Serializer):
    notes = serializers.CharField(required=False, allow_blank=True)
    items = ShiftRequestItemSerializer(many=True, required=False)


class ShiftRequestReturnSerializer(serializers.Serializer):
    reason = serializers.CharField(required=True, allow_blank=False)
