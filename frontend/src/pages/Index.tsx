import Navbar from "@/components/Navbar";
import TrackPanel from "@/components/TrackPanel";
import MetricsPanel from "@/components/MetricsPanel";
import FeedbackPanel from "@/components/FeedbackPanel";
import SystemsPanel from "@/components/SystemsPanel";

const Index = () => {
  return (
    <div className="flex flex-col h-screen overflow-hidden">
      <Navbar />
      <div className="flex flex-1 min-h-0">
        {/* Main content */}
        <div className="flex flex-col gap-4 flex-1 min-h-0 p-4">
          {/* Track - 60% */}
          <div className="flex-[6] min-h-0 flex">
            <TrackPanel />
          </div>
          {/* Metrics + AI Feedback - 40% */}
          <div className="flex-[4] min-h-0 flex gap-4">
            <div className="flex-[6] min-h-0">
              <MetricsPanel />
            </div>
            <div className="flex-[4] min-h-0">
              <FeedbackPanel />
            </div>
          </div>
        </div>
        {/* Systems sidebar */}
        <SystemsPanel />
      </div>
    </div>
  );
};

export default Index;
