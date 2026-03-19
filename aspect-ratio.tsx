import "./index.css";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { Toaster } from "sonner";
import LandingPage from "./pages/LandingPage";
import AdminPage from "./pages/AdminPage";
import { useEffect } from "react";
import axios from "axios";

const API = "/api";

function App() {
  useEffect(() => {
    const seedData = async () => {
      try {
        await axios.post(`${API}/seed`);
      } catch {
        // already seeded or error, fine
      }
    };
    seedData();
  }, []);

  return (
    <div className="bg-black min-h-screen">
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<LandingPage />} />
          <Route path="/admin" element={<AdminPage />} />
        </Routes>
      </BrowserRouter>
      <Toaster position="top-center" />
    </div>
  );
}

export default App;
