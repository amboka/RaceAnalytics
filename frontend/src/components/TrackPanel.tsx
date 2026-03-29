import { useState } from "react";
import { MapPinned } from "lucide-react";
import InteractiveTrackMap from "@/components/InteractiveTrackMap";
import SegmentModal from "@/components/SegmentModal";
import type { TrackSegment } from "@/lib/track-map";

const TrackPanel = () => {
  const [selectedSegment, setSelectedSegment] = useState<TrackSegment | null>(null);
  const [modalOpen, setModalOpen] = useState(false);

  const handleSegmentSelect = (segment: TrackSegment) => {
    setSelectedSegment(segment);
    setModalOpen(true);
  };

  return (
    <>
      <div className="relative flex flex-1 flex-col rounded-[1.5rem] border border-white/10 bg-card/60 min-h-0 shadow-2xl shadow-black/20">
        <div className="flex items-center justify-between border-b border-white/10 px-4 py-3">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-primary/12 text-primary">
              <MapPinned className="h-4.5 w-4.5" />
            </div>
            <div>
              <p className="font-display text-sm tracking-[0.18em] text-white">Yas Marina</p>
              <p className="text-xs text-muted-foreground">Interactive sector navigator</p>
            </div>
          </div>

          <div className="hidden items-center gap-2 md:flex">
            <span className="rounded-full border border-white/10 bg-white/5 px-3 py-1 text-[11px] text-slate-400">3 sectors loaded</span>
            <span className="rounded-full border border-white/10 bg-white/5 px-3 py-1 text-[11px] text-slate-400">click to open</span>
          </div>
        </div>

        <div className="min-h-0 flex-1 p-3">
          <InteractiveTrackMap onSegmentSelect={handleSegmentSelect} className="min-h-full" />
        </div>
      </div>

      <SegmentModal
        segment={selectedSegment}
        open={modalOpen}
        onOpenChange={setModalOpen}
        onSegmentChange={(seg) => setSelectedSegment(seg)}
      />
    </>
  );
};

export default TrackPanel;
