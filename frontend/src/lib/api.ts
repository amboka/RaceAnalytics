const API_BASE = "http://localhost:8000/api";

class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export interface LapTimeResponse {
  header: { segment: string };
  slow_race: {
    race_id: string;
    duration: { seconds: number; milliseconds: number };
  };
  fast_race: {
    race_id: string;
    duration: { seconds: number; milliseconds: number };
  };
  difference: {
    slow_minus_fast: { seconds: number };
  };
}

export interface TopSpeedResponse {
  topSpeeds: {
    race_id: string;
    top_speed_mps: number;
  }[];
}

export interface TimeLostPerSectionResponse {
  timeLostPerSection: {
    snake: number;
    long: number;
    corner: number;
  };
}

export interface BrakingEfficiencyResponse {
  brakingEfficiency: {
    score: number | null;
    rating: string | null;
    timeLostUnderBraking: { seconds: number } | null;
    weakestSection: string | null;
    sections: {
      section: string;
      score: number;
      time_lost: { seconds: number };
      race?: {
        score: number;
        rating: string;
        timeLostUnderBraking: { seconds: number };
      };
    }[];
  };
}

export interface GripUtilizationResponse {
  gripUtilization: {
    score: number | null;
    rating: string | null;
    overallStatus: string | null;
    weakestSection: string | null;
    sections: {
      section: string;
      status: string;
      score: number;
      race?: {
        score: number;
        rating: string;
        overallStatus: string;
      };
    }[];
  };
}

export interface TrajectoryPoint {
  x_m: number;
  y_m: number;
}

export interface RaceTrajectory {
  race_id: string;
  point_count: number;
  sample_step: number;
  points: TrajectoryPoint[];
}

export interface TrajectoriesResponse {
  currentLap: RaceTrajectory;
  bestLap: RaceTrajectory;
}

const fetchJson = async <T>(path: string): Promise<T> => {
  const response = await fetch(`${API_BASE}${path}`);
  const payload = await response.json().catch(() => null);

  if (!response.ok) {
    const message =
      payload && typeof payload === "object" && "error" in payload && typeof payload.error === "string"
        ? payload.error
        : `Request failed with status ${response.status}`;
    throw new ApiError(message, response.status);
  }

  return payload as T;
};

export const fetchLapTime = (segment?: string): Promise<LapTimeResponse> =>
  fetchJson(`/getLapTime${joinParams(segment ? `segment=${encodeURIComponent(segment)}` : "")}`);

export interface TimeRange {
  start_ns: string;
  end_ns: string;
}

const timeRangeParams = (tr?: TimeRange) =>
  tr ? `start_ns=${tr.start_ns}&end_ns=${tr.end_ns}` : "";

const joinParams = (...parts: string[]) => {
  const filled = parts.filter(Boolean);
  return filled.length ? `?${filled.join("&")}` : "";
};

export const fetchTopSpeed = (tr?: TimeRange): Promise<TopSpeedResponse> =>
  fetchJson(`/topSpeed${joinParams(timeRangeParams(tr))}`);

export const fetchTimeLostPerSection = (): Promise<TimeLostPerSectionResponse> =>
  fetchJson("/timeLostPerSection");

export const fetchBrakingEfficiency = (tr?: TimeRange): Promise<BrakingEfficiencyResponse> =>
  fetchJson(`/brakingEfficiency${joinParams("race_id=slow", "reference_race_id=fast", timeRangeParams(tr))}`);

export const fetchGripUtilization = (tr?: TimeRange): Promise<GripUtilizationResponse> =>
  fetchJson(`/gripUtilization${joinParams("race_id=slow", "reference_race_id=fast", timeRangeParams(tr))}`);

export const fetchTrajectories = (
  currentRaceId = "0",
  bestRaceId = "1",
): Promise<TrajectoriesResponse> =>
  fetchJson(`/trajectories?current_race_id=${encodeURIComponent(currentRaceId)}&best_race_id=${encodeURIComponent(bestRaceId)}`);

