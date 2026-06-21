export const capabilityLevelLabels = {
  trainee: "研修中",
  assisted: "補助付きで対応可能",
  independent: "単独対応可能",
  trainer: "指導者",
} as const;

export const capabilityLevelOptions = Object.entries(capabilityLevelLabels).map(([value, label]) => ({
  value,
  label,
}));

export function formatCapabilityLevel(level: string | null | undefined) {
  if (!level) {
    return "-";
  }
  return capabilityLevelLabels[level as keyof typeof capabilityLevelLabels] ?? level;
}
