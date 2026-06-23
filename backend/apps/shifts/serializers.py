from rest_framework import serializers

from .models import ShiftPattern, ShiftPatternSegment, WeeklyShiftTemplate, WeeklyShiftTemplateEntry
from .services import save_shift_pattern, save_weekly_template

FORBIDDEN_CHILD_FIELDS = {"is_active", "created_at", "updated_at"}
IMMUTABLE_LOCATION_MESSAGE = "拠点は作成後変更できません。別拠点用に複製してください。"


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