// Engine comparison types & fetchers

export interface ThrottleComparisonResponse {
  series: {
    distanceM: number[];
    progressRatio: number[];
    lapThrottlePct: number[];
    referenceThrottlePct: number[];
    deltaThrottlePct: number[];
  };
  highlights: { startDistanceM: number; endDistanceM: number }[];
}

export interface GearboxComparisonResponse {
  series: {
    distanceM: number[];
    lapGear: number[];
    referenceGear: number[];
    lapSpeedMps: number[];
    referenceSpeedMps: number[];
  };
  summary: {
    earlierShiftCount: number;
    laterShiftCount: number;
    mismatchZoneCount: number;
  };
}

export interface RpmComparisonResponse {
  series: {
    distanceM: number[];
    lapRpm: number[];
    referenceRpm: number[];
  };
}

export const fetchThrottleComparison = (
  slowId = "slow",
  fastId = "fast",
  points = 600,
): Promise<ThrottleComparisonResponse> =>
  fetchJson(`/engine/throttleComparison?slow_race_id=${slowId}&fast_race_id=${fastId}&n_points=${points}`);

export const fetchGearboxComparison = (
  slowId = "slow",
  fastId = "fast",
  points = 600,
): Promise<GearboxComparisonResponse> =>
  fetchJson(`/engine/gearboxAndShift/comparison?slow_race_id=${slowId}&fast_race_id=${fastId}&n_points=${points}`);

export const fetchRpmComparison = (
  slowId = "slow",
  fastId = "fast",
  points = 600,
): Promise<RpmComparisonResponse> =>
  fetchJson(`/engine/rpm/comparison?slow_race_id=${slowId}&fast_race_id=${fastId}&n_points=${points}`);

// Steering types & fetchers

export interface SteeringAngleRaceSeries {
  tsNs: number[];
  steeringAngleRad: number[];
  steeringAngleDeg: number[];
}

export interface SteeringAngleRace {
  raceId: string;
  sampleCount: number;
  series: SteeringAngleRaceSeries;
}

export interface SteeringAngleResponse {
  signal: { source: string; unit: string; outputSampleHz: number };
  raceCount: number;
  races: SteeringAngleRace[];
}

export interface OverUnderSteerRaceSeries {
  tsNs: number[];
  steeringAngleRad: number[];
  speedMps: number[];
  yawRateMeasuredRadPs: number[];
  yawRateExpectedRadPs: number[];
  yawRateErrorRadPs: number[];
  balanceScore: number[];
  balanceClass: string[];
  isCornering: boolean[];
}

export interface OverUnderSteerRace {
  raceId: string;
  sampleCount: number;
  summary: {
    corneringSampleCount: number;
    understeerCount: number;
    oversteerCount: number;
    neutralCount: number;
  };
  series: OverUnderSteerRaceSeries;
}

export interface OverUnderSteerResponse {
  method: { name: string; scoreDefinition: string };
  config: Record<string, number>;
  raceCount: number;
  races: OverUnderSteerRace[];
}

export interface SlipCoachingRaceSeries {
  tsNs: number[];
  speedMps: number[];
  lateralAccelMps2: number[];
  lateralG: number[];
  frontSlipDeg: number[];
  rearSlipDeg: number[];
  maxSlipDeg: number[];
  slipBalanceDeg: number[];
  gripUsageRatio: number[];
  coachingState: string[];
  balanceHint: string[];
  isHighDemandCornering: boolean[];
}

export interface SlipCoachingRace {
  raceId: string;
  sampleCount: number;
  summary: {
    analyzedSampleCount: number;
    belowOptimalSlipCount: number;
    inOptimalWindowCount: number;
    overLimitSlipCount: number;
    frontLimitedCount: number;
    rearLimitedCount: number;
    medianMaxSlipDeg: number;
    p95MaxSlipDeg: number;
    avgAbsLateralG: number;
  };
  series: SlipCoachingRaceSeries;
}

