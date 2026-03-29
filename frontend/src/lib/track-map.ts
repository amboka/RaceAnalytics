import { useEffect, useState } from "react";

export type TrackPoint = [number, number];

interface SegmentFileRecord {
  segment_id: number;
  from_split: string;
  to_split: string;
  route: string;
  left_index_start: number;
  left_index_end: number;
  right_index_start: number;
  right_index_end: number;
  polygon: TrackPoint[];
}

interface SegmentMapFile {
  map_name: string;
  segments: SegmentFileRecord[];
}

interface BoundaryMapFile {
  boundaries: {
    left_border: TrackPoint[];
    right_border: TrackPoint[];
  };
}

export interface TrackBounds {
  minX: number;
  minY: number;
  maxX: number;
  maxY: number;
  width: number;
  height: number;
}

export interface TrackSegment {
  segmentId: number;
  fromSplit: string;
  toSplit: string;
  route: string;
  leftIndexStart: number;
  leftIndexEnd: number;
  rightIndexStart: number;
  rightIndexEnd: number;
  polygon: TrackPoint[];
  bounds: TrackBounds;
  center: { x: number; y: number };
  label: string;
  accent: string;
}

export interface TrackMapData {
  mapName: string;
  bounds: TrackBounds;
  leftBorder: TrackPoint[];
  rightBorder: TrackPoint[];
  trackPolygon: TrackPoint[];
  segments: TrackSegment[];
}

const SEGMENT_ACCENTS = ["#ff5c57", "#f6c445", "#35c6ff"];

const getBounds = (points: TrackPoint[]): TrackBounds => {
  const [firstX, firstY] = points[0] ?? [0, 0];
  let minX = firstX;
  let minY = firstY;
  let maxX = firstX;
  let maxY = firstY;

  for (const [x, y] of points) {
    minX = Math.min(minX, x);
    minY = Math.min(minY, y);
    maxX = Math.max(maxX, x);
    maxY = Math.max(maxY, y);
  }

  return {
    minX,
    minY,
    maxX,
    maxY,
    width: Math.max(maxX - minX, 1),
    height: Math.max(maxY - minY, 1),
  };
};

const getCenter = (bounds: TrackBounds) => ({
  x: bounds.minX + bounds.width / 2,
  y: bounds.minY + bounds.height / 2,
});

const mapSegment = (segment: SegmentFileRecord, index: number): TrackSegment => {
  const bounds = getBounds(segment.polygon);

  return {
    segmentId: segment.segment_id,
    fromSplit: segment.from_split,
    toSplit: segment.to_split,
    route: segment.route,
    leftIndexStart: segment.left_index_start,
    leftIndexEnd: segment.left_index_end,
    rightIndexStart: segment.right_index_start,
    rightIndexEnd: segment.right_index_end,
    polygon: segment.polygon,
    bounds,
    center: getCenter(bounds),
    label: `Sector ${String(segment.segment_id).padStart(2, "0")}`,
    accent: SEGMENT_ACCENTS[index % SEGMENT_ACCENTS.length],
  };
};

let trackMapPromise: Promise<TrackMapData> | null = null;

export const loadTrackMapData = async (): Promise<TrackMapData> => {
  if (!trackMapPromise) {
    trackMapPromise = Promise.all([
      fetch("/maps/yas_marina_segments.json").then(async (response) => {
        if (!response.ok) throw new Error("Unable to load Yas Marina segment map.");
        return response.json() as Promise<SegmentMapFile>;
      }),
      fetch("/maps/yas_marina_bnd.json").then(async (response) => {
        if (!response.ok) throw new Error("Unable to load Yas Marina boundary map.");
        return response.json() as Promise<BoundaryMapFile>;
      }),
    ]).then(([segmentFile, boundaryFile]) => {
      const leftBorder = boundaryFile.boundaries.left_border;
      const rightBorder = boundaryFile.boundaries.right_border;
      const trackPolygon = [...leftBorder, ...[...rightBorder].reverse()];
      const segments = segmentFile.segments.map(mapSegment);

      return {
        mapName: segmentFile.map_name,
        bounds: getBounds(trackPolygon),
        leftBorder,
        rightBorder,
        trackPolygon,
        segments,
      };
    });
  }

  return trackMapPromise;
};

export const useTrackMapData = () => {
  const [data, setData] = useState<TrackMapData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    loadTrackMapData()
      .then((result) => {
        if (cancelled) return;
        setData(result);
      })
      .catch((reason: Error) => {
        if (cancelled) return;
        setError(reason.message || "Unable to load track map.");
      })
      .finally(() => {
        if (cancelled) return;
        setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  return { data, loading, error };
};

export const padBounds = (bounds: TrackBounds, padding = 40): TrackBounds => ({
  minX: bounds.minX - padding,
  minY: bounds.minY - padding,
  maxX: bounds.maxX + padding,
  maxY: bounds.maxY + padding,
  width: bounds.width + padding * 2,
  height: bounds.height + padding * 2,
});

