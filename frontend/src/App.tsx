import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { Toaster } from "@/components/ui/toaster";
import { TooltipProvider } from "@/components/ui/tooltip";
import Index from "./pages/Index.tsx";
import Engine from "./pages/Engine.tsx";
import NotFound from "./pages/NotFound.tsx";

import Steering from "./pages/Steering.tsx";
import Brakes from "./pages/Brakes.tsx";
import History from "./pages/History.tsx";
import RaceDetail from "./pages/RaceDetail.tsx";
import Live from "./pages/Live.tsx";
import LiveSimulate from "./pages/LiveSimulate.tsx";


const queryClient = new QueryClient();

const App = () => (
  <QueryClientProvider client={queryClient}>
    <TooltipProvider>
      <Toaster />
      <Sonner />
      <BrowserRouter
        future={{
          v7_startTransition: true,
          v7_relativeSplatPath: true,
        }}
      >
        <Routes>
          <Route path="/" element={<Index />} />
          
          <Route path="/engine" element={<Engine />} />
          <Route path="/steering" element={<Steering />} />
          <Route path="/brakes" element={<Brakes />} />
          <Route path="/history" element={<History />} />
          <Route path="/history/:raceId" element={<RaceDetail />} />
          <Route path="/live" element={<Live />} />
          <Route path="/live/simulate" element={<LiveSimulate />} />
          
          {/* ADD ALL CUSTOM ROUTES ABOVE THE CATCH-ALL "*" ROUTE */}
          <Route path="*" element={<NotFound />} />
        </Routes>
      </BrowserRouter>
    </TooltipProvider>
  </QueryClientProvider>
);

export default App;