export interface SlipCoachingResponse {
  method: { name: string };
  config: Record<string, number>;
  raceCount: number;
  races: SlipCoachingRace[];
}

export const fetchSteeringAngle = (): Promise<SteeringAngleResponse> =>
  fetchJson("/steering/getSteeringAngle");

export const fetchOverUnderSteer = (): Promise<OverUnderSteerResponse> =>
  fetchJson("/steering/getOverUnderSteer");

export const fetchSlipCoachingMetrics = (): Promise<SlipCoachingResponse> =>
  fetchJson("/steering/getSlipCoachingMetrics");

// Brakes types & fetchers

export interface BrakePressureComparisonResponse {
  lap: { lapId: string; raceId: string; lapNumber: number };
  referenceLap: { lapId: string; raceId: string; lapNumber: number };
  signal: { mode: string; unit: string; activeThreshold: number };
  alignment: {
    basis: string;
    referencePathLengthM: number;
    pointCount: number;
    outputSampleHz: number;
  };
  series: {
    progressRatio: number[];
    distanceM: number[];
    lapBrakePressure: number[];
    referenceBrakePressure: number[];
    deltaBrakePressure: number[];
    lapElapsedMs: number[];
    referenceElapsedMs: number[];
  };
  brakingZones: {
    zoneIndex: number;
    startProgress: number;
    endProgress: number;
    lap: { onsetDistanceM: number; releaseDistanceM: number; peakPressure: number };
    reference: { onsetDistanceM: number; releaseDistanceM: number; peakPressure: number };
    differences: { onsetDeltaM: number; releaseDeltaM: number; peakPressureDelta: number };
    traits: string[];
    severity: number;
  }[];
  highlights: {
    zoneIndex: number;
    type: string;
    startProgress: number;
    endProgress: number;
    severity: number;
    notes: string;
  }[];
}

export interface BrakeTemperatureComparisonResponse {
  lap: { lapId: string; raceId: string; lapNumber: number };
  referenceLap: { lapId: string; raceId: string; lapNumber: number };
  signal: { source: string; unit: string };
  alignment: { pointCount: number; zoneCount: number };
  series: {
    progressRatio: number[];
    distanceM: number[];
    lapTempC: number[];
    lapPerWheelTempC: {
      flTempC: number[];
      frTempC: number[];
      rlTempC: number[];
      rrTempC: number[];
    };
    referenceTempC: number[];
    deltaTempC: number[];
    lapBrakePressure: number[];
  };
  peaks: {
    lap: { maxTempC: number; atProgress: number; atDistanceM: number };
    reference: { maxTempC: number; atProgress: number; atDistanceM: number };
    deltaMaxTempC: number;
  };
  zoneSummary: {
    zoneIndex: number;
    startProgress: number;
    endProgress: number;
    lap: { meanTempC: number; peakTempC: number; avgBrakePressure: number };
    reference: { meanTempC: number; peakTempC: number };
    delta: { meanTempC: number; peakTempC: number };
    classification: { thermal: string; brakeLoad: string; hotUnderLoad: boolean };
  }[];
  hottestZones: { zoneIndex: number; lap: { meanTempC: number } }[];
  comparisonSummary: {
    hotterProgressRatio: number;
    meanTempDeltaC: number;
    maxTempDeltaC: number;
    minTempDeltaC: number;
  };
}

export interface TrailBrakingZone {
  zoneId: number;
  start: { progress: number; distanceM: number };
  end: { progress: number; distanceM: number };
  peak: { progress: number; distanceM: number; brakePressure: number };
  releasePoint: { progress: number; distanceM: number; brakePressure: number };
  corner: { cornerStartProgress: number; extendsIntoCorner: boolean };
  trailBraking: {
    lengthM: number;
    durationS: number;
    intoCornerLengthM: number;
    intoCornerDurationS: number;
  };
  reference?: { zoneId: number; trailBraking: { lengthM: number } };
  delta?: { trailLengthM: number; peakProgress: number };
}

