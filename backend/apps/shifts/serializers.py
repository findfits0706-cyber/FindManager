from rest_framework import serializers

from .models import (
    MonthlyShiftAssignment,
    MonthlyShiftPlan,
    MonthlyShiftSegment,
    ShiftPattern,
    ShiftPatternSegment,
    WeeklyShiftTemplate,
    WeeklyShiftTemplateEntry,
)
from .services import save_monthly_assignment, save_monthly_plan, save_shift_pattern, save_weekly_template

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
    assignment_count = serializers.SerializerMethodField()
    staff_count = serializers.SerializerMethodField()

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
            "is_active",
            "created_at",
            "updated_at",
        ]
        validators = []

    def get_assignment_count(self, obj):
        return obj.assignments.filter(is_active=True).count()

    def get_staff_count(self, obj):
        return obj.assignments.filter(is_active=True).values("staff_id").distinct().count()

    def validate(self, attrs):
        forbidden = {"is_active", "created_at", "updated_at", "last_generated_at", "last_generated_by"}.intersection(
            self.initial_data
        )
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
