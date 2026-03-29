import {
  ChevronDown,
  Settings,
  User,
  LogOut,
  HelpCircle,
  Sparkles,
  History,
  Radio,
} from "lucide-react";
import { useState, useRef, useEffect } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import CopilotChat from "./CopilotChat";

const Navbar = () => {
  const [menuOpen, setMenuOpen] = useState(false);
  const [copilotOpen, setCopilotOpen] = useState(() => {
    if (sessionStorage.getItem("copilot_opened")) return false;
    sessionStorage.setItem("copilot_opened", "1");
    return true;
  });
  const menuRef = useRef<HTMLDivElement>(null);
  const navigate = useNavigate();
  const location = useLocation();

  const isHistoryActive = location.pathname === "/history";
  const isLiveActive = location.pathname.startsWith("/live");

  useEffect(() => {
    const handleClick = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  return (
    <nav className="flex items-center justify-between px-5 py-2.5 border-b border-border bg-card">
      <div className="flex items-center gap-2.5">
        <div
          className="w-7 h-7 rounded bg-primary flex items-center justify-center cursor-pointer"
          onClick={() => navigate("/")}
        >
          <span className="font-display text-[10px] font-bold text-primary-foreground">
            RA
          </span>
        </div>
        <span
          className="font-display text-sm font-semibold tracking-wider text-foreground cursor-pointer"
          onClick={() => navigate("/")}
        >
          RaceAnalytics
        </span>
      </div>

      <div className="flex items-center gap-2">
        <button
          onClick={() => navigate("/history")}
          className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-medium transition-all ${
            isHistoryActive
              ? "bg-primary/15 text-primary border border-primary/30"
              : "text-muted-foreground hover:text-foreground hover:bg-surface border border-transparent"
          }`}
        >
          <History className="w-3.5 h-3.5" />
          <span>History</span>
        </button>

        <button
          onClick={() => navigate("/live")}
          className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-medium transition-all ${
            isLiveActive
              ? "bg-primary/15 text-primary border border-primary/30"
              : "text-muted-foreground hover:text-foreground hover:bg-surface border border-transparent"
          }`}
        >
          <Radio className="w-3.5 h-3.5" />
          <span>Live</span>
        </button>

        <button
          onClick={() => setCopilotOpen(!copilotOpen)}
          className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-medium transition-all ${
            copilotOpen
              ? "bg-primary/15 text-primary border border-primary/30"
              : "text-muted-foreground hover:text-foreground hover:bg-surface border border-transparent"
          }`}
        >
          <Sparkles className="w-3.5 h-3.5" />
          <span>Copilot</span>
        </button>

        <div ref={menuRef} className="relative">
          <button
            onClick={() => setMenuOpen(!menuOpen)}
            className="flex items-center gap-2 px-2 py-1.5 rounded-md hover:bg-surface transition-colors"
          >
            <div className="w-7 h-7 rounded-full bg-muted flex items-center justify-center text-xs font-medium text-muted-foreground">
              DR
            </div>
            <ChevronDown className="w-3.5 h-3.5 text-muted-foreground" />
          </button>

          {menuOpen && (
            <div className="absolute right-0 top-full mt-2 w-44 bg-card border border-border rounded-lg shadow-xl z-50 overflow-hidden">
              <button className="w-full flex items-center gap-3 px-4 py-2.5 text-sm text-secondary-foreground hover:bg-surface transition-colors">
                <User className="w-4 h-4" /> Profile
              </button>
              <button className="w-full flex items-center gap-3 px-4 py-2.5 text-sm text-secondary-foreground hover:bg-surface transition-colors">
                <Settings className="w-4 h-4" /> Settings
              </button>
              <button className="w-full flex items-center gap-3 px-4 py-2.5 text-sm text-secondary-foreground hover:bg-surface transition-colors">
                <HelpCircle className="w-4 h-4" /> Help
              </button>
              <div className="border-t border-border" />
              <button className="w-full flex items-center gap-3 px-4 py-2.5 text-sm text-destructive hover:bg-surface transition-colors">
                <LogOut className="w-4 h-4" /> Log Out
              </button>
            </div>
          )}
        </div>
      </div>

      <CopilotChat open={copilotOpen} onClose={() => setCopilotOpen(false)} />
    </nav>
  );
};

export default Navbar;