export interface TrailBrakingAnalysisResponse {
  lap: { lapId: string; raceId: string };
  referenceLap: { lapId: string; raceId: string };
  signal: { pressureMode: string; corneringSignal: string };
  zoneCount: number;
  zones: TrailBrakingZone[];
  detailedTrace?: {
    zoneId: number;
    lap: { zoneProgress: number[]; brakePressure: number[]; steeringRad: number[] };
    reference: { zoneProgress: number[]; brakePressure: number[]; steeringRad: number[] };
  };
}

export interface BrakeTransitionZone {
  zoneId: number;
  start: { progress: number; distanceM: number };
  end: { progress: number; distanceM: number };
  peakBrake: { progress: number; brakePressure: number };
  brakeRelease: { progress: number; distanceM: number };
  apex: { progress: number; distanceM: number; speedMps: number };
  throttleApplication: { progress: number; distanceM: number; throttlePct: number };
  transition: {
    brakeToThrottleGapS: number;
    brakeToThrottleGapM: number;
    overlapS: number;
    throttleDelayVsApexS: number;
    throttleDelayVsApexM: number;
    smoothnessScore: number;
    classification: string;
  };
  reference?: {
    zoneId: number;
    transition: {
      brakeToThrottleGapS: number;
      throttleDelayVsApexS: number;
      smoothnessScore: number;
    };
  };
  delta?: {
    gapS: number;
    throttleDelayVsApexS: number;
    smoothnessScore: number;
  };
}

export interface BrakeTransitionResponse {
  lap: { lapId: string; raceId: string };
  referenceLap: { lapId: string; raceId: string };
  signal: { brakePressureMode: string; throttleSource: string };
  zoneCount: number;
  zones: BrakeTransitionZone[];
  selectedZoneDetail: {
    zoneId: number;
    lap: {
      localProgress: number[];
      absoluteProgress: number[];
      brakePressure: number[];
      throttlePct: number[];
      markers: { brakeRelease: number; apex: number; throttleApplication: number };
      window: { startProgress: number; apexProgress: number; endProgress: number };
    };
    reference: {
      localProgress: number[];
      absoluteProgress: number[];
      brakePressure: number[];
      throttlePct: number[];
      markers: { brakeRelease: number; apex: number; throttleApplication: number };
    };
  };
}

export const fetchBrakePressureComparison = (
  points = 700,
): Promise<BrakePressureComparisonResponse> =>
  fetchJson(`/breaks/pressureComparison?points=${points}`);

export const fetchBrakeTemperatureComparison = (
  points = 500,
): Promise<BrakeTemperatureComparisonResponse> =>
  fetchJson(`/breaks/temperatureComparison?race_id=slow&reference_race_id=fast&points=${points}`);

export const fetchTrailBrakingAnalysis = (): Promise<TrailBrakingAnalysisResponse> =>
  fetchJson("/breaks/trailBrakingAnalysis?race_id=slow&reference_race_id=fast");

export const fetchBrakeTransition = (
  zoneId?: number,
): Promise<BrakeTransitionResponse> =>
  fetchJson(`/breaks/releaseThrottleTransition?race_id=slow&reference_race_id=fast${zoneId !== undefined ? `&zone_id=${zoneId}` : ""}`);

// Camera frames for mistake analysis
// Fetches images by timestamp — no mistake_id needed in the DB

export interface CameraFramesResponse {
  raceId: string;
  camera: number;
  fps: number;
  frameCount: number;
  frames: Array<string | CameraFrame>;
}

export interface CameraFrame {
  frameNumber: number;
  imageUrl: string;
  timestampSeconds: number;
  timestampNs: number;
  x: number;
  y: number;
  z: number;
}

export const fetchCameraFrames = (
  raceId: string,
  camera: number,
  startTimestamp: string,
  durationS: number = 10,
): Promise<CameraFramesResponse> =>
  fetchJson(`/camera/frames?race_id=${encodeURIComponent(raceId)}&camera=${camera}&start_ts=${encodeURIComponent(startTimestamp)}&duration=${durationS}`);
