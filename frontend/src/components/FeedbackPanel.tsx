import { Bot } from "lucide-react";

const feedback = [
  { title: "Turn 3 Entry:", text: "Braking 8m too late compared to optimal line. Consider earlier brake application for better corner entry speed." },
  { title: "Sector 2:", text: "Throttle application is 0.3s earlier than optimal on corner exit. Good improvement from previous lap." },
  { title: "Overall:", text: "Lap consistency improved by 12% compared to session average. Focus on Turn 7 apex for further gains." },
];

const FeedbackPanel = () => {
  return (
    <div className="bg-card border border-border rounded-lg p-4 flex flex-col h-full">
      <div className="flex items-center gap-2 mb-3">
        <Bot className="w-4 h-4 text-primary/70" />
        <span className="text-[10px] text-muted-foreground uppercase tracking-wider">AI Analysis</span>
      </div>
      <div className="flex flex-col gap-2.5 flex-1 overflow-y-auto">
        {feedback.map((f, i) => (
          <div key={i} className="bg-surface rounded-md px-3 py-2.5 border-l-2 border-primary/30">
            <p className="text-sm text-secondary-foreground leading-relaxed">
              <span className="font-medium text-foreground">{f.title}</span>{" "}
              <span className="text-muted-foreground">{f.text}</span>
            </p>
          </div>
        ))}
      </div>
    </div>
  );
};

export default FeedbackPanel;
