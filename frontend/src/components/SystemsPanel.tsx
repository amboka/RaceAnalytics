import { Cog, Disc, Navigation } from "lucide-react";
import { useNavigate, useLocation } from "react-router-dom";

const systems = [
  { label: "Engine", icon: Cog, path: "/engine" },
  { label: "Brakes", icon: Disc, path: "/brakes" },
  { label: "Steering", icon: Navigation, path: "/steering" },
];

const SystemsPanel = () => {
  const navigate = useNavigate();
  const location = useLocation();

  return (
    <div className="flex flex-col items-center h-full border-l border-border py-4 px-2 w-[88px] shrink-0">
      <button
        onClick={() => navigate("/")}
        className="font-display text-[9px] uppercase tracking-[0.15em] text-muted-foreground mb-4 hover:text-foreground transition-colors cursor-pointer"
      >
        Systems
      </button>
      <div className="flex flex-col gap-1 flex-1 w-full">
        {systems.map((s) => {
          const isActive = s.path && location.pathname === s.path;
          return (
            <button
              key={s.label}
              onClick={() => s.path && navigate(s.path)}
              className={`flex flex-col items-center gap-1.5 py-3 rounded-lg transition-all cursor-pointer group flex-1 justify-center ${
                isActive ? "bg-surface" : "hover:bg-surface"
              } ${!s.path ? "opacity-50 cursor-default" : ""}`}
            >
              <s.icon className={`w-5 h-5 transition-colors ${isActive ? "text-primary" : "text-muted-foreground group-hover:text-primary"}`} />
              <span className={`text-[10px] transition-colors ${isActive ? "text-foreground" : "text-muted-foreground group-hover:text-secondary-foreground"}`}>
                {s.label}
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
};

export default SystemsPanel;
