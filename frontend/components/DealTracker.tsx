"use client";

const BASE_FLOW = [
  "LEAD",
  "PRE_QUALIFYING",
  "QUALIFIED",
  "ENGAGED",
  "PROFILED",
  "MATCHING",
  "VEHICLE_SELECTED",
  "FUNDING",
  "ACQUISITION_PENDING",
  "ACQUIRED",
  "IN_TRANSIT",
  "DELIVERED",
];

const DISPLAY_NAMES: Record<string, string> = {
  FUNDING: "FINANCE",
};

const STAGES = [
  ...BASE_FLOW,
  "RETURN_PENDING",
  "CLOSED_WON",
  "CLOSED_LOST"
] as const;

type StageStatus = "completed" | "current" | "upcoming";

function getStageStatus(item: string, currentStage: string): StageStatus {
  if (item === currentStage) return "current";

  const baseIndex = BASE_FLOW.indexOf(currentStage);
  const itemBaseIndex = BASE_FLOW.indexOf(item);

  if (baseIndex >= 0) {
    if (itemBaseIndex >= 0 && itemBaseIndex < baseIndex) {
      return "completed";
    }
    return "upcoming";
  }

  if (currentStage === "RETURN_PENDING" || currentStage === "CLOSED_WON") {
    if (itemBaseIndex >= 0) {
      return "completed";
    }
  }

  return "upcoming";
}

function stageStatusLabel(status: StageStatus): string {
  if (status === "completed") return "Completed";
  if (status === "current") return "Current stage";
  return "Upcoming";
}

export function DealTracker({ stage }: { stage: string }) {
  const normalizedStage = stage || "LEAD";
  const trackerStages = STAGES.includes(normalizedStage as (typeof STAGES)[number]) ? STAGES : [...STAGES, normalizedStage];

  return (
    <div className="stage-track">
      {trackerStages.map((item) => {
        const status = getStageStatus(item, normalizedStage);
        return (
          <div key={item} className={`stage-pill stage-pill-${status}`}>
            <span className="stage-pill-status">{stageStatusLabel(status)}</span>
            <strong>{DISPLAY_NAMES[item] || item.replaceAll("_", " ")}</strong>
          </div>
        );
      })}
    </div>
  );
}
