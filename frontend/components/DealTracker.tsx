"use client";

const STAGES = [
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
  "RETURN_PENDING",
  "CLOSED_WON",
  "CLOSED_LOST"
];

export function DealTracker({ stage }: { stage: string }) {
  const activeIndex = STAGES.indexOf(stage);
  return (
    <div className="stage-track">
      {STAGES.map((item, index) => (
        <div key={item} className={`stage-pill ${index <= activeIndex ? "active" : ""}`}>
          {item.replaceAll("_", " ")}
        </div>
      ))}
    </div>
  );
}
